import logging
import stat

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
    monkeypatch.setenv("GLM2API_LOG_DIR", str(log_dir))
    setup_logging("DEBUG")
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
        setup_logging("INFO")

