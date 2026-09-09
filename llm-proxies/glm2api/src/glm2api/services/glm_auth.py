from __future__ import annotations

import hashlib
import gzip
import json
import random
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from logging import Logger

from ..config import AppConfig, GUEST_REFRESH_TOKEN_MARKER
from ..logging_utils import debug_dump


SIGN_SECRET = "8a1317a7468aa3ad86e997d08f3f31cb"
ACCESS_TOKEN_EXPIRES_SECONDS = 3600


def build_sign() -> tuple[str, str, str]:
    now = str(int(time.time() * 1000))
    digits = [int(char) for char in now]
    checksum = (sum(digits) - digits[-2]) % 10
    timestamp = now[:-2] + str(checksum) + now[-1]
    nonce = uuid.uuid4().hex
    sign = hashlib.md5(f"{timestamp}-{nonce}-{SIGN_SECRET}".encode("utf-8")).hexdigest()
    return timestamp, nonce, sign


def build_random_x_forwarded_for() -> str:
    while True:
        first_octet = random.randint(1, 223)
        if first_octet in {10, 127, 169, 172, 192}:
            continue
        octets = [first_octet]
        for _ in range(3):
            octets.append(random.randint(0, 255))
        return ".".join(str(octet) for octet in octets)


@dataclass(slots=True)
class AccessToken:
    access_token: str
    refresh_token: str
    expires_at: float


@dataclass(slots=True)
class AccountState:
    refresh_token: str
    is_guest: bool = False
    cached_token: AccessToken | None = None


