import logging

from glm2api.config import GUEST_REFRESH_TOKEN_MARKER, load_config
from glm2api.logging_utils import setup_logging


def test_single_refresh_token_adds_guest_fallback(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_REFRESH_TOKEN=account-token\n"
        "GLM_USE_GUEST_REFRESH_TOKEN=false\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GLM_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("GLM_USE_GUEST_REFRESH_TOKEN", raising=False)

    config = load_config(env_path)

    assert config.glm_refresh_tokens == ["account-token", GUEST_REFRESH_TOKEN_MARKER]
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

