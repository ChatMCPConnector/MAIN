from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# ── ANSI colour palette ──────────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_C_FG = {
    "grey": "\033[38;5;245m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "white": "\033[37m",
    "bright_cyan": "\033[96m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_red": "\033[91m",
    "bright_magenta": "\033[95m",
}

_C_BG = {
    "cyan": "\033[46m",
    "green": "\033[42m",
    "yellow": "\033[43m",
    "red": "\033[41m",
    "magenta": "\033[45m",
    "grey": "\033[48;5;240m",
}

# ── Level styling ────────────────────────────────────────────────────────────
# Use ASCII-safe icons on Windows to avoid codec errors with legacy code pages.
_IS_WINDOWS = sys.platform.startswith("win")

_LEVEL_STYLES: dict[str, dict[str, str]] = {
    "DEBUG": {
        "icon": "*" if _IS_WINDOWS else "◆",
        "fg": _C_FG["bright_cyan"],
        "bg": _C_BG["cyan"],
        "name_fg": _C_FG["cyan"],
    },
    "INFO": {
        "icon": ">" if _IS_WINDOWS else "●",
        "fg": _C_FG["bright_green"],
        "bg": _C_BG["green"],
        "name_fg": _C_FG["green"],
    },
    "WARNING": {
        "icon": "!" if _IS_WINDOWS else "▲",
        "fg": _C_FG["bright_yellow"],
        "bg": _C_BG["yellow"],
        "name_fg": _C_FG["yellow"],
    },
    "ERROR": {
        "icon": "x" if _IS_WINDOWS else "■",
        "fg": _C_FG["bright_red"],
        "bg": _C_BG["red"],
        "name_fg": _C_FG["red"],
    },
    "CRITICAL": {
        "icon": "X" if _IS_WINDOWS else "◈",
        "fg": _C_FG["bright_magenta"],
        "bg": _C_BG["magenta"],
        "name_fg": _C_FG["magenta"],
    },
}

