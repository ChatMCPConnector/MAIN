from __future__ import annotations

import difflib
import logging
import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .model_variants import expand_model_variants


DEFAULT_ASSISTANT_ID = "65940acff94777010aa6b796"
DEFAULT_IMAGE_ASSISTANT_ID = "65a232c082ff90a2ad2f15e2"
DEFAULT_IMAGE_MODEL_NAME = "glm-image-1"
DEFAULT_GLM_BASE_URL = "https://chatglm.cn/chatglm"
GUEST_REFRESH_TOKEN_MARKER = "__glm_guest__"
DEFAULT_BLOCKED_TOOL_NAMES = ()
DEFAULT_MAX_REQUEST_BODY_BYTES = 32 * 1024 * 1024
DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_REQUEST_LINE_BYTES = 8192
DEFAULT_MAX_HEADERS = 64
DEFAULT_MAX_HEADER_BYTES = 64 * 1024
DEFAULT_MAX_CONNECTIONS = 32
DEFAULT_REQUEST_QUEUE_SIZE = 32
MAX_REQUEST_BODY_BYTES_LIMIT = 128 * 1024 * 1024
MAX_REQUEST_SOCKET_TIMEOUT_SECONDS = 300.0
MAX_REQUEST_LINE_BYTES_LIMIT = 64 * 1024
MAX_HEADERS_LIMIT = 100
MAX_HEADER_BYTES_LIMIT = 1024 * 1024
MAX_CONNECTIONS_LIMIT = 128
MAX_REQUEST_QUEUE_SIZE_LIMIT = 128
MAX_CONCURRENCY_LIMIT = 32
MAX_REQUEST_TIMEOUT_SECONDS = 900
MAX_QUEUE_WAIT_TIMEOUT_SECONDS = 900
MAX_BUSY_RETRIES = 30
MAX_BUSY_RETRY_INTERVAL_SECONDS = 60.0
MAX_RATE_LIMIT_RETRIES = 5
MAX_RATE_LIMIT_RETRY_INTERVAL_SECONDS = 300.0
MAX_GUEST_RETRIES = 10
MAX_REQUEST_DEADLINE_SECONDS = 1800
DEFAULT_REQUEST_DEADLINE_SECONDS = 300.0
MAX_STREAM_ERROR_RETRIES = 5
MAX_STREAM_ERROR_RETRY_INTERVAL_SECONDS = 60.0
MAX_BLOCKED_TOOL_FOLLOW_UPS = 5
MAX_HISTORY_MAX_CHARS = 5_000_000
MAX_EMPTY_RESPONSE_RETRIES = 5
BUILTIN_EXPOSED_MODELS = (
    "cogView-4-250304",
    "glm-5.3",
    "glm-5.2",
    "glm-5.1",
    "glm-5v-turbo",
    "glm-5-turbo",
    "glm-5",
    "glm-4.7-flash",
    "glm-4.7",
    "glm-4.6v-flash",
    "glm-4.6",
    "glm-4.5",
    "glm-4.1v-thinking-flashx",
    "glm-4",
    "glm-4-flash",
    "glm-4-air",
    "glm-4v",
    "glm-4-flashx-250414",
    "glm-4-flash-250414",
    "glm-zero-preview",
    "glm-deep-research",
    DEFAULT_IMAGE_MODEL_NAME,
)
MODEL_VARIANT_EXCLUDED_MODELS = {
    "cogView-4-250304",
    DEFAULT_IMAGE_MODEL_NAME,
}


class ConfigError(ValueError):
    pass


