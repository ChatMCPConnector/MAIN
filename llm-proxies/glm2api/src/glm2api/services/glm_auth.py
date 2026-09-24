from __future__ import annotations

import hashlib
import gzip
import io
import json
import os
import random
import re
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from typing import Iterable

from ..config import AppConfig, GUEST_REFRESH_TOKEN_MARKER
from ..logging_utils import debug_dump


SIGN_SECRET = "8a1317a7468aa3ad86e997d08f3f31cb"
ACCESS_TOKEN_EXPIRES_SECONDS = 3600
MAX_JSON_RESPONSE_BYTES = 1024 * 1024
ACCOUNT_RETRY_STATUS_CODES = {401, 403, 408, 425, 429}
ACCOUNT_RETRY_UPSTREAM_ERROR_CODES = {10025, 10061, 10062}
DETERMINISTIC_UPSTREAM_ERROR_CODES = {10040}
ACCOUNT_AUTH_ERROR_CODES = {
    "authentication_failed",
    "expired_token",
    "forbidden",
    "invalid_grant",
    "invalid_token",
    "token_expired",
    "unauthorized",
}

_TOKEN_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:access[_-]?token|refresh[_-]?token|guest[_-]?token|id[_-]?token|token)\b\s*[:=]\s*)"
    r"([\"']?)([^\"'\s,;}]+)([\"']?)"
)
_AUTHORIZATION_RE = re.compile(
    r"(?i)(\bauthorization\b\s*[:=]\s*)(?:(bearer)\s+)?([^\"'\s,;}]+)"
)
_BEARER_RE = re.compile(r"(?i)(\bbearer\s+)([^\s,;}]+)")
_AUTH_ERROR_TEXT_RE = re.compile(
    r"(?i)\b(?:invalid|expired|revoked)\s+(?:(?:access|refresh)\s+)?token\b"
    r"(?!\s+(?:count|limit|length|budget)\b)"
    r"|\btoken\s+(?:is\s+)?(?:expired|revoked|invalid)\b(?!\s+(?:count|limit|length|budget)\b)"
    r"|\b(?:unauthorized|authentication\s+failed)\b"
)


def redact_token(value: object) -> str:
    token = value if isinstance(value, str) else str(value)
    if not token:
        return "<redacted>"
    if len(token) <= 8:
        return "<redacted>"
    return f"{token[:4]}…{token[-4:]}"


def _is_sensitive_key(key: object) -> bool:
    normalized = "".join(char for char in str(key).casefold() if char.isalnum())
    sensitive_keys = {"authorization", "proxyauthorization", "cookie", "setcookie", "xapikey", "apikey"}
    return normalized in sensitive_keys or normalized.endswith("token")