_DATE_FMT = "%H:%M:%S"
_REDACTED_VALUE = "[REDACTED]"
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "authorization",
        "x-api-key",
        "x_api_key",
        "cookie",
        "api-key",
        "api_key",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?i)(authorization|x[-_]api[-_]key|cookie|api[-_]key|access[-_]token|refresh[-_]token)(\s*:\s*)([^\r\n]+)"
)
_SENSITIVE_QUOTED_RE = re.compile(
    r"(?i)(['\"])(authorization|x[-_]api[-_]key|cookie|api[-_]key|access[-_]token|refresh[-_]token)\1(\s*:\s*)(['\"])(.*?)\4"
)
# C-17: signierte URLs tragen ihre berechtigung im QUERY-STRING
# (`?signature=…&expires=…&X-Amz-Signature=…`). Die feld-basierte Redaktion
# greift dort nicht, weil der name in einer URL und nicht in einem key
# steht — der token landete vollstaendig im Debug-Log.
_SENSITIVE_QUERY_KEYS = (
    "signature",
    "sig",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "key",
    "auth",
    "authorization",
    "session",
    "sessionid",
    "credential",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-security-token",
    "x-goog-signature",
)
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:" + "|".join(re.escape(key) for key in _SENSITIVE_QUERY_KEYS) + r")=)[^&\s\"'\\]+"
)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    """Liest eine optionale Groessen-Konfiguration aus der Umgebung."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


class _SecureRotatingFileHandler(RotatingFileHandler):
    def doRollover(self) -> None:
        super().doRollover()
        base_path = Path(str(getattr(self, "baseFilename")))
        for path in (base_path, *base_path.parent.glob(f"{base_path.name}.*")):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, 0o600)


def redact_sensitive_text(value: str) -> str:
    def replace_quoted(match: re.Match[str]) -> str:
        replacement = match.group(5) if "…" in match.group(5) else _REDACTED_VALUE
        return (
            f"{match.group(1)}{match.group(2)}{match.group(1)}{match.group(3)}"
            f"{match.group(4)}{replacement}{match.group(4)}"
        )

    def replace_unquoted(match: re.Match[str]) -> str:
        replacement = match.group(3) if "…" in match.group(3) else _REDACTED_VALUE
        return f"{match.group(1)}{match.group(2)}{replacement}"

    value = _SENSITIVE_QUOTED_RE.sub(replace_quoted, value)
    value = _SENSITIVE_HEADER_RE.sub(replace_unquoted, value)
    # C-17: query-secrets signierter URLs zuletzt redigieren (der header- und
    # feld-pass greift fuer `?signature=…` nicht).
    return _SENSITIVE_QUERY_RE.sub(lambda match: f"{match.group(1)}{_REDACTED_VALUE}", value)


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in _SENSITIVE_FIELD_NAMES:
                item_text = str(item)
                redacted[key] = item if "…" in item_text or "<redacted>" in item_text else _REDACTED_VALUE
            else:
                redacted[key] = redact_sensitive_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


class _NameColumnMixin:
    """Gemeinsame Name-Spaltenlogik (breite wächst lazy bis Cap)."""

    _name_width = 16
    _name_max = 22

    def _pad_name(self, name: str) -> str:
        # Shorten common prefixes to keep output compact
        name = name.replace("glm2api.", "")
        if len(name) > self._name_width:
            self._name_width = min(len(name), self._name_max)
        return name.ljust(self._name_width)


class _TUIFormatter(_NameColumnMixin, logging.Formatter):
    """Terminal-UI inspired formatter with icons, colours and aligned columns."""

    def __init__(self, use_colour: bool = True) -> None:
        super().__init__()
        self.use_colour = use_colour

    def _colorize(self, text: str, codes: str) -> str:
        if not self.use_colour:
            return text
        return f"{codes}{text}{_RESET}"

    def format(self, record: logging.LogRecord) -> str:
        style = _LEVEL_STYLES.get(record.levelname, _LEVEL_STYLES["INFO"])
        time_str = self.formatTime(record, _DATE_FMT)

        # colourised components
        time_part = self._colorize(time_str, _C_FG["grey"] + _DIM)
        icon_part = self._colorize(f" {style['icon']} ", style["fg"] + _BOLD)
        level_badge = self._colorize(
            f" {record.levelname:<7} ",
            _C_FG["white"] + style["bg"] + _BOLD,
        )
        name_part = self._colorize(self._pad_name(record.name), style["name_fg"] + _DIM)

        # message — keep newlines but indent continuations
        message = record.getMessage()
        lines = message.splitlines()
        indent = " " * (len(time_str) + 1 + 3 + 1 + 9 + 1 + self._name_width + 3)
        formatted_lines: list[str] = []
        for idx, line in enumerate(lines):
            if idx == 0:
                formatted_lines.append(
                    f"{time_part} {icon_part} {level_badge} │ {name_part} │ {line}"
                )
            else:
                formatted_lines.append(f"{indent}{line}")

        return "\n".join(formatted_lines)


class _PlainFormatter(_NameColumnMixin, logging.Formatter):
    """Plain-text formatter for file logs (no colour, no icons)."""

    def format(self, record: logging.LogRecord) -> str:
        time_str = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        icon = _LEVEL_STYLES.get(record.levelname, _LEVEL_STYLES["INFO"])["icon"]
        message = record.getMessage()
        lines = message.splitlines()
        indent = " " * (len(time_str) + 1 + 3 + 1 + 9 + 1 + self._name_width + 3)
        formatted: list[str] = []
        for idx, line in enumerate(lines):
            if idx == 0:
                formatted.append(
                    f"{time_str} {icon} {record.levelname:<7} │ "
                    f"{self._pad_name(record.name)} │ {line}"
                )
            else:
                formatted.append(f"{indent}{line}")
        return "\n".join(formatted)


def _should_use_colour() -> bool:
    """Heuristic: use colour when stdout is a TTY."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def setup_logging(
    level: str,
    log_dir_name: str = "log",
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    # Attempt to force UTF-8 on Windows consoles so Unicode icons survive emit.
    if _IS_WINDOWS:
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    root = logging.getLogger()
    root.handlers.clear()
    # Der Bootstrap-Handler aus load_config() (fängt fruehe Config-Logs vor
    # dem vollen Setup ab) muss hier weg — sonst dupliziert sich JEDE
    # glm2api-Zeile: einmal via Propagation zum glm2api-Logger-Handler,
    # einmal via root-Console-Handler.
    logging.getLogger("glm2api").handlers.clear()
    resolved_level = getattr(logging, str(level).upper(), logging.INFO)
    root.setLevel(resolved_level)
    logging.getLogger("glm2api").setLevel(resolved_level)

    # ── Console handler (TUI style) ──────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_TUIFormatter(use_colour=_should_use_colour()))
    root.addHandler(console)

    # ── File handler (plain text, only when DEBUG) ───────────────────────────
    if resolved_level <= logging.DEBUG:
        # D-11: der wert kommt aus der config, nicht aus os.environ.
        # `load_config()` liest die .env, exportiert sie aber nicht in die
        # umgebung — ein in der datei gesetzter `GLM2API_LOG_DIR` war
        # damit still wirkungslos, waehrend die datei ihn als gueltige
        # option auswies.
        log_dir = Path(log_dir_name)
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(log_dir, 0o700)
        for existing_log in log_dir.glob("glm2api_debug.log*"):
            if existing_log.is_file() and not existing_log.is_symlink():
                os.chmod(existing_log, 0o600)
        log_path = log_dir / "glm2api_debug.log"
        # 100 MB pro Generation statt 10 MB: das Debug-Log ist bewusst
        # vollstaendig (1:1 Requests/Antworten), weil es die Grundlage fuer
        # Nachvollzug und Patches ist. Beim Wert von 10 MB fehlten genau die
        # Ereignisse, die man zum Debuggen brauchte. Staendige
        # Wegwerf-Logs sind keine Datenhaltung — hier zaehlt
        # Nachvollziehbarkeit, und die Platte ist begrenzt.
        # D-11: siehe log_dir — auch diese beiden kamen vorher nur aus
        # os.environ und ignorierten die .env.
        file_handler = _SecureRotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        os.chmod(log_path, 0o600)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_PlainFormatter())
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def serialize_for_debug(value: Any) -> str:
    value = redact_sensitive_data(value)
    if isinstance(value, bytes):
        try:
            return redact_sensitive_text(value.decode("utf-8"))
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, str):
        return redact_sensitive_text(value)
    try:
        import json

        return redact_sensitive_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        )
    except Exception:
        return redact_sensitive_text(repr(value))


def debug_dump(logger: logging.Logger, enabled: bool, title: str, value: Any) -> None:
    if not enabled:
        return
    logger.debug("%s\n%s", redact_sensitive_text(title), serialize_for_debug(value))
