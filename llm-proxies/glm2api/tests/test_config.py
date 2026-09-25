import logging
import stat
from pathlib import Path

import pytest

from glm2api.config import ConfigError, GUEST_REFRESH_TOKEN_MARKER, load_config
from glm2api.logging_utils import serialize_for_debug, setup_logging


def test_single_refresh_token_does_not_add_guest_fallback(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_REFRESH_TOKEN=account-token\n"
        "GLM_USE_GUEST_REFRESH_TOKEN=false\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GLM_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("GLM_USE_GUEST_REFRESH_TOKEN", raising=False)

    config = load_config(env_path)

    # Kein impliziter Gast-Slot: das Gastkonto ist limitiert und fuer
    # Agentenlaeufe nicht brauchbar (Nutzerentscheidung 2026-09-25).
    assert config.glm_refresh_tokens == ["account-token"]
    assert config.glm_refresh_token == "account-token"
    assert config.glm_use_guest_refresh_token is False
    assert config.glm_persistent_conversation is False
    assert config.glm_delete_conversation is True


def test_persistent_conversation_flag(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_USE_GUEST_REFRESH_TOKEN=true\n"
        "GLM_PERSISTENT_CONVERSATION=true\n"
        "GLM_DELETE_CONVERSATION=false\n",
        encoding="utf-8",
    )
    config = load_config(env_path)
    assert config.glm_persistent_conversation is True
    assert config.glm_delete_conversation is False


def test_setup_logging_removes_load_config_bootstrap_handler(tmp_path):
    """Regression: load_config() legt einen Handler auf den 'glm2api'-Logger,
    den setup_logging() nicht entfernte — dadurch wurde jede logzeile doppelt
    ausgegeben (einmal plain via glm2api-handler, einmal via root-handler)."""
    glm_logger = logging.getLogger("glm2api")
    env_path = tmp_path / ".env"
    env_path.write_text("GLM_USE_GUEST_REFRESH_TOKEN=true\n", encoding="utf-8")

    config = load_config(env_path)
    assert glm_logger.handlers, "load_config sollte den bootstrap-handler setzen"

    setup_logging("INFO")
    assert glm_logger.handlers == []
    assert len(logging.getLogger().handlers) == 1


def _clear_security_environment(monkeypatch):
    for name in (
        "HOST",
        "PORT",
        "CORS_ALLOW_ORIGIN",
        "SERVER_API_KEYS",
        "GLM_BASE_URL",
        "GLM_MAX_CONCURRENCY",
        "GLM_BUSY_RETRY_INTERVAL_SECONDS",
        "REQUEST_TIMEOUT_SECONDS",
        "MAX_REQUEST_BODY_BYTES",
        "MAX_REQUEST_LINE_BYTES",
        "MAX_HEADERS",
        "MAX_HEADER_BYTES",
        "MAX_CONNECTIONS",
        "REQUEST_QUEUE_SIZE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_non_loopback_binding_requires_api_keys(tmp_path, monkeypatch):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HOST=0.0.0.0\nCORS_ALLOW_ORIGIN=https://app.example\nGLM_REFRESH_TOKEN=acct-token\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="SERVER_API_KEYS"):
        load_config(env_path)


def test_non_loopback_binding_rejects_wildcard_cors(tmp_path, monkeypatch):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HOST=0.0.0.0\nSERVER_API_KEYS=local-key\nCORS_ALLOW_ORIGIN=*\n"
        "GLM_REFRESH_TOKEN=acct-token\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="CORS_ALLOW_ORIGIN"):
        load_config(env_path)


def test_http_upstream_is_limited_to_loopback_hosts(tmp_path, monkeypatch):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_BASE_URL=http://example.com/chatglm\nGLM_REFRESH_TOKEN=acct-token\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="loopback"):
        load_config(env_path)


def test_invalid_numeric_values_use_safe_defaults_and_warn(tmp_path, monkeypatch, caplog):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_MAX_CONCURRENCY=abc\n"
        "GLM_BUSY_RETRY_INTERVAL_SECONDS=NaN\n"
        "GLM_REFRESH_TOKEN=acct-token\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="glm2api.config"):
        config = load_config(env_path)

    assert config.glm_max_concurrency == 3
    assert config.glm_busy_retry_interval == 2.0
    assert "GLM_MAX_CONCURRENCY" in caplog.text
    assert "GLM_BUSY_RETRY_INTERVAL_SECONDS" in caplog.text


def test_request_limits_are_loaded_and_capped(tmp_path, monkeypatch):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MAX_REQUEST_BODY_BYTES=1048576\n"
        "MAX_REQUEST_LINE_BYTES=4096\n"
        "MAX_HEADERS=32\n"
        "MAX_HEADER_BYTES=32768\n"
        "MAX_CONNECTIONS=16\n"
        "REQUEST_QUEUE_SIZE=8\n"
        "GLM_REFRESH_TOKEN=acct-token\n",
        encoding="utf-8",
    )

    config = load_config(env_path)

    assert config.max_request_body_bytes == 1048576
    assert config.max_request_line == 4096
    assert config.max_headers == 32
    assert config.max_header_bytes == 32768
    assert config.max_connections == 16
    assert config.request_queue_size == 8


def test_empty_cors_value_does_not_become_wildcard(tmp_path, monkeypatch):
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("CORS_ALLOW_ORIGIN=\nGLM_REFRESH_TOKEN=acct-token\n", encoding="utf-8")

    config = load_config(env_path)

    assert config.cors_allow_origin == ""


def test_debug_header_dump_redacts_credentials():
    serialized = serialize_for_debug(
        {
            "Authorization": "Bearer secret",
            "x-api-key": "secret",
            "Cookie": "session=secret",
            "api-key": "secret",
            "safe": "value",
        }
    )

    assert "secret" not in serialized
    assert "[REDACTED]" in serialized
    assert "safe" in serialized


def test_debug_log_directory_and_file_are_private(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    # D-11: der pfad kommt als parameter aus der config, nicht mehr aus
    # os.environ — `load_config()` exportiert die .env namlich nicht in die
    # umgebung, ein dort gesetzter wert war damit still unwirksam.
    setup_logging("DEBUG", log_dir_name=str(log_dir))
    try:
        log_file = log_dir / "glm2api_debug.log"
        assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
        for handler in logging.getLogger().handlers:
            if hasattr(handler, "doRollover"):
                setattr(handler, "maxBytes", 1)
                getattr(handler, "doRollover")()
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in log_dir.glob("glm2api_debug.log*")
        )
    finally:
        for handler in list(logging.getLogger().handlers):
            close = getattr(handler, "close", None)
            if close is not None:
                close()
        setup_logging("INFO", log_dir_name="log")



def test_default_port_matches_the_documented_operational_port(tmp_path, monkeypatch):
    """S-13: code-default und `.env.example` sagten 8000, der Betrieb läuft
    auf 8001 (infrastructure.md, infra/scripts/glm2api.sh, opencode). Ein
    frischer Clone haette den proxy auf 8000 gestartet und damit jeden
    client und jedes betriebsscript gebrochen."""
    _clear_security_environment(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("GLM_REFRESH_TOKEN=acct-token\n", encoding="utf-8")

    assert load_config(env_path).port == 8001


def test_env_example_port_matches_code_default():
    """Der Beispiel-koern darf nicht vom code-default abweichen."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    port_lines = [
        line.strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("PORT=")
    ]

    assert port_lines == ["PORT=8001"]


def test_env_example_documents_every_operational_config_key():
    """D-11: 16 Betriebs-Keys der AppConfig fehlten in `.env.example` — sie
    waren nur implizit über die Standardwerte sichtbar.

    Geprüft werden die Keys, die `load_config` TATSÄCHLICH liest (nicht die
    Feldnamen des Dataclass — die weichen ab: `GLM_TOKEN_FILE` →
    `token_file_path`, `GLM_BUSY_RETRY_INTERVAL_SECONDS` →
    `glm_busy_retry_interval`). So bleibt der Test ohne Pflegeliste
    korrekt."""
    import inspect
    import pathlib
    import re

    import glm2api.config as config_module

    source = inspect.getsource(config_module)
    read_keys: set[str] = set()
    for match in re.finditer(
        r'(?:_config_int|_config_float|_config_bool|_config_str|_config_limit)\(\s*"([A-Z][A-Z0-9_]+)"', source
    ):
        read_keys.add(match.group(1))
    for match in re.finditer(r'values\.get\("([A-Z][A-Z0-9_]+)"', source):
        read_keys.add(match.group(1))
    # abgeleitete/sonstige schluessel, die bewusst nicht env-gesteuert sind
    not_env_keys = {"ENV_FILE_PATH", "ENV_FILE_CREATED", "LOG_LEVEL_FORMAT", "LOG_DATE_FORMAT", "LOG_STREAM_LOG_LEVEL"}
    read_keys -= not_env_keys

    example_text = (pathlib.Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    documented = {
        line.split("=", 1)[0].strip()
        for line in example_text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    missing = sorted(key for key in read_keys if key not in documented)

    assert not missing, f"in .env.example nicht dokumentiert: {missing}"


# --- S-15: stille tippfehler -------------------------------------------


@pytest.mark.parametrize("typo,expected", [
    ("CORS_ALLOW_ORIGINS", "CORS_ALLOW_ORIGIN"),
    ("SERVER_API_KEY", "SERVER_API_KEYS"),
    ("GLM_MAX_CONCURRANCY", "GLM_MAX_CONCURRENCY"),
    ("GLM_MAX_OUTPUT_TOKEN", "GLM_MAX_OUTPUT_TOKENS"),
])
def test_typo_config_keys_are_reported(tmp_path, monkeypatch, caplog, typo, expected):
    """S-15: `CORS_ALLOW_ORIGINS` statt `CORS_ALLOW_ORIGIN` sah aus wie
    eine absicherung und war keine — der stille fallback lieferte `*`,
    also genau die umkehrung der beabsichtigten schranke. Unbekannte
    keys mit geringer edit-distanz werden gemeldet."""
    import logging as _logging

    from glm2api.config import _warn_unknown_config_keys

    logger = _logging.getLogger("glm2api.config.test_typo")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        _warn_unknown_config_keys({typo: "x", "GLM_REFRESH_TOKEN": "t"}, logger)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert typo in messages
    assert expected in messages
    assert "NO effect" in messages


def test_unrelated_unknown_keys_stay_quiet(tmp_path, caplog):
    """Gegenprobe: beliebige extra-keys werden nicht gemeldet — sonst
    waere jeder startup verrauscht und die echte warnung verschaend."""
    import logging as _logging

    from glm2api.config import _warn_unknown_config_keys

    logger = _logging.getLogger("glm2api.config.test_quiet")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        _warn_unknown_config_keys({"FOO_BAR": "1", "MY_OWN_NOTE": "x"}, logger)

    assert caplog.records == []


def test_valid_keys_are_not_reported_as_typos(tmp_path, caplog):
    """Gegenprobe: die echten keys dürfen nicht als tippfehler
    gemeldet werden — sonst startet jeder normale betrieb mit drei
    'security'-warnungen."""
    import logging as _logging

    from glm2api.config import _warn_unknown_config_keys

    logger = _logging.getLogger("glm2api.config.test_valid")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        _warn_unknown_config_keys(
            {
                "CORS_ALLOW_ORIGIN": "*",
                "SERVER_API_KEYS": "sk-1",
                "GLM_MAX_CONCURRENCY": "3",
                "GLM_MAX_OUTPUT_TOKENS": "16384",
                "LOG_LEVEL": "INFO",
            },
            logger,
        )

    assert caplog.records == []


def test_log_settings_from_env_file_are_not_silently_dropped(tmp_path, monkeypatch):
    """D-11: `GLM2API_LOG_DIR`/`_MAX_BYTES`/`_BACKUP_COUNT` wurden direkt
    aus `os.environ` gelesen. `load_config()` liest die .env, exportiert
    sie aber nicht in die umgebung — ein in der datei gesetzter
    log-pfad war damit still unwirksam, waehrend die datei ihn als
    gueltige option auswies."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_REFRESH_TOKEN=account-token\n"
        "GLM_ASSISTANT_ID=1\n"
        "GLM2API_LOG_DIR=/var/log/glm2api\n"
        "GLM2API_LOG_MAX_BYTES=209715200\n"
        "GLM2API_LOG_BACKUP_COUNT=7\n",
        encoding="utf-8",
    )
    for name in ("GLM_REFRESH_TOKEN", "GLM_ASSISTANT_ID", "GLM2API_LOG_DIR",
                 "GLM2API_LOG_MAX_BYTES", "GLM2API_LOG_BACKUP_COUNT"):
        monkeypatch.delenv(name, raising=False)

    config = load_config(str(env_path))

    assert config.log_dir == "/var/log/glm2api"
    assert config.log_max_bytes == 209715200
    assert config.log_backup_count == 7


def test_log_settings_default_safely_when_absent(tmp_path, monkeypatch):
    """Ohne angaben bleiben die dokumentierten defaults erhalten."""
    env_path = tmp_path / ".env"
    env_path.write_text("GLM_REFRESH_TOKEN=t\nGLM_ASSISTANT_ID=1\n", encoding="utf-8")
    for name in ("GLM_REFRESH_TOKEN", "GLM_ASSISTANT_ID", "GLM2API_LOG_DIR"):
        monkeypatch.delenv(name, raising=False)

    config = load_config(str(env_path))

    assert config.log_dir == "log"
    assert config.log_max_bytes == 100 * 1024 * 1024
    assert config.log_backup_count == 3


# --- S-13: direktstart aus fremdem verzeichnis -------------------------


def test_env_file_is_found_when_started_from_another_directory(tmp_path, monkeypatch):
    """S-13: `.env` war ein relativer pfad. Ein direktstart aus einem
    anderen verzeichnis lud damit eine falsche konfiguration — oder legte
    ungefragt eine neue `.env` dort an (`ensure_env_file()`). Ohne die
    betriebsdatei lief der dienst auf dem code-default, waehrend agent
    und supervisor auf 8001 warteten."""
    from glm2api.config import _resolve_env_file

    package_root = Path(__file__).resolve().parent.parent  # .../llm-proxies/glm2api
    env_file = package_root / ".env"
    if not env_file.exists():
        pytest.skip("kein .env im repo (nur in einer echten installation)")

    monkeypatch.chdir(tmp_path)  # verzeichnis OHNE .env
    resolved = _resolve_env_file(".env")

    assert resolved == env_file, "muss die repo-.env finden, nicht cwd/.env"


def test_no_env_file_is_created_in_a_foreign_directory(tmp_path, monkeypatch):
    """Gegenprobe zur eigentlichen副作用: ein start aus einem fremden
    verzeichnis darf dort keine `.env` anlegen."""
    from glm2api.config import ensure_env_file

    monkeypatch.chdir(tmp_path)
    ensure_env_file(Path(".env"))

    assert not (tmp_path / ".env").exists()
