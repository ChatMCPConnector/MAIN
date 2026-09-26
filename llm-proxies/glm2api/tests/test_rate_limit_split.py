"""F-6: upstream-code 10061 hat zwei bedeutungen und braucht zwei antworten.

Der proxy hat beide ueber denselben pfad geschickt: HTTP 429 ->
`_should_retry_busy_error` -> 30 versuche im 2s-raster. Bei einer echten
konto-drosselung ("请求过于频繁") feuerte das 30 requests in ~4 minuten auf
ein konto, das in minuten abklingt — jeder versuch verlaegerte die
freigabe. Zusaetzlich stand 10061 in `TRANSIENT_UPSTREAM_ERROR_CODES`, der
stream-retry (2x, 1s) lief also mit.

Diese tests halten die trennung fest: busy darf weiter schnell und oft
warten, eine drosselung darf das nicht.
"""

import email.message
import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from glm2api.services.glm_client import GLMWebClient, UpstreamAPIError


BUSY_BODY = {"status": 10061, "message": "请等待其他对话生成完毕"}
RATE_LIMIT_BODY = {"status": 10061, "message": "请求过于频繁，请稍后再试"}


class _ThrottleConfig:
    glm_stream_error_max_retries = 2
    glm_stream_error_retry_interval = 0.0
    glm_max_output_tokens = 16384
    glm_blocked_tool_follow_ups = 0
    glm_empty_response_max_retries = 2
    glm_history_max_chars = 120000
    request_timeout = 5
    blocked_tool_names = []
    debug_dump_all = False
    glm_assistant_id = "assistant"
    glm_delete_conversation = False
    glm_queue_wait_timeout = 5
    glm_max_concurrency = 1
    glm_base_url = "https://chatglm.cn/chatglm"
    chat_stream_url = "https://chatglm.cn/chatglm/api/chat/stream"
    glm_busy_max_retries = 3
    glm_busy_retry_interval = 2.0
    glm_rate_limit_max_retries = 2
    glm_rate_limit_retry_interval = 30.0
    glm_request_deadline_seconds = 300.0
    glm_persistent_conversation = False


def _http_error(body):
    return urllib.error.HTTPError(
        url="https://chatglm.cn/chatglm/api/chat/stream",
        code=429,
        msg="Too Many Requests",
        hdrs=email.message.Message(),
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


def _make_client(monkeypatch, body, *, calls):
    """Client, dessen `_open_chat_stream` bis zum HTTP-send läuft und dann
    mit `body` abgewiesen wird. `time.sleep` wird aufgezeichnet, nicht
    abgewartet — 90s echte Wartezeit waere kein Test mehr."""
    waits = []
    monkeypatch.setattr(
        "glm2api.services.glm_client.time.sleep", lambda seconds: waits.append(seconds)
    )

    def fake_urlopen(request, timeout=None):
        calls["count"] += 1
        raise _http_error(body)

    monkeypatch.setattr("glm2api.services.glm_client.urllib.request.urlopen", fake_urlopen)

    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _ThrottleConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.auth = SimpleNamespace(
        get_browser_headers=lambda: {},
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda i: "tok",
    )
    # der failover ist nicht der gegenstand dieses tests — er wuerde bei
    # einem 429 das konto rotieren und die zaehlung verwischen.
    client._call_with_account_failover = lambda name, operation, preferred_account_index=None: (
        operation(0, "tok")
    )
    client.reset_active_conversation = lambda: None
    client.delete_conversation = lambda cid, assistant_id=None: None
    return client, waits


def _open(client):
    return client._open_chat_stream(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "hi"}]},
        filtered_tools=[],
    )


# --- Klassifikation -------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"status": 10061, "message": "请等待其他对话生成完毕"}, "busy"),
        ({"status": 10061, "message": "请求过于频繁，请稍后再试"}, "rate_limit"),
        # 10061 ohne erkennbare message: ratelimit ist der wahrscheinlichere
        # und der schaedlichere fehlerfall.
        ({"status": 10061}, "rate_limit"),
        # SSE-form: code/err_msg statt status/message
        ({"last_error": {"error_code": 10061, "err_msg": "请求过于频繁"}}, "rate_limit"),
        ({"error": {"error_code": 10061, "message": "请等待其他对话生成完毕"}}, "busy"),
        # englische variante
        ({"status": 10061, "message": "Too Many Requests"}, "rate_limit"),
        # kein throttling
        ({"status": 10040, "message": "context exceeded"}, ""),
        ({"status": 10025, "message": "stream request error"}, ""),
    ],
)
def test_classify_upstream_throttle(payload, expected):
    assert GLMWebClient._classify_upstream_throttle(payload) == expected


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"error_code": 10025, "err_msg": "stream request error"}, True),
        ({"error_code": 10040, "err_msg": "context exceeded"}, True),
        ({"error_code": 10062, "err_msg": "upstream busy"}, True),
        # der busy-code kommt im 429-body als `status`, im SSE-event als
        # `error_code` — beide formen muessen als transient gelten
        ({"status": 10061, "message": "请等待其他对话生成完毕"}, True),
        ({"error_code": 10061, "err_msg": "请等待其他对话生成完毕"}, True),
        # F-6: die drosselung ist NICHT transient. Waere sie es, naeme der
        # stream-retry sie auf und produzierte genau die sekundenschnellen
        # versuche, die das hier verhindern soll.
        ({"status": 10061, "message": "请求过于频繁，请稍后再试"}, False),
        ({"error_code": 10061, "err_msg": "请求过于频繁"}, False),
        ({"status": 10061}, False),
        ({"error_code": 99999, "err_msg": "boom"}, False),
        ("kein payload", False),
    ],
)
def test_payload_is_transient(payload, expected):
    assert GLMWebClient._payload_is_transient(GLMWebClient.__new__(GLMWebClient), payload) is expected


