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


# --- S-02: CORS-default -----------------------------------------------


def test_cors_is_disabled_by_default(tmp_path, monkeypatch):
    """S-02: der default war `*`. Damit durfte JEDE website im browser
    des nutzers den loopback-dienst unter `http://127.0.0.1:8001`
    ansprechen und die antworten lesen — der `Host`-header ist dabei
    `127.0.0.1`, der rebinding-guard greift also nicht, und genau der
    wildcard erlaubt das lesen."""
    env_path = tmp_path / ".env"
    env_path.write_text("GLM_REFRESH_TOKEN=t\nGLM_ASSISTANT_ID=1\n", encoding="utf-8")
    monkeypatch.delenv("CORS_ALLOW_ORIGIN", raising=False)
    monkeypatch.delenv("SERVER_API_KEYS", raising=False)

    assert load_config(str(env_path)).cors_allow_origin == ""


def test_cors_wildcard_still_possible_when_explicitly_requested(tmp_path, monkeypatch):
    """Gegenprobe zum Komfort: wer browserzugriff wirklich braucht,
    kann ihn ausdruecklich einschalten — es wird nicht verboten, nur
    nicht mehr voreingestellt."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GLM_REFRESH_TOKEN=t\nGLM_ASSISTANT_ID=1\nCORS_ALLOW_ORIGIN=*\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CORS_ALLOW_ORIGIN", raising=False)
    monkeypatch.delenv("SERVER_API_KEYS", raising=False)

    assert load_config(str(env_path)).cors_allow_origin == "*"


def test_env_files_do_not_reintroduce_the_cors_wildcard():
    """Die ausgelieferte Beispielkonfiguration darf das Loch nicht
    wieder aufmachen — sonst waere die Umstellung in `.env.example`
    nach dem naechsten deploy wieder rueckgaengig."""
    from pathlib import Path as _P

    example = _P(__file__).resolve().parent.parent / ".env.example"
    if not example.exists():
        pytest.skip("keine .env.example im repo")
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("CORS_ALLOW_ORIGIN="):
            value = line.split("=", 1)[1].strip()
            assert value != "*", "die beispielkonfiguration darf CORS nicht auf '*' setzen"
            return
    pytest.fail("CORS_ALLOW_ORIGIN fehlt in .env.example")


def test_output_token_budget_allows_deep_reasoning_runs():
    """Der standard muss gross genug sein, damit ein agentenlauf mit
    `reasoning_effort: max` sein kontingent nicht durch das eigene
    nachdenken verbraucht. Gemessen an einer echten session
    (2026-09-25): 61 820 zeichen reasoning — bei 16 384 token standard
    lief das nachdenken in die ausgabegrenze und der turn endete mit
    `length` OHNE text und OHNE tool-call.

    32 768 gibt dem denkkanal 22 937 token (70 %) und der lieferung
    9 830 — beides reicht fuer einen arbeitsauftrag. Die
    konfigurationsgrenze erlaubt bis 131 072, es ist also kein
    grenzenfall."""
    from glm2api.config import _config_int
    import logging as _logging

    logger = _logging.getLogger("glm2api.config.test_budget")
    assert _config_int({}, "GLM_MAX_OUTPUT_TOKENS", 32768, 1024, 131072, logger) == 32768
    assert _config_int({"GLM_MAX_OUTPUT_TOKENS": "32768"}, "GLM_MAX_OUTPUT_TOKENS", 32768, 1024, 131072, logger) == 32768


def test_valid_keys_are_never_reported_as_typos(tmp_path):
    """Regression 2026-09-26: `GLM_IMAGE_ASSISTANT_ID` ist ein GUELTIGER
    key, wurde aber als tippfehler von `GLM_ASSISTANT_ID` gemeldet — die
    schleife verglich der reihe nach und brach beim ersten treffer ab
    (praefix-kollision). Eine sicherheitswarnung, die immer brennt, wird
    vom betreiber ignoriert; dann schuetzt sie nicht mehr.

    Gepruft wird gegen die tatsaechlich gueltigen keys aus der
    `.env`/`.env.example` des betriebs."""
    import logging as _logging

    from glm2api.config import _warn_unknown_config_keys

    records: list[str] = []

    class _Capture(_logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = _logging.getLogger("glm2api.config.test_valid_keys_2")
    logger.handlers = [_Capture()]
    logger.propagate = False
    logger.setLevel(_logging.WARNING)

    valid_keys = {
        "GLM_IMAGE_ASSISTANT_ID": "x", "GLM_ASSISTANT_ID": "y",
        "CORS_ALLOW_ORIGIN": "*", "PORT": "8001", "HOST": "127.0.0.1",
        "GLM_MAX_CONCURRENCY": "3", "GLM2API_LOG_DIR": "log",
        "GLM_BASE_URL": "https://chatglm.cn/chatglm", "SERVER_API_KEYS": "k",
        "GLM_REFRESH_TOKEN": "t", "GLM_MAX_OUTPUT_TOKENS": "16384",
        "GLM2API_LOG_MAX_BYTES": "104857600", "GLM2API_LOG_BACKUP_COUNT": "3",
        "GLM_USE_GUEST_REFRESH_TOKEN": "false", "LOG_LEVEL": "INFO",
    }
    _warn_unknown_config_keys(valid_keys, logger)

    assert records == [], f"gueltige keys wurden faelschlich gemeldet: {records}"


# --- 2026-09-26: tote keys in den ausgelieferten .env --------------------

# Diese vier standen in `.env`, `.env.example` und `llm-proxies/glm2api.env`
# und wirkten nicht. Zwei wurden als Nahbeirrung gemeldet, zwei stillschweigend
# ignoriert — und die beiden stillen hatten zudem exakt den Standardwert.
_ENV_KEYS_THAT_NEVER_WORKED = (
    ("GLM_REFRESH_TOKENS", "GLM_REFRESH_TOKEN"),
    ("REQUEST_TIMEOUT", "REQUEST_TIMEOUT_SECONDS"),
    ("REQUEST_SOCKET_TIMEOUT", "REQUEST_SOCKET_TIMEOUT_SECONDS"),
    ("GLM_QUEUE_WAIT_TIMEOUT", "GLM_QUEUE_WAIT_TIMEOUT_SECONDS"),
)


@pytest.mark.parametrize("file_name", [".env.example", "../glm2api.env"])
@pytest.mark.parametrize("dead,correct", _ENV_KEYS_THAT_NEVER_WORKED)
def test_shipped_env_files_contain_no_dead_config_key(file_name, dead, correct):
    """Ein key, den `load_config` nicht liest, sieht aus wie eine
    konfiguration und ist keine. Bei `GLM_REFRESH_TOKENS=` waere der
    inline-kommentar sogar als WERT gelandet.

    Geprueft werden ALLE ausgelieferten dateien, nicht nur `.env.example`:
    die drei sind handgepflegte kopien, und die drift ist genau das, was
    hier passiert war.
    """
    import pathlib

    import glm2api.config as config_module

    path = pathlib.Path(__file__).resolve().parents[1] / file_name
    if not path.exists():
        pytest.skip(f"{file_name} nicht im repo")
    values = config_module.parse_dotenv(path)

    assert dead not in values, f"{path.name}: '{dead}' wird nicht gelesen (richtig waere {correct})"
    # und der richtige key ist tatsaechlich dokumentiert
    assert correct in values, f"{path.name}: '{correct}' fehlt, '{dead}' stand da"


@pytest.mark.parametrize("dead,correct", [
    ("REQUEST_TIMEOUT", "REQUEST_TIMEOUT_SECONDS"),
    ("REQUEST_SOCKET_TIMEOUT", "REQUEST_SOCKET_TIMEOUT_SECONDS"),
    ("GLM_REFRESH_TOKENS", "GLM_REFRESH_TOKEN"),
])
def test_silent_dead_keys_are_now_reported_as_near_misses(dead, correct, caplog):
    """S-15 haette die beiden stillen tippfehler melden muessen. Vorher
    standen sie nicht in der nahbeirrungs-liste, deshalb liefen sie
    kommentarlos durch — der einzige grund, warum sie so lange
    unentdeckt blieben."""
    import logging as _logging

    from glm2api.config import _warn_unknown_config_keys

    logger = _logging.getLogger("glm2api.config.test_dead_keys")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        _warn_unknown_config_keys({dead: "x", correct: "y"}, logger)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert dead in messages, f"{dead} wird nicht mehr gemeldet"
    assert correct in messages
    assert "NO effect" in messages


# --- 2026-09-26: doppelte keys in der .env ---------------------------------

# Live: eine leere zweite `GLM_REFRESH_TOKEN=` verdraengte den echten
# token aus zeile 63 (`parse_dotenv` laesst den letzten gewinnen), und der
# dienst startete nicht mehr — "kein ChatGLM-Konto konfiguriert". Die datei
# sah korrekt aus. Genau deshalb wird der doppelte key jetzt gemeldet, mit
# zeilennummern und ohne den wert zu nennen.


def test_duplicate_key_with_different_value_is_reported(tmp_path, caplog):
    import logging as _logging

    from glm2api.config import parse_dotenv

    env = tmp_path / ".env"
    env.write_text(
        "GLM_REFRESH_TOKEN=echtes-token\n"
        "GLM_PORT=8001\n"
        "\n"
        "# ein kommentar\n"
        "GLM_REFRESH_TOKEN=\n",
        encoding="utf-8",
    )
    logger = _logging.getLogger("glm2api.config.test_dup")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        values = parse_dotenv(env, logger)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "GLM_REFRESH_TOKEN" in messages
    assert "line 1" in messages and "line 5" in messages
    # der wert selbst darf NIE im log stehen
    assert "echtes-token" not in messages
    # verhalten bleibt: letzter gewinnt (dokumentiert, nicht geaendert)
    assert values["GLM_REFRESH_TOKEN"] == ""


def test_duplicate_key_with_the_same_value_stays_quiet(tmp_path, caplog):
    """Zweimal derselbe wert ist harmlos (z. B. eine kopie am ende der
    datei) und darf keinen lärm machen."""
    import logging as _logging

    from glm2api.config import parse_dotenv

    env = tmp_path / ".env"
    env.write_text("GLM_TOKEN_FILE=token.txt\nGLM_TOKEN_FILE=token.txt\n", encoding="utf-8")
    logger = _logging.getLogger("glm2api.config.test_dup_same")
    with caplog.at_level(_logging.WARNING, logger=logger.name):
        values = parse_dotenv(env, logger)

    assert not caplog.records
    assert values["GLM_TOKEN_FILE"] == "token.txt"


@pytest.mark.parametrize("file_name", [".env.example", "../glm2api.env"])
def test_shipped_env_files_have_no_duplicate_keys(file_name):
    """Die handgepflegten kopien der betriebsdatei: ein doppelter key ist
    dort immer ein merge-fehler, und die files werden nicht automatisch
    aus einer quelle erzeugt."""
    import pathlib

    from glm2api.config import parse_dotenv

    path = pathlib.Path(__file__).resolve().parents[1] / file_name
    if not path.exists():
        pytest.skip(f"{file_name} nicht im repo")

    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in seen:
            duplicates.append(f"{key} (Zeile {seen[key]} und {line_number})")
        seen[key] = line_number

    assert not duplicates, f"{path.name}: doppelte keys -> {duplicates}"
    # parse_dotenv bleibt trotzdem aufrufbar (sanity, der pfad wird genutzt)
    assert isinstance(parse_dotenv(path), dict)
