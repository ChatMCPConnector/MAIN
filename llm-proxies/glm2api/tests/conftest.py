import os

import pytest


_GLM_ENV_PREFIX = "GLM"
_ENV_KEYS = (
    "GLM2API_LOG_DIR",
    "GLM2API_LOG_MAX_BYTES",
    "GLM2API_LOG_BACKUP_COUNT",
)


@pytest.fixture(autouse=True)
def _isolate_process_environment(monkeypatch):
    """D-13: tests teilen prozess-globalen zustand (env, logging-konfiguration).

    Ein test, der `GLM_*` in der umgebung setzt, beeinflusste dadurch den
    nachfolgenden. Der fixture stellt den vorherigen stand fuer jeden test
    wieder her — damit das ergebnis nicht von der ausfuehrungsreihenfolge
    abhaengt."""
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    saved_glob = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(_GLM_ENV_PREFIX) and key not in saved
    }
    for key in [key for key in os.environ if key.startswith(_GLM_ENV_PREFIX)]:
        monkeypatch.delenv(key, raising=False)
    yield
    for key, value in saved_glob.items():
        os.environ[key] = value
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