def test_10061_steht_nicht_mehr_in_den_transienten_codes():
    assert 10061 not in GLMWebClient.TRANSIENT_UPSTREAM_ERROR_CODES
    assert 10061 in GLMWebClient.THROTTLE_UPSTREAM_ERROR_CODES


# --- Backoff --------------------------------------------------------------


def test_rate_limit_backoff_verdoppelt_und_ist_gedeckelt():
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _ThrottleConfig()
    waits = [client._rate_limit_backoff_seconds(attempt) for attempt in range(1, 8)]

    assert waits[0] == pytest.approx(30.0, abs=3.0)
    assert waits[1] == pytest.approx(60.0, abs=6.0)
    assert waits[2] == pytest.approx(120.0, abs=12.0)
    # ab dem vierten versuch ist die schranke erreicht (8x basis = 240s) und
    # die wartezeit waechst nicht weiter — sonst wuerde ein request mit
    # maximalem budget stundenlang auf einem gedrosselten konto stehen.
    for wait in waits[3:]:
        assert 240.0 <= wait <= 240.0 * 1.1


def test_rate_limit_backoff_hat_keinen_jitter_nach_unten():
    """Bei einer drosselung ist gleichzeitiges aufwachen mehrerer clients
    genau das, was die sperre am laufen haelt. Der jitter darf nur nach
    oben entzerren."""
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _ThrottleConfig()
    for _ in range(50):
        assert client._rate_limit_backoff_seconds(1) >= 30.0


# --- HTTP-pfad ------------------------------------------------------------


def test_rate_limit_wird_wenig_und_lange_wiederholt(monkeypatch):
    calls = {"count": 0}
    client, waits = _make_client(monkeypatch, RATE_LIMIT_BODY, calls=calls)

    with pytest.raises(UpstreamAPIError) as excinfo:
        _open(client)

    # 1 + 2 retries, nicht 1 + 30
    assert calls["count"] == 3
    assert len(waits) == 2
    assert waits[0] >= 30.0
    assert waits[1] >= 60.0
    # der client bekommt einen sauberen 429 und KEIN transient-flag
    assert excinfo.value.status_code == 429
    assert excinfo.value.transient is False


def test_busy_behaelt_das_schnelle_profil(monkeypatch):
    """Regression: die trennung darf den nebenlauf-busy nicht verschaerfen."""
    calls = {"count": 0}
    client, waits = _make_client(monkeypatch, BUSY_BODY, calls=calls)

    with pytest.raises(UpstreamAPIError) as excinfo:
        _open(client)

    assert calls["count"] == 4, "1 + glm_busy_max_retries(3)"
    assert len(waits) == 3
    assert all(wait < 30.0 for wait in waits), "busy bleibt im sekundenbereich"
    assert excinfo.value.transient is True


def test_rate_limit_ohne_retry_budget_geht_sofort_zum_client(monkeypatch):
    calls = {"count": 0}
    client, waits = _make_client(monkeypatch, RATE_LIMIT_BODY, calls=calls)
    client.config.glm_rate_limit_max_retries = 0

    with pytest.raises(UpstreamAPIError) as excinfo:
        _open(client)

    assert calls["count"] == 1
    assert waits == []
    assert excinfo.value.status_code == 429


def test_rate_limit_abbruch_bei_erreichter_request_deadline(monkeypatch):
    """Wer die 30s-wartezeit nicht mehr in das request-budget passt, wartet
    nicht — er meldet den 429, statt den aufrufer ueber sein eigenes
    deadline zu heben."""
    calls = {"count": 0}
    client, waits = _make_client(monkeypatch, RATE_LIMIT_BODY, calls=calls)
    client.config.glm_request_deadline_seconds = 0.0
    # deadline 0 = aus; wir setzen sie stattdessen hart, indem wir die
    # abfrage monkeypatchen
    client._request_deadline = lambda: 0.0
    client._deadline_exceeded = lambda deadline: True

    with pytest.raises(UpstreamAPIError) as excinfo:
        _open(client)

    assert calls["count"] == 1
    assert waits == []
    assert excinfo.value.status_code == 429


def test_rate_limit_gibt_keinen_zusatzlichen_stream_retry(monkeypatch):
    """Der fluss nach dem 429: `transient=False` ist die ganze garantie. Ein
    transientes flag wuerde den stream-retry (2x, 1s) wieder in gang
    setzen — die kombination war die ursache der eskalation."""
    calls = {"count": 0}
    client, _ = _make_client(monkeypatch, RATE_LIMIT_BODY, calls=calls)
    client._read_error_payload = lambda exc: dict(RATE_LIMIT_BODY)

    with pytest.raises(UpstreamAPIError) as excinfo:
        _open(client)

    assert excinfo.value.transient is False
    assert excinfo.value.payload.get("status") == 10061


def test_anderer_429_code_bleibt_nicht_throttle():
    """Nur 10061 (und die rate-limit-textmarker) sind throttle. Ein 429 aus
    anderem grund darf den langen ratelimit-pfad nicht ziehen."""
    client = GLMWebClient.__new__(GLMWebClient)
    assert GLMWebClient._classify_upstream_throttle({"status": 429, "message": "capacity"}) == ""