def redact_sensitive_text(value: object, extra_secrets: Iterable[str] = ()) -> str:
    text = str(value)
    secrets = {secret for secret in extra_secrets if isinstance(secret, str) and secret}
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, redact_token(secret))

    def replace_authorization(match: re.Match[str]) -> str:
        scheme = f"{match.group(2)} " if match.group(2) else ""
        return f"{match.group(1)}{scheme}{redact_token(match.group(3))}"

    def replace_assignment(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{redact_token(match.group(3))}{match.group(4)}"

    text = _AUTHORIZATION_RE.sub(replace_authorization, text)
    text = _TOKEN_ASSIGNMENT_RE.sub(replace_assignment, text)
    return _BEARER_RE.sub(lambda match: f"{match.group(1)}{redact_token(match.group(2))}", text)


def redact_sensitive(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: redact_token(item) if _is_sensitive_key(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact_sensitive(item) for item in value)
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return f"<{len(value)} binary bytes>"
        try:
            return redact_sensitive(json.loads(text))
        except json.JSONDecodeError:
            return redact_sensitive_text(text)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _token_values(payload: object) -> set[str]:
    values: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _is_sensitive_key(key) and isinstance(value, str) and value:
                values.add(value)
            else:
                values.update(_token_values(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            values.update(_token_values(item))
    return values


def _safe_error_code(value: object, secrets: Iterable[str] = ()) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)[:64]
    text = redact_sensitive_text(value, secrets)
    if not text.isprintable():
        return "invalid"
    if len(text) > 32:
        return redact_token(text)
    return text or "unknown"


class GLMAuthError(RuntimeError):
    def __init__(
        self,
        status_code: int | None,
        error_code: object = None,
        secrets: Iterable[str] = (),
    ) -> None:
        safe_code = _safe_error_code(error_code, secrets)
        self.status_code = status_code
        self.error_code = safe_code
        super().__init__(f"GLM authentication failed status={status_code or 'unknown'} code={safe_code}")


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
    refresh_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


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
        headers = response.headers
        content_type = str(headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise RuntimeError("GLM response has an unexpected content type; expected JSON")

        raw_body = response.read(MAX_JSON_RESPONSE_BYTES + 1)
        if len(raw_body) > MAX_JSON_RESPONSE_BYTES:
            raise RuntimeError("GLM JSON response exceeds the size limit")

        content_encoding = str(headers.get("Content-Encoding", "identity")).strip().casefold()
        if content_encoding not in {"", "identity", "gzip", "deflate"}:
            raise RuntimeError("GLM response uses an unsupported content encoding")
        if content_encoding == "gzip":
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as compressed:
                    raw_body = compressed.read(MAX_JSON_RESPONSE_BYTES + 1)
            except (EOFError, OSError, zlib.error) as exc:
                raise RuntimeError("Failed to decompress gzip-encoded GLM response") from exc
        elif content_encoding == "deflate":
            try:
                decompressor = zlib.decompressobj()
                raw_body = decompressor.decompress(raw_body, MAX_JSON_RESPONSE_BYTES + 1)
                if decompressor.unconsumed_tail:
                    raise RuntimeError("GLM JSON response exceeds the size limit")
                if not decompressor.eof:
                    raise RuntimeError("Failed to decompress deflate-encoded GLM response")
            except zlib.error as exc:
                raise RuntimeError("Failed to decompress deflate-encoded GLM response") from exc

        if len(raw_body) > MAX_JSON_RESPONSE_BYTES:
            raise RuntimeError("GLM JSON response exceeds the size limit")
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except UnicodeDecodeError:
            raise RuntimeError("GLM response is not valid UTF-8") from None
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"GLM response is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
            ) from None
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected GLM response format, expected JSON object, got: {type(payload).__name__}"
            )
        debug_dump(self.logger, self.config.debug_dump_all, "GLM redacted JSON response", redact_sensitive(payload))
        return payload

    def _error_code_from_payload(self, payload: dict[str, object]) -> object:
        for key in ("code", "error_code"):
            if key in payload and payload[key] is not None:
                return payload[key]
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("code", "error_code"):
                if key in error and error[key] is not None:
                    return error[key]
        status = payload.get("status")
        return status if status is not None else None

    def _auth_error(
        self,
        status_code: int | None,
        payload: dict[str, object],
    ) -> GLMAuthError:
        secrets = self._known_token_values()
        secrets.update(_token_values(payload))
        return GLMAuthError(status_code, self._error_code_from_payload(payload), secrets)

    def _request_auth_json(self, request) -> tuple[int, dict[str, object]]:
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                status = int(getattr(response, "status", None) or response.getcode())
                try:
                    return status, self.read_json_response(response)
                except (OSError, RuntimeError):
                    raise GLMAuthError(status, "invalid_response") from None
        except urllib.error.HTTPError as exc:
            payload: dict[str, object] = {}
            try:
                payload = self.read_json_response(exc)
            except (OSError, RuntimeError):
                pass
            raise self._auth_error(exc.code, payload) from None

    def _validate_auth_response(
        self,
        status: int,
        payload: dict[str, object],
        fallback_refresh_token: str | None,
    ) -> tuple[str, str]:
        code = self._error_code_from_payload(payload)
        code_is_success = code is None
        if code is not None and not isinstance(code, bool):
            try:
                code_is_success = int(code) == 0  # type: ignore[arg-type]
            except (TypeError, ValueError):
                code_is_success = False
        if status != 200 or not code_is_success:
            raise self._auth_error(status, payload)

        result = payload.get("result")
        if not isinstance(result, dict):
            raise GLMAuthError(status, "invalid_result", self._known_token_values())
        access_token = result.get("access_token")
        refresh_token = result.get("refresh_token")
        if refresh_token is None:
            refresh_token = fallback_refresh_token
        if not self._is_valid_token(access_token) or not self._is_valid_token(refresh_token):
            raise GLMAuthError(status, "invalid_token", self._known_token_values() | _token_values(result))
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        return access_token, refresh_token

    @staticmethod
    def _is_valid_token(value: object) -> bool:
        return isinstance(value, str) and bool(value) and not any(char.isspace() for char in value)

    def _known_token_values(self) -> set[str]:
        with self._lock:
            values = {account.refresh_token for account in self._accounts if account.refresh_token}
            values.update(
                account.cached_token.access_token
                for account in self._accounts
                if account.cached_token and account.cached_token.access_token
            )
            return values

    def get_account_count(self) -> int:
        return len(self._accounts)

    def get_registered_account_indices(self) -> list[int]:
        with self._lock:
            return [i for i, acc in enumerate(self._accounts) if not acc.is_guest]

    def get_current_account_index(self) -> int:
        with self._lock:
            return self._current_index

    def is_guest_account(self, account_index: int) -> bool:
        with self._lock:
            return self._accounts[account_index].is_guest

    def advance_account(self, failed_index: int, reason: str) -> int:
        safe_reason = redact_sensitive_text(reason, self._known_token_values())
        with self._lock:
            if failed_index != self._current_index:
                return self._current_index
            next_index = (failed_index + 1) % len(self._accounts)
            self._current_index = next_index
            self.logger.warning(
                "Account request failed, switching refresh_token account index=%s -> %s reason=%s",
                failed_index,
                next_index,
                safe_reason,
            )
            return next_index

    def reset_account_cycle(self) -> None:
        with self._lock:
            self._current_index = 0

    def invalidate_account(self, account_index: int) -> None:
        with self._lock:
            self._accounts[account_index].cached_token = None

    def get_access_token_for_account(self, account_index: int) -> str:
        with self._lock:
            account = self._accounts[account_index]
            cached_token = account.cached_token
            if cached_token and time.time() < cached_token.expires_at - 60:
                self.logger.debug(
                    "Using cached access_token account=%s remaining=%.0fs",
                    account_index,
                    cached_token.expires_at - time.time(),
                )
                return cached_token.access_token

        # Pro Account serialisieren: andere Accounts bleiben parallel, gleiche
        # Refreshes warten aber auf exakt einen Upstream-Aufruf.
        with account.refresh_lock:
            with self._lock:
                cached_token = self._accounts[account_index].cached_token
                if cached_token and time.time() < cached_token.expires_at - 60:
                    return cached_token.access_token
            token = self._refresh_access_token(account_index)
            with self._lock:
                self._accounts[account_index].cached_token = token
            return token.access_token

    def _refresh_access_token(self, account_index: int) -> AccessToken:
        with self._lock:
            account = self._accounts[account_index]
            old_refresh_token = account.refresh_token
            is_guest = account.is_guest
        if is_guest or not old_refresh_token:
            return self._fetch_guest_access_token(account_index)

        timestamp, nonce, sign = build_sign()
        request = urllib.request.Request(
            self.config.refresh_url,
            data=b"{}",
            method="POST",
            headers={
                **self.get_browser_headers(),
                "Authorization": f"Bearer {old_refresh_token}",
                "X-Device-Id": uuid.uuid4().hex,
                "X-Nonce": nonce,
                "X-Request-Id": uuid.uuid4().hex,
                "X-Sign": sign,
                "X-Timestamp": timestamp,
            },
        )
        debug_dump(
            self.logger,
            self.config.debug_dump_all,
            f"GLM refresh access_token request headers account={account_index}",
            redact_sensitive(dict(request.header_items())),
        )
        debug_dump(
            self.logger,
            self.config.debug_dump_all,
            f"GLM refresh access_token request body account={account_index}",
            b"{}",
        )
        status, payload = self._request_auth_json(request)
        access_token, refresh_token = self._validate_auth_response(status, payload, old_refresh_token)
        persisted = True
        if refresh_token != old_refresh_token:
            try:
                self._persist_refresh_token(account_index, refresh_token)
            except Exception as exc:
                persisted = False
                safe_error = redact_sensitive_text(exc, {old_refresh_token, refresh_token})
                self.logger.warning(
                    "Failed to write back GLM refresh_token index=%s error=%s",
                    account_index,
                    safe_error,
                )
            with self._lock:
                self._accounts[account_index].refresh_token = refresh_token
            self.logger.info(
                "GLM refresh_token automatically refreshed index=%s persisted=%s",
                account_index,
                persisted,
            )
        return AccessToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + ACCESS_TOKEN_EXPIRES_SECONDS - random.randint(10, 30),
        )

    def _fetch_guest_access_token(self, account_index: int) -> AccessToken:
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
        debug_dump(
            self.logger,
            self.config.debug_dump_all,
            f"GLM guest token request headers account={account_index}",
            redact_sensitive(dict(request.header_items())),
        )
        debug_dump(
            self.logger,
            self.config.debug_dump_all,
            f"GLM guest token request body account={account_index}",
            b"",
        )
        status, payload = self._request_auth_json(request)
        access_token, refresh_token = self._validate_auth_response(status, payload, None)
        with self._lock:
            self._accounts[account_index].refresh_token = refresh_token
        self.logger.info("Obtained new GLM guest refresh_token index=%s", account_index)
        return AccessToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + ACCESS_TOKEN_EXPIRES_SECONDS - random.randint(10, 30),
        )

    @staticmethod
    def _atomic_write_text(path: Path, content: str, label: str) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path)
        except (OSError, UnicodeError) as exc:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise RuntimeError(f"Failed to atomically write {label} error={type(exc).__name__}") from None

    def _persist_refresh_token(self, account_index: int, refresh_token: str) -> None:
        with self._persist_lock:
            with self._lock:
                if self._accounts[account_index].is_guest:
                    return
            tokens = list(self.config.glm_refresh_tokens)
            if account_index < 0 or account_index >= len(tokens):
                raise RuntimeError("Cannot persist refresh token for unknown account index")
            tokens[account_index] = refresh_token
            try:
                if self.config.token_file_path.exists() or len(tokens) > 1:
                    self._atomic_write_text(
                        self.config.token_file_path,
                        "\n".join(tokens) + "\n",
                        "token file",
                    )
                else:
                    self._persist_env_refresh_token(refresh_token)
            finally:
                self.config.glm_refresh_tokens[:] = tokens
                if account_index == 0:
                    self.config.glm_refresh_token = refresh_token

    def _persist_env_refresh_token(self, refresh_token: str) -> None:
        env_path = self.config.env_file_path
        if not env_path.exists():
            self.logger.warning(".env file does not exist, cannot automatically write back new refresh_token")
            return

        try:
            content = env_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise RuntimeError(".env is not valid UTF-8 encoded") from None
        except OSError as exc:
            raise RuntimeError(f"Failed to read .env error={type(exc).__name__}") from None
        lines = content.splitlines()
        replacement = f"GLM_REFRESH_TOKEN={refresh_token}"
        updated = False

        for index, line in enumerate(lines):
            if line.startswith("GLM_REFRESH_TOKEN="):
                lines[index] = replacement
                updated = True

        if not updated:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(replacement)

        self._atomic_write_text(env_path, "\n".join(lines) + "\n", ".env")

    def should_switch_account(self, exc: Exception) -> bool:
        if isinstance(exc, GLMAuthError):
            return True

        payload = getattr(exc, "payload", None)
        error_code: object = None
        if isinstance(payload, dict):
            error_code = self._error_code_from_payload(payload)
        if error_code is not None and not isinstance(error_code, bool):
            if str(error_code).casefold() in ACCOUNT_AUTH_ERROR_CODES:
                return True
            try:
                numeric_error_code = int(error_code)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                numeric_error_code = None
            if numeric_error_code in DETERMINISTIC_UPSTREAM_ERROR_CODES:
                return False
            if numeric_error_code in ACCOUNT_RETRY_UPSTREAM_ERROR_CODES:
                return True

        has_auth_error_text = False
        if isinstance(payload, dict):
            error_details = payload
            nested_error = payload.get("error")
            if isinstance(nested_error, dict):
                error_details = nested_error
            error_text = str(error_details.get("message") or error_details.get("err_msg") or "")
            has_auth_error_text = bool(_AUTH_ERROR_TEXT_RE.search(error_text))

        raw_status = getattr(exc, "status_code", None)
        if raw_status is None and isinstance(exc, urllib.error.HTTPError):
            raw_status = exc.code
        try:
            status_code = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            status_code = None
        if status_code is not None:
            if status_code in {400, 404, 409, 413, 422}:
                return has_auth_error_text
            return status_code in ACCOUNT_RETRY_STATUS_CODES or status_code >= 500
        if has_auth_error_text:
            return True

        if isinstance(exc, urllib.error.URLError):
            reason = redact_sensitive_text(exc.reason).casefold()
            return not any(marker in reason for marker in ("certificate verify failed", "certificate_verify_failed"))
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        return False