class GLMAccessTokenManager:
    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self._accounts = [
            AccountState(
                refresh_token="" if token == GUEST_REFRESH_TOKEN_MARKER else token,
                is_guest=(token == GUEST_REFRESH_TOKEN_MARKER),
            )
            for token in config.glm_refresh_tokens
        ]
        self._current_index = 0
        self._lock = threading.Lock()
        self._persist_lock = threading.Lock()
        logger.info(
            "Account manager initialized accounts=%s guest_mode=%s",
            len(self._accounts),
            any(a.is_guest for a in self._accounts),
        )

    def get_browser_headers(self, app_fr: str = "browser_extension") -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*" if app_fr == "default" else "text/event-stream",
            "Accept-Encoding": "gzip, deflate" if app_fr == "default" else "identity",
            "Accept-Language": "en-US,en;q=0.9",
            "App-Name": "chatglm",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "Origin": "https://chatglm.cn",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Sec-Ch-Ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": self.config.glm_user_agent,
            "X-App-Fr": app_fr,
            "X-App-Platform": "pc",
            "X-App-Version": "0.0.1",
            "X-Device-Brand": "",
            "X-Device-Model": "",
            "X-Lang": "en",
            "X-Forwarded-For": build_random_x_forwarded_for(),
        }

    def read_json_response(self, response) -> dict[str, object]:
        try:
            raw_body = response.read()
            content_encoding = response.headers.get("Content-Encoding", "").lower()

            if content_encoding == "gzip":
                raw_body = gzip.decompress(raw_body)

            debug_dump(self.logger, self.config.debug_dump_all, "GLM raw JSON response body", raw_body)
            payload = json.loads(raw_body.decode("utf-8"))
        except gzip.BadGzipFile as exc:
            raise RuntimeError("Failed to decompress gzip-encoded GLM response") from exc
        except UnicodeDecodeError as exc:
            raise RuntimeError("GLM response is not valid UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GLM response is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected GLM response format, expected JSON object, got: {type(payload).__name__}")
        return payload

    def get_account_count(self) -> int:
        return len(self._accounts)

    def get_current_account_index(self) -> int:
        with self._lock:
            return self._current_index

    def is_guest_account(self, account_index: int) -> bool:
        with self._lock:
            return self._accounts[account_index].is_guest

    def advance_account(self, failed_index: int, reason: str) -> int:
        with self._lock:
            if failed_index != self._current_index:
                return self._current_index
            next_index = (failed_index + 1) % len(self._accounts)
            self._current_index = next_index
            self.logger.warning(
                "Account request failed, switching refresh_token account index=%s -> %s reason=%s",
                failed_index,
                next_index,
                reason,
            )
            return next_index

    def reset_account_cycle(self) -> None:
        with self._lock:
            self._current_index = 0

    def invalidate_account(self, account_index: int) -> None:
        with self._lock:
            self._accounts[account_index].cached_token = None

    def get_access_token_for_account(self, account_index: int) -> str:
        # Lock nur fuer Cache-Lookup und State-Update; der Netzwerk-Refresh
        # laeuft AUSSERHALB des Locks (sonst blockiert ein langsamer/timeoutender
        # Refresh alle anderen Accounts bis zu request_timeout=120s).
        # Double-checked: nach dem Refresh erneut pruefen, ob zwischenzeitlich
        # ein parallel laufender Refresh schon ein frisches Token gesetzt hat.
        with self._lock:
            account = self._accounts[account_index]
            if account.cached_token and time.time() < account.cached_token.expires_at - 60:
                self.logger.debug("Using cached access_token account=%s remaining=%.0fs", account_index, account.cached_token.expires_at - time.time())
                return account.cached_token.access_token
        token = self._refresh_access_token(account_index)
        with self._lock:
            account = self._accounts[account_index]
            if account.cached_token and time.time() < account.cached_token.expires_at - 60:
                # paralleler Refresh war schneller — deren Token nutzen, unseres verwerfen
                return account.cached_token.access_token
            account.cached_token = token
            return token.access_token

    def _refresh_access_token(self, account_index: int) -> AccessToken:
        account = self._accounts[account_index]
        if account.is_guest or not account.refresh_token:
            return self._fetch_guest_access_token(account_index)
        timestamp, nonce, sign = build_sign()
        request = urllib.request.Request(
            self.config.refresh_url,
            data=b"{}",
            method="POST",
            headers={
                **self.get_browser_headers(),
                "Authorization": f"Bearer {account.refresh_token}",
                "X-Device-Id": uuid.uuid4().hex,
                "X-Nonce": nonce,
                "X-Request-Id": uuid.uuid4().hex,
                "X-Sign": sign,
                "X-Timestamp": timestamp,
            },
        )
        debug_dump(self.logger, self.config.debug_dump_all, f"GLM refresh access_token request headers account={account_index}", dict(request.header_items()))
        debug_dump(self.logger, self.config.debug_dump_all, f"GLM refresh access_token request body account={account_index}", b"{}")
        with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
            status = response.status
            payload = self.read_json_response(response)
        code = payload.get("code", payload.get("status"))
        result: dict[str, object] = payload.get("result") or {}
        access_token = result.get("access_token")
        refresh_token = result.get("refresh_token", account.refresh_token)
        if status != 200 or code not in {0, None} or not access_token:
            raise RuntimeError(f"Failed to refresh GLM token: {payload}") from None
        if refresh_token != account.refresh_token:
            try:
                self._persist_refresh_token(account_index, refresh_token)
            except Exception as exc:
                self.logger.warning("Failed to write back GLM refresh_token index=%s error=%s", account_index, exc)
            account.refresh_token = refresh_token
            self.config.glm_refresh_tokens[account_index] = refresh_token
            if account_index == 0:
                self.config.glm_refresh_token = refresh_token
            self.logger.info("GLM refresh_token automatically refreshed and written back to account storage index=%s", account_index)
        return AccessToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + ACCESS_TOKEN_EXPIRES_SECONDS - random.randint(10, 30),
        )

    def _fetch_guest_access_token(self, account_index: int) -> AccessToken:
        account = self._accounts[account_index]
        timestamp, nonce, sign = build_sign()
        request_id = uuid.uuid4().hex
        device_id = uuid.uuid4().hex
        request = urllib.request.Request(
            self.config.guest_refresh_url,
            data=b"",
            method="POST",
            headers={
                **self.get_browser_headers(app_fr="default"),
                "Content-Length": "0",
                "Referer": "https://chatglm.cn/",
                "X-Device-Id": device_id,
                "X-Nonce": nonce,
                "X-Request-Id": request_id,
                "X-Sign": sign,
                "X-Timestamp": timestamp,
            },
        )
        debug_dump(self.logger, self.config.debug_dump_all, f"GLM guest token request headers account={account_index}", dict(request.header_items()))
        debug_dump(self.logger, self.config.debug_dump_all, f"GLM guest token request body account={account_index}", b"")
        with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
            status = response.status
            payload = self.read_json_response(response)
        code = payload.get("code", payload.get("status"))
        result: dict[str, object] = payload.get("result") or {}
        access_token = result.get("access_token")
        refresh_token = result.get("refresh_token")
        if status != 200 or code not in {0, None} or not access_token or not refresh_token:
            raise RuntimeError(f"Failed to obtain GLM guest token: {payload}") from None
        account.refresh_token = str(refresh_token)
        self.logger.info("Obtained new GLM guest refresh_token index=%s", account_index)
        return AccessToken(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            expires_at=time.time() + ACCESS_TOKEN_EXPIRES_SECONDS - random.randint(10, 30),
        )

    def _persist_refresh_token(self, account_index: int, refresh_token: str) -> None:
        with self._persist_lock:
            if self._accounts[account_index].is_guest:
                return
            if self.config.token_file_path.exists() or len(self.config.glm_refresh_tokens) > 1:
                tokens = list(self.config.glm_refresh_tokens)
                tokens[account_index] = refresh_token
                content = "\n".join(tokens) + "\n"
                try:
                    self.config.token_file_path.write_text(content, encoding="utf-8")
                except OSError as exc:
                    raise RuntimeError(f"Failed to write token file: {self.config.token_file_path} error={exc}") from exc
                return
            self._persist_env_refresh_token(refresh_token)

    def _persist_env_refresh_token(self, refresh_token: str) -> None:
        env_path = self.config.env_file_path
        if not env_path.exists():
            self.logger.warning(".env file does not exist, cannot automatically write back new refresh_token")
            return

        try:
            content = env_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f".env is not valid UTF-8 encoded: {env_path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to read .env: {env_path} error={exc}") from exc
        lines = content.splitlines()
        updated = False

        for index, line in enumerate(lines):
            if line.startswith("GLM_REFRESH_TOKEN="):
                lines[index] = f"GLM_REFRESH_TOKEN={refresh_token}"
                updated = True
                break

        if not updated:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"GLM_REFRESH_TOKEN={refresh_token}")

        new_content = "\n".join(lines) + "\n"
        try:
            env_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write .env: {env_path} error={exc}") from exc

    def should_switch_account(self, exc: Exception) -> bool:
        if hasattr(exc, "status_code"):
            return True
        if isinstance(exc, urllib.error.HTTPError):
            return True
        if isinstance(exc, urllib.error.URLError):
            return True
        if isinstance(exc, TimeoutError):
            return True
        if isinstance(exc, RuntimeError):
            return "token" in str(exc).lower()
        return False
