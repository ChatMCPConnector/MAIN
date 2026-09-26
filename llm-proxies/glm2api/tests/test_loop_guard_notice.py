"""T-25: der loop guard war fuer das modell unsichtbar.

Live-Fall 2026-09-26 (`ses_f21fbf23…`): das modell rief 10x in EINEM turn
`open` mit identischem ziel `/workspaces/MAIN/glm2api`. Der proxy mappt
`open` auf `read` (translator.map_native_open_tool_call), der loop guard
lässt 2 durch und verwirft 8 — **ohne jede rueckmeldung**. Das modell sah
10 calls und 2 ergebnisse, schloss auf ein nicht existentes limit
("Tool-Limit (8/8 Runden) erreicht"), brach ab und verlangte einen neustart.

Diese tests halten fest:
  - der guard verwirft weiter (doppelt ausgefuehrt wird nicht),
  - aber jeder verworfene call wird fuer das modell SICHTBAR,
  - die notice nennt den nativen namen (`open`), nicht den gemappten
    (`read`) — sonst sucht das modell den fehler im falschen werkzeug,
  - und sie widerspricht der limit-narrative ausdruecklich.
"""

import json
from types import SimpleNamespace

from glm2api.services.glm_client import GLMWebClient, _loop_guard_notice_text
from glm2api.services.translator import GLMEventAccumulator

TARGET = "/workspaces/MAIN/glm2api"


def _native_open_event(call_id: str, target: str = TARGET):
    return {
        "status": "init",
        "parts": [
            {
                "id": f"p{call_id}",
                "logic_id": f"l{call_id}",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": call_id,
                            "name": "open",
                            "arguments": json.dumps({"open": [{"ref_id": target, "lineno": 1}]}),
                        },
                    }
                ],
            }
        ],
    }


def _feed(acc, count: int, target: str = TARGET, tag: str = "c"):
    for index in range(count):
        acc.consume_event(_native_open_event(f"call_{tag}{index}", target))


def _acc():
    return GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "read", "webfetch"})


# --- Guard-Verhalten (unveraendert) ---------------------------------------


def test_loop_guard_liefert_nur_zwei_und_zaehlt_die_drops():
    acc = _acc()
    _feed(acc, 10)

    assert len(acc._server_side_tool_calls) == 2, "zwei identische calls sind erlaubt"
    assert acc.loop_guard_dropped_count == 8
    assert acc.blocked_tool_attempt_names == [], "der guard ist KEIN blocked-tool-fall"


def test_unterschiedliche_ziele_werfen_den_guard_nicht_aus():
    """Der guard gilt pro signatur. Zwei verschiedene pfade sind zwei
    echte aufrufe — sonst wuerde er legitime arbeit kappen."""
    acc = _acc()
    _feed(acc, 3, target="/workspaces/MAIN/a.md", tag="a")
    _feed(acc, 3, target="/workspaces/MAIN/b.md", tag="b")

    assert len(acc._server_side_tool_calls) == 4
    assert acc.loop_guard_dropped_count == 2


def test_ohne_drops_bleibt_der_zaehler_null():
    acc = _acc()
    _feed(acc, 2)
    assert acc.loop_guard_dropped_count == 0


# --- Notice ---------------------------------------------------------------


def test_notice_nennt_den_nativen_namen_nicht_den_gemappten():
    text = _loop_guard_notice_text(8, ["open"])
    assert "open" in text
    # `read` ist der gemappte name — ihn zu nennen wuerde das modell auf
    # das falsche werkzeug schicken (live-fall: 'read funktioniert nicht').
    assert "identical open call" in text


def test_notice_widerspricht_der_limit_narrative():
    text = _loop_guard_notice_text(8, ["open"]).lower()
    assert "no tool limit" in text
    assert "round limit" in text
    assert "fix the" in text and "instead of repeating" in text


def test_notice_nennt_die_anzahl():
    assert "8 identical" in _loop_guard_notice_text(8, ["open"])


def test_ohne_drops_keine_notice():
    assert _loop_guard_notice_text(0, []) == ""
    assert _loop_guard_notice_text(-1, ["open"]) == ""


def test_notice_ohne_toolnamen_bleibt_lesbar():
    text = _loop_guard_notice_text(3, [])
    assert "3 identical" in text
    assert "loop guard" in text


class _LoopGuardConfig:
    glm_stream_error_max_retries = 2
    glm_stream_error_retry_interval = 0.0
    glm_max_output_tokens = 16384
    glm_blocked_tool_follow_ups = 0
    glm_empty_response_max_retries = 0
    glm_history_max_chars = 120000
    glm_request_deadline_seconds = 300.0
    request_timeout = 5
    blocked_tool_names = []
    debug_dump_all = False
    glm_assistant_id = "assistant"
    glm_delete_conversation = False
    glm_queue_wait_timeout = 5
    glm_max_concurrency = 1
    glm_base_url = "https://chatglm.cn/chatglm"
    glm_persistent_conversation = False


class _FakeResponse:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def close(self):
        self.closed = True


def _make_client():
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _LoopGuardConfig()
    client.logger = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, debug=lambda *a, **k: None
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1, get_access_token_for_account=lambda i: "tok"
    )
    events = [_native_open_event(f"call_{i}") for i in range(6)]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    client.delete_conversation = lambda cid, assistant_id=None: None
    client._iter_sse_events = lambda response: iter(response._events)
    return client


def _payload():
    return {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "lies die datei"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "parameters": {
                        "type": "object",
                        "properties": {"filePath": {"type": "string"}},
                        "required": ["filePath"],
                    },
                },
            }
        ],
    }


# --- Sichtbarkeit im Antwortstrom ----------------------------------------


def test_stream_antwort_enthaelt_die_loop_guard_notice():
    client = _make_client()
    chunks = [c.decode("utf-8") for c in client.stream_chat_completion(_payload())]
    text = "".join(chunks)
    assert "[loop_guard_notice]" in text
    assert "4 identical open call" in text
    assert "NO tool limit" in text


def test_stream_liefert_genau_zwei_calls_und_keine_mehr():
    client = _make_client()
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    # die argument-string stehen im SSE-chunk escaped
    assert text.count("filePath") == 2, "der guard darf nicht auf 6 durchlassen"


def test_non_stream_antwort_enthaelt_die_loop_guard_notice():
    client = _make_client()
    result, _ = client.chat_completion(_payload())
    message = result["choices"][0]["message"]
    content = message.get("content") or ""
    assert "[loop_guard_notice]" in content
    assert "NO tool limit" in content
    assert len(message.get("tool_calls") or []) == 2


def test_ohne_drops_keine_notice_im_strom():
    """Gegenprobe: ein turn mit zwei verschiedenen zielen darf keine
    alarmmeldung produzieren, sonst schickt der proxy bei jedem normalen
    tool-loop eine."""
    client = _make_client()
    events = [_native_open_event(f"call_a{i}", "/workspaces/MAIN/a.md") for i in range(2)]
    events += [_native_open_event(f"call_b{i}", "/workspaces/MAIN/b.md") for i in range(2)]
    client._open_chat_stream = lambda p, preferred_account_index=None, filtered_tools=None: (
        _FakeResponse(events),
        "assistant-1",
    )
    text = "".join(c.decode("utf-8") for c in client.stream_chat_completion(_payload()))
    assert "[loop_guard_notice]" not in text