def parse_dotenv(path: Path, logger: logging.Logger | None = None) -> dict[str, str]:
    """Liest eine `.env`. Der LETZTE Eintrag eines Keys gewinnt.

    Ein doppelter Key war still: gemessen am 2026-09-26 hat eine leere
    zweite `GLM_REFRESH_TOKEN=` die echte aus Zeile 63 verdraengt, und der
    Dienst startete nicht mehr („kein ChatGLM-Konto konfiguriert"). Genau
    die Fehlerklasse, die hier teuer ist: die datei sieht korrekt aus, der
    wert ist weg. Deshalb wird ein doppelter Key mit abweichendem Wert
    gemeldet — inklusive Zeilennummern und ohne den Wert zu nennen (das
    haette hier den refresh-token in das log geschrieben).
    """
    values: dict[str, str] = {}
    first_line: dict[str, int] = {}
    if not path.exists():
        return values

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Config file is not valid UTF-8 encoded: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read config file: {path} error={exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        value = raw_value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        key = key.strip()
        if key in values and values[key] != value and logger is not None:
            logger.warning(
                "Duplicate key %r in %s (line %d is overwritten by line %d); "
                "the LAST value wins",
                key,
                path.name,
                first_line[key],
                line_number,
            )
        values[key] = value
        first_line.setdefault(key, line_number)
    return values


def parse_bool(
    value: str | None,
    default: bool = False,
    *,
    name: str = "value",
    logger: logging.Logger | None = None,
) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    if logger is not None:
        logger.warning(
            "Invalid boolean config value %s=%r; using safe default %s",
            name,
            value,
            default,
        )
    return default


def parse_int(
    value: str | None,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    name: str = "value",
    logger: logging.Logger | None = None,
) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        if logger is not None:
            logger.warning(
                "Invalid integer config value %s=%r; using safe default %s",
                name,
                value,
                default,
            )
            return default
        raise ConfigError(f"Invalid integer config value: {value}") from exc
    if (minimum is not None and parsed < minimum) or (maximum is not None and parsed > maximum):
        if logger is not None:
            logger.warning(
                "Integer config value out of range %s=%r; using safe default %s",
                name,
                value,
                default,
            )
            return default
        raise ConfigError(
            f"Integer config value out of range {name}={value}; expected {minimum}..{maximum}"
        )
    return parsed


def parse_float(
    value: str | None,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    name: str = "value",
    logger: logging.Logger | None = None,
) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        if logger is not None:
            logger.warning(
                "Invalid float config value %s=%r; using safe default %s",
                name,
                value,
                default,
            )
            return default
        raise ConfigError(f"Invalid float config value: {value}") from exc
    if not math.isfinite(parsed):
        if logger is not None:
            logger.warning(
                "Non-finite float config value %s=%r; using safe default %s",
                name,
                value,
                default,
            )
            return default
        raise ConfigError(f"Float config value must be finite: {value}")
    if (minimum is not None and parsed < minimum) or (maximum is not None and parsed > maximum):
        if logger is not None:
            logger.warning(
                "Float config value out of range %s=%r; using safe default %s",
                name,
                value,
                default,
            )
            return default
        raise ConfigError(
            f"Float config value out of range {name}={value}; expected {minimum}..{maximum}"
        )
    return parsed


def parse_list(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    if value is None or value.strip() == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    return normalized in {"127.0.0.1", "localhost", "::1"}


def _first_config_value(values: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in values:
            return values[name]
    return None


def _config_int(
    values: dict[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
    logger: logging.Logger,
    aliases: tuple[str, ...] = (),
) -> int:
    value = _first_config_value(values, name, *aliases)
    return parse_int(
        value,
        default,
        minimum=minimum,
        maximum=maximum,
        name=name,
        logger=logger,
    )


def _config_float(
    values: dict[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
    logger: logging.Logger,
    aliases: tuple[str, ...] = (),
) -> float:
    value = _first_config_value(values, name, *aliases)
    return parse_float(
        value,
        default,
        minimum=minimum,
        maximum=maximum,
        name=name,
        logger=logger,
    )


def load_refresh_tokens(token_file_path: Path) -> list[str]:
    if not token_file_path.exists():
        return []
    tokens: list[str] = []
    try:
        lines = token_file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Token file is not valid UTF-8 encoded: {token_file_path}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read token file: {token_file_path} error={exc}") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens.append(line)
    return tokens


def is_guest_token_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"guest", "guest_ck", "guest-ck", "visitor", "tourist", "游客", GUEST_REFRESH_TOKEN_MARKER}


@dataclass(slots=True)
class AppConfig:
    env_file_path: Path
    env_file_created: bool
    token_file_path: Path
    host: str
    port: int
    api_prefix: str
    log_level: str
    debug_dump_all: bool
    request_timeout: int
    request_socket_timeout: float
    max_request_body_bytes: int
    max_request_line: int
    max_headers: int
    max_header_bytes: int
    max_connections: int
    request_queue_size: int
    glm_base_url: str
    glm_use_guest_refresh_token: bool
    glm_refresh_token: str
    glm_refresh_tokens: list[str]
    glm_assistant_id: str
    glm_image_assistant_id: str
    glm_image_model_name: str
    glm_user_agent: str
    glm_delete_conversation: bool
    glm_persistent_conversation: bool
    glm_conversation_file: Path
    glm_conversation_id: str
    glm_max_concurrency: int
    glm_queue_wait_timeout: int
    glm_busy_max_retries: int
    glm_busy_retry_interval: float
    # F-6: eigener, KURZER budget fuer echte upstream-drosselung
    # (code 10061 "请求过于频繁"). Busy (nebenlauf) braucht viele kurze
    # versuche, ein ratelimit braucht wenige lange.
    glm_rate_limit_max_retries: int
    glm_rate_limit_retry_interval: float
    glm_guest_max_retries: int
    glm_stream_error_max_retries: int
    glm_stream_error_retry_interval: float
    glm_max_output_tokens: int
    # S-14: gesamt-deadline einer requestlaufzeit (0 = aus)
    glm_request_deadline_seconds: float
    glm_blocked_tool_follow_ups: int
    glm_history_max_chars: int
    glm_empty_response_max_retries: int
    blocked_tool_names: list[str]
    exposed_models: list[str]
    server_api_keys: list[str]
    cors_allow_origin: str
    log_dir: str
    log_max_bytes: int
    log_backup_count: int

    @property
    def refresh_url(self) -> str:
        return f"{self.glm_base_url}/user-api/user/refresh"

    @property
    def guest_refresh_url(self) -> str:
        return f"{self.glm_base_url}/user-api/guest/access"

    @property
    def chat_stream_url(self) -> str:
        return f"{self.glm_base_url}/backend-api/assistant/stream"

    @property
    def delete_conversation_url(self) -> str:
        return f"{self.glm_base_url}/backend-api/assistant/conversation/delete"


def ensure_env_file(env_path: Path) -> bool:
    if env_path.exists():
        return False

    example_candidates = [
        env_path.with_name(".env.example"),
        env_path.parent / ".env.example",
    ]
    example_path = next((candidate for candidate in example_candidates if candidate.exists()), None)
    if example_path is None:
        return False

    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example_path, env_path)
    except OSError as exc:
        raise ConfigError(f"Failed to auto-create config file: source={example_path} target={env_path} error={exc}") from exc
    return True


# S-15: unbekannte config-keys wurden vollstaendig lautlos verworfen.
# Ein tippfehler wie `CORS_ALLOW_ORIGINS` (statt `CORS_ALLOW_ORIGIN`) oder
# `SERVER_API_KEY` (statt `SERVER_API_KEYS`) sah aus wie eine konfiguration —
# und war keine. Im CORS-fall war das die genaue umkehrung der beabsichtigten
# absicherung: wer eine beschraenkung eintragen wollte, bekam `*`.
# Es wird nicht jeder unbekannte key gemeldet (das wuerde bei jedem
# request-verzeichnis verrauschen), sondern nur NAHBEIRRUNGEN: der key ist einem bekannten so
# aehnlich, dass ein tippfehler die naheliegendste erklaerung ist.
_CONFIG_KEY_NEAR_MISSES = (
    # (bekannter key, schweregrad) — schweregrad steuert die deutlichkeit
    ("CORS_ALLOW_ORIGIN", "security"),
    ("SERVER_API_KEYS", "security"),
    ("GLM_REFRESH_TOKEN", "security"),
    ("GLM_USE_GUEST_REFRESH_TOKEN", "security"),
    ("GLM_ASSISTANT_ID", "security"),
    # GUELTIGE keys, die dennoch als nahbeirrung auffallen. Geprueft
    # 2026-09-26: `GLM_IMAGE_ASSISTANT_ID` wurde faelschlich als tippfehler
    # von `GLM_ASSISTANT_ID` gemeldet, obwohl der key gueltig ist — eine
    # sicherheitswarnung, die immer brennt, wird ignoriert.
    ("GLM_IMAGE_ASSISTANT_ID", "security"),
    ("GLM_MAX_CONCURRENCY", "behavior"),
    ("GLM_MAX_OUTPUT_TOKENS", "behavior"),
    ("GLM_REQUEST_DEADLINE_SECONDS", "behavior"),
    # 2026-09-26: `REQUEST_TIMEOUT` und `REQUEST_SOCKET_TIMEOUT` (die
    # kurzformen ohne `_SECONDS`) wurden in allen drei ausgelieferten
    # .env mitgefuehrt und wirkten NIE — und wurden dabei nicht einmal
    # gemeldet, weil sie nicht in dieser liste standen. Sie hatten zudem
    # exakt den standardwert, deshalb fiel der unterschied nie auf.
    ("REQUEST_TIMEOUT_SECONDS", "behavior"),
    ("REQUEST_SOCKET_TIMEOUT_SECONDS", "behavior"),
    ("GLM_QUEUE_WAIT_TIMEOUT_SECONDS", "behavior"),
    ("GLM_BUSY_RETRY_INTERVAL_SECONDS", "behavior"),
    ("GLM_RATE_LIMIT_MAX_RETRIES", "behavior"),
    ("GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS", "behavior"),
    ("GLM_BLOCKED_TOOL_FOLLOW_UPS", "behavior"),
    ("GLM_DELETE_CONVERSATION", "behavior"),
    ("LOG_LEVEL", "behavior"),
    ("PORT", "behavior"),
    ("HOST", "behavior"),
)


# 2026-09-26: key-schreibweisen, die es GAB und die NICHT wirkten. Sie sind
# hier aufgeschluesselt, weil die unschaerfe (`get_close_matches`, cutoff
# 0.82) sie nicht faengt: `REQUEST_TIMEOUT` gegen
# `REQUEST_TIMEOUT_SECONDS` liegt bei 0.77 — ein echter tippfehler, aber
# fuer die unschaerfe zu weit weg. Beide standen so in ALLEN drei
# ausgelieferten .env und wurden stillschweigend ignoriert.
_CONFIG_KEY_KNOWN_TYPOS = {
    "REQUEST_TIMEOUT": "REQUEST_TIMEOUT_SECONDS",
    "REQUEST_SOCKET_TIMEOUT": "REQUEST_SOCKET_TIMEOUT_SECONDS",
    "GLM_REFRESH_TOKENS": "GLM_REFRESH_TOKEN",
    "GLM_QUEUE_WAIT_TIMEOUT": "GLM_QUEUE_WAIT_TIMEOUT_SECONDS",
}


def _report_unknown_key(stripped: str, known: str, severity: str, logger: logging.Logger) -> None:
    """Einmal die Meldung — zwei Wege (exakte Tot-Schreibweise, unscharfer
    Nahbeirtung) sollen sich nicht in der Wortlautpflege duplizieren."""
    message = (
        f"Unknown config key {stripped!r} is IGNORED (did you mean {known!r}?). "
        f"The setting has NO effect."
    )
    if severity == "security":
        logger.error("SECURITY: %s", message)
    else:
        logger.warning("%s", message)


def _warn_unknown_config_keys(values: dict[str, str], logger: logging.Logger) -> None:
    """S-15: unbekannte keys mit geringer edit-distanz melden.

    Absichtlich konservativ: nur keys, die einem bekannten aehnlich sind.
    Wer `FOO_BAR=1` mitbringt, wird nicht beledigt; wer
    `CORS_ALLOW_ORIGINS` tippt, schon — denn dort ist der
    stillschweigende fallback die falsche Richtung."""
    for key in sorted(values):
        stripped = key.strip().upper()
        if not stripped:
            continue
        # Reihenfolge unabhaengig (geprueft 2026-09-26): ZUERST gegen alle
        # bekannten namen auf exakte uebereinstimmung pruefen, nur wenn
        # keiner passt, auf aehnlichkeit. Vorher gewann der erste treffer —
        # `GLM_IMAGE_ASSISTANT_ID` kollidiert als praefix mit
        # `GLM_ASSISTANT_ID` und wurde deshalb faelschlich als tippfehler
        # gemeldet, obwohl der key gueltig ist. Eine sicherheitswarnung,
        # die immer brennt, wird vom betreiber ignoriert.
        for known, _severity in _CONFIG_KEY_NEAR_MISSES:
            if stripped == known:
                break
        else:
            # bekannte tot-schreibweisen zuerst, exakt und ohne
            # unschaerfe — die liegt bei einem praefix-key im prinzip nie
            # nah genug am echten key
            known_typo = _CONFIG_KEY_KNOWN_TYPOS.get(stripped)
            if known_typo is not None:
                _report_unknown_key(stripped, known_typo, "security", logger)
                continue
            for known, severity in _CONFIG_KEY_NEAR_MISSES:
                if not difflib.get_close_matches(stripped, [known], n=1, cutoff=0.82):
                    continue
                _report_unknown_key(stripped, known, severity, logger)
                break


def _resolve_env_file(env_file: str) -> Path:
    """S-13: `.env` war ein RELATIVER pfad.

    Ein direkter start aus einem anderen verzeichnis lud damit eine
    falsche konfiguration — oder legte ungefragt eine neue `.env` dort
    an, weil `ensure_env_file()` sie dort erzeugte. Ohne die
    betriebsdatei lief der dienst zudem auf dem code-default, waehrend
    agent und supervisor auf 8001 warteten.

    Reihenfolge: expliziter pfad (absolut oder mit pfadanteil) bleibt
    unveraendert; ein reiner dateiname wird zuerst im
    arbeitsverzeichnis, dann neben dem paket gesucht. `.env.example`
    wandert fuer die erzeugung mit.
    """
    given = Path(env_file)
    if given.is_absolute() or given.parent != Path("."):
        return given
    if given.exists():
        return given
    # neben dem paket / repo-wurzel suchen
    package_root = Path(__file__).resolve().parent
    for anchor in (package_root, package_root.parent, package_root.parent.parent):
        candidate = anchor / given.name
        if candidate.exists():
            return candidate
    return given


def load_config(env_file: str = ".env") -> AppConfig:
    # Basis-Logging vorab konfigurieren: load_config laeuft VOR
    # Application.__init__ (setup_logging) — ohne Handler laufen die
    # INFO-Logs hier ins lastResort-Nirvana. Ein einfacher Stream-Handler
    # reicht; das volle Setup (Level, Formatter, Datei) macht app.py danach.
    _logger = logging.getLogger("glm2api")
    if not _logger.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(_handler)
        _logger.setLevel(logging.INFO)
    logger = logging.getLogger("glm2api.config")
    env_path = _resolve_env_file(env_file)
    env_file_created = ensure_env_file(env_path)
    file_values = parse_dotenv(env_path, logger)
    values = {**file_values, **os.environ}
    _warn_unknown_config_keys(values, logger)

    glm_max_concurrency = _config_int(
        values,
        "GLM_MAX_CONCURRENCY",
        3,
        1,
        MAX_CONCURRENCY_LIMIT,
        logger,
    )
    token_file_path = Path(values.get("GLM_TOKEN_FILE", "token.txt"))
    if not token_file_path.is_absolute():
        token_file_path = (env_path.parent / token_file_path).resolve()

    refresh_tokens = load_refresh_tokens(token_file_path)
    single_refresh_token = values.get("GLM_REFRESH_TOKEN", "").strip()
    explicit_guest_mode = parse_bool(
        values.get("GLM_USE_GUEST_REFRESH_TOKEN"),
        False,
        name="GLM_USE_GUEST_REFRESH_TOKEN",
        logger=logger,
    ) or is_guest_token_value(single_refresh_token)

    if explicit_guest_mode:
        # Gastmodus ist ausschliesslich eine ausdrueckliche Wahl. Das
        # Gastkonto ist limitiert und fuer den Agentenbetrieb nicht
        # brauchbar — ein stilles Mitlaufen ist schlimmer als ein Fehler.
        refresh_tokens = [GUEST_REFRESH_TOKEN_MARKER] * glm_max_concurrency
        single_refresh_token = GUEST_REFRESH_TOKEN_MARKER
        if not is_guest_token_value(single_refresh_token) and logger:
            logger.warning(
                "GLM_USE_GUEST_REFRESH_TOKEN is set: running on the guest account "
                "(limited, not usable for agent runs)"
            )
    else:
        # Kein impliziter Gast-Slot. Entweder ein echtes Konto, oder der
        # Start schlaegt mit einer klaren Anweisung fehl.
        refresh_tokens = [token for token in refresh_tokens if token]
        if single_refresh_token and not refresh_tokens:
            refresh_tokens = [single_refresh_token]
        if not refresh_tokens or all(is_guest_token_value(token) for token in refresh_tokens):
            raise SystemExit(
                "glm2api: kein ChatGLM-Konto konfiguriert.\n"
                "  Setze GLM_REFRESH_TOKEN in .env (oder hinterlege token.txt),\n"
                "  oder starte bewusst im Gastmodus: GLM_USE_GUEST_REFRESH_TOKEN=true\n"
                "  Der Gastmodus ist limitiert und fuer Agentenlaeufe nicht brauchbar."
            )

    persistent_conv = parse_bool(
        values.get("GLM_PERSISTENT_CONVERSATION"),
        False,
        name="GLM_PERSISTENT_CONVERSATION",
        logger=logger,
    )
    conversation_file = Path(values.get("GLM_CONVERSATION_FILE", "conversation.txt"))
    if not conversation_file.is_absolute():
        conversation_file = (env_path.parent / conversation_file).resolve()
    conv_id = values.get("GLM_CONVERSATION_ID", "").strip()
    if persistent_conv and not conv_id and conversation_file.exists():
        try:
            stored = conversation_file.read_text(encoding="utf-8").strip()
            if stored and len(stored) == 24 and all(c in "0123456789abcdefABCDEF" for c in stored):
                conv_id = stored
        except Exception:
            pass

    host = values.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    api_prefix = values.get("API_PREFIX", "/v1").strip()
    if not api_prefix:
        api_prefix = "/v1"
    if not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/") or "/v1"
    log_level = values.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    debug_dump_all = parse_bool(
        values.get("DEBUG_DUMP_ALL"),
        False,
        name="DEBUG_DUMP_ALL",
        logger=logger,
    )
    if debug_dump_all:
        log_level = "DEBUG"
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        logger.warning("Invalid LOG_LEVEL=%r; using safe default INFO", values.get("LOG_LEVEL"))
        log_level = "INFO"
    image_model_name = values.get("GLM_IMAGE_MODEL_NAME", DEFAULT_IMAGE_MODEL_NAME).strip() or DEFAULT_IMAGE_MODEL_NAME
    exposed_models = expand_model_variants(
        BUILTIN_EXPOSED_MODELS,
        excluded_models=MODEL_VARIANT_EXCLUDED_MODELS,
    )

    request_socket_timeout = _config_float(
        values,
        "REQUEST_SOCKET_TIMEOUT_SECONDS",
        DEFAULT_REQUEST_SOCKET_TIMEOUT_SECONDS,
        0.1,
        MAX_REQUEST_SOCKET_TIMEOUT_SECONDS,
        logger,
        aliases=("HTTP_SOCKET_TIMEOUT_SECONDS", "CLIENT_SOCKET_TIMEOUT_SECONDS", "SOCKET_TIMEOUT_SECONDS"),
    )
    max_request_body_bytes = _config_int(
        values,
        "MAX_REQUEST_BODY_BYTES",
        DEFAULT_MAX_REQUEST_BODY_BYTES,
        1,
        MAX_REQUEST_BODY_BYTES_LIMIT,
        logger,
        aliases=("MAX_BODY_BYTES", "MAX_REQUEST_BODY_SIZE_BYTES"),
    )
    max_request_line = _config_int(
        values,
        "MAX_REQUEST_LINE_BYTES",
        DEFAULT_MAX_REQUEST_LINE_BYTES,
        1,
        MAX_REQUEST_LINE_BYTES_LIMIT,
        logger,
        aliases=("MAX_REQUEST_LINE",),
    )
    max_headers = _config_int(
        values,
        "MAX_HEADERS",
        DEFAULT_MAX_HEADERS,
        1,
        MAX_HEADERS_LIMIT,
        logger,
    )
    max_header_bytes = _config_int(
        values,
        "MAX_HEADER_BYTES",
        DEFAULT_MAX_HEADER_BYTES,
        1,
        MAX_HEADER_BYTES_LIMIT,
        logger,
    )
    max_connections = _config_int(
        values,
        "MAX_CONNECTIONS",
        DEFAULT_MAX_CONNECTIONS,
        1,
        MAX_CONNECTIONS_LIMIT,
        logger,
        aliases=("MAX_CONCURRENT_CONNECTIONS", "MAX_HTTP_CONNECTIONS"),
    )
    request_queue_size = _config_int(
        values,
        "REQUEST_QUEUE_SIZE",
        DEFAULT_REQUEST_QUEUE_SIZE,
        1,
        MAX_REQUEST_QUEUE_SIZE_LIMIT,
        logger,
    )
    # S-13: der betrieb laeuft auf 8001 (infrastructure.md, infra/scripts/glm2api.sh,
    # openode-provider). Der default 8000 trieb code, .env.example und
    # betrieb auseinander — ein frischer clone haette auf 8000 gehoert und
    # damit jeden client und jedes script gebrochen.
    port = _config_int(values, "PORT", 8001, 1, 65535, logger)
    # D-11: diese drei standen vorher nur in `logging_utils` und wurden
    # direkt aus os.environ gelesen. `load_config()` exportiert die .env
    # aber nicht in die umgebung — ein in der datei gesetzter wert war
    # damit still unwirksam.
    log_dir = _first_config_value(values, "GLM2API_LOG_DIR") or "log"
    log_max_bytes = _config_int(
        values, "GLM2API_LOG_MAX_BYTES", 100 * 1024 * 1024, 1024 * 1024, 2 * 1024**3, logger
    )
    log_backup_count = _config_int(values, "GLM2API_LOG_BACKUP_COUNT", 3, 1, 20, logger)
    request_timeout = _config_int(
        values,
        "REQUEST_TIMEOUT_SECONDS",
        120,
        1,
        MAX_REQUEST_TIMEOUT_SECONDS,
        logger,
    )
    glm_queue_wait_timeout = _config_int(
        values,
        "GLM_QUEUE_WAIT_TIMEOUT_SECONDS",
        600,
        1,
        MAX_QUEUE_WAIT_TIMEOUT_SECONDS,
        logger,
    )
    glm_busy_max_retries = _config_int(
        values,
        "GLM_BUSY_MAX_RETRIES",
        30,
        0,
        MAX_BUSY_RETRIES,
        logger,
    )
    glm_busy_retry_interval = _config_float(
        values,
        "GLM_BUSY_RETRY_INTERVAL_SECONDS",
        2.0,
        0.0,
        MAX_BUSY_RETRY_INTERVAL_SECONDS,
        logger,
    )
    # F-6: getrenntes budget fuer die echte konto-drosselung. Der 429/code
    # 10061 mit "请求过于频繁" ist kein nebenlauf-busy: er klingt in
    # minuten ab, nicht in sekunden. Mit dem busy-profil (30 versuche,
    # basis 2s) feuerte der proxy bis zu 30 requests in ~4 minuten auf ein
    # bereits gedrosseltes konto und verstaerkte die sperre. Zwei versuche
    # im abstand von 30s/60s geben kurzzeitige throttles zeit, ohne zu
    # hauen; danach geht ein sauberer 429 an den client.
    glm_rate_limit_max_retries = _config_int(
        values,
        "GLM_RATE_LIMIT_MAX_RETRIES",
        2,
        0,
        MAX_RATE_LIMIT_RETRIES,
        logger,
    )
    glm_rate_limit_retry_interval = _config_float(
        values,
        "GLM_RATE_LIMIT_RETRY_INTERVAL_SECONDS",
        30.0,
        0.0,
        MAX_RATE_LIMIT_RETRY_INTERVAL_SECONDS,
        logger,
    )
    glm_guest_max_retries = _config_int(
        values,
        "GLM_GUEST_MAX_RETRIES",
        3,
        0,
        MAX_GUEST_RETRIES,
        logger,
    )
    glm_stream_error_max_retries = _config_int(
        values,
        "GLM_STREAM_ERROR_MAX_RETRIES",
        2,
        0,
        MAX_STREAM_ERROR_RETRIES,
        logger,
    )
    # S-14: ein requestweises GESAMT-deadline. Die einzelnen zaehler
    # (stream-retry, leer-retry, busy-retry, blocked-follow-up) sind je
    # request begrenzt, ihre summe nicht: ein request mit vielen
    # transienten runden konnte einen slot minutenlang belegen und die
    # queue aufhalten. 0 = aus (verhalten wie bisher).
    glm_request_deadline_seconds = _config_float(
        values,
        "GLM_REQUEST_DEADLINE_SECONDS",
        DEFAULT_REQUEST_DEADLINE_SECONDS,
        0,
        MAX_REQUEST_DEADLINE_SECONDS,
        logger,
    )
    glm_stream_error_retry_interval = _config_float(
        values,
        "GLM_STREAM_ERROR_RETRY_INTERVAL_SECONDS",
        1.0,
        0.0,
        MAX_STREAM_ERROR_RETRY_INTERVAL_SECONDS,
        logger,
    )
    # Obergrenze fuer die erzeugte Antwort. Der upsteam (chatglm.cn)
    # kennt keine ausgabegrenze — ohne durchsetzung laeuft ein entarteter
    # turn endlos weiter (live-beobachtet: 30k zeichen / 24 calls).
    glm_max_output_tokens = _config_int(
        values,
        "GLM_MAX_OUTPUT_TOKENS",
        32768,
        1024,
        131072,
        logger,
    )
    glm_blocked_tool_follow_ups = _config_int(
        values,
        "GLM_BLOCKED_TOOL_FOLLOW_UPS",
        2,
        0,
        MAX_BLOCKED_TOOL_FOLLOW_UPS,
        logger,
    )
    glm_history_max_chars = _config_int(
        values,
        "GLM_HISTORY_MAX_CHARS",
        120000,
        0,
        MAX_HISTORY_MAX_CHARS,
        logger,
    )
    glm_empty_response_max_retries = _config_int(
        values,
        "GLM_EMPTY_RESPONSE_MAX_RETRIES",
        2,
        0,
        MAX_EMPTY_RESPONSE_RETRIES,
        logger,
    )
    server_api_keys = parse_list(values.get("SERVER_API_KEYS"))
    # S-02: der default war `*`. Damit durfte JEDE website im browser des
    # nutzers den loopback-dienst unter `http://127.0.0.1:8001` ansprechen
    # und die antworten lesen — der `Host`-header ist dabei `127.0.0.1`, der
    # rebinding-guard greift also nicht, und genau der wildcard erlaubt das
    # lesen. Der dienst ist eine API fuer cli-clients (opencode, curl);
    # browserzugriff ist kein feature, sondern nur ein loch. Default ist
    # deshalb KEIN cors. Wer ihn wirklich braucht, setzt ihn ausdruecklich.
    cors_allow_origin = values.get("CORS_ALLOW_ORIGIN", "").strip()
    glm_base_url = values.get("GLM_BASE_URL", DEFAULT_GLM_BASE_URL).rstrip("/")

    config = AppConfig(
        env_file_path=env_path,
        env_file_created=env_file_created,
        token_file_path=token_file_path,
        host=host,
        port=port,
        api_prefix=api_prefix,
        log_level=log_level,
        debug_dump_all=debug_dump_all,
        request_timeout=request_timeout,
        request_socket_timeout=request_socket_timeout,
        max_request_body_bytes=max_request_body_bytes,
        max_request_line=max_request_line,
        max_headers=max_headers,
        max_header_bytes=max_header_bytes,
        max_connections=max_connections,
        request_queue_size=request_queue_size,
        glm_base_url=glm_base_url,
        glm_use_guest_refresh_token=explicit_guest_mode,
        glm_refresh_token=single_refresh_token,
        glm_refresh_tokens=refresh_tokens,
        glm_assistant_id=values.get("GLM_ASSISTANT_ID", DEFAULT_ASSISTANT_ID).strip(),
        glm_image_assistant_id=values.get("GLM_IMAGE_ASSISTANT_ID", DEFAULT_IMAGE_ASSISTANT_ID).strip(),
        glm_image_model_name=image_model_name,
        glm_user_agent=values.get(
            "GLM_USER_AGENT",
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
            ),
        ).strip(),
        glm_delete_conversation=parse_bool(
            values.get("GLM_DELETE_CONVERSATION"),
            True,
            name="GLM_DELETE_CONVERSATION",
            logger=logger,
        ),
        glm_persistent_conversation=persistent_conv,
        glm_conversation_file=conversation_file,
        glm_conversation_id=conv_id,
        glm_max_concurrency=glm_max_concurrency,
        glm_queue_wait_timeout=glm_queue_wait_timeout,
        glm_busy_max_retries=glm_busy_max_retries,
        glm_busy_retry_interval=glm_busy_retry_interval,
        glm_rate_limit_max_retries=glm_rate_limit_max_retries,
        glm_rate_limit_retry_interval=glm_rate_limit_retry_interval,
        glm_guest_max_retries=glm_guest_max_retries,
        glm_stream_error_max_retries=glm_stream_error_max_retries,
        glm_stream_error_retry_interval=glm_stream_error_retry_interval,
        glm_max_output_tokens=glm_max_output_tokens,
        glm_request_deadline_seconds=glm_request_deadline_seconds,
        glm_blocked_tool_follow_ups=glm_blocked_tool_follow_ups,
        glm_history_max_chars=glm_history_max_chars,
        glm_empty_response_max_retries=glm_empty_response_max_retries,
        blocked_tool_names=parse_list(values.get("BLOCKED_TOOL_NAMES"), DEFAULT_BLOCKED_TOOL_NAMES),
        exposed_models=exposed_models,
        server_api_keys=server_api_keys,
        cors_allow_origin=cors_allow_origin,
        log_dir=log_dir,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
    )

    if not (1 <= config.port <= 65535):
        raise ConfigError(f"Port config out of range: PORT={config.port}")
    if config.request_timeout <= 0:
        raise ConfigError(f"Request timeout must be greater than 0: REQUEST_TIMEOUT_SECONDS={config.request_timeout}")
    if config.request_socket_timeout <= 0:
        raise ConfigError(
            "Request socket timeout must be greater than 0: "
            f"REQUEST_SOCKET_TIMEOUT_SECONDS={config.request_socket_timeout}"
        )
    if config.max_request_body_bytes <= 0:
        raise ConfigError("MAX_REQUEST_BODY_BYTES must be greater than 0")
    if config.max_request_line <= 0 or config.max_headers <= 0 or config.max_header_bytes <= 0:
        raise ConfigError("HTTP request line and header limits must be greater than 0")
    if config.max_connections <= 0 or config.request_queue_size <= 0:
        raise ConfigError("HTTP connection and queue limits must be greater than 0")
    if config.glm_queue_wait_timeout <= 0:
        raise ConfigError(f"Queue wait timeout must be greater than 0: GLM_QUEUE_WAIT_TIMEOUT_SECONDS={config.glm_queue_wait_timeout}")
    if config.glm_busy_retry_interval < 0:
        raise ConfigError(f"Busy retry interval cannot be less than 0: GLM_BUSY_RETRY_INTERVAL_SECONDS={config.glm_busy_retry_interval}")

    if not is_loopback_host(config.host):
        if not config.server_api_keys:
            raise ConfigError(
                "SERVER_API_KEYS must be configured when HOST is not loopback "
                f"(HOST={config.host})"
            )
        if config.cors_allow_origin == "*":
            raise ConfigError(
                "CORS_ALLOW_ORIGIN=* is only allowed for loopback bindings "
                f"(HOST={config.host})"
            )

    try:
        parsed_base_url = urlsplit(config.glm_base_url)
        base_host = parsed_base_url.hostname or ""
        parsed_base_url.port
    except ValueError as exc:
        raise ConfigError(f"GLM_BASE_URL is invalid: {config.glm_base_url}") from exc
    base_scheme = parsed_base_url.scheme.lower()
    if base_scheme not in {"http", "https"} or not base_host:
        raise ConfigError(
            f"GLM_BASE_URL must be an absolute http(s) URL: {config.glm_base_url}"
        )
    if base_scheme == "http" and not is_loopback_host(base_host):
        raise ConfigError(
            "GLM_BASE_URL may use http only for loopback hosts "
            f"(configured host={base_host})"
        )
    if parsed_base_url.username or parsed_base_url.password:
        raise ConfigError("GLM_BASE_URL must not contain embedded credentials")

    token_source = "guest mode" if explicit_guest_mode else (f"token file ({token_file_path})" if token_file_path.exists() else ".env GLM_REFRESH_TOKEN")
    logger.info(
        "Configuration loaded port=%s concurrency=%s accounts=%s token_source=%s log_level=%s",
        config.port,
        config.glm_max_concurrency,
        len(config.glm_refresh_tokens),
        token_source,
        config.log_level,
    )
    logger.debug(
        "Config details host=%s api_prefix=%s timeout=%ss delete_conversation=%s exposed_models=%s",
        config.host,
        config.api_prefix,
        config.request_timeout,
        config.glm_delete_conversation,
        len(config.exposed_models),
    )
    return config
