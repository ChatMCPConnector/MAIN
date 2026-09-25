import logging
import threading
import time
from types import SimpleNamespace

import pytest

from glm2api.services.glm_client import (
    ConcurrentRequestQueue,
    GLMWebClient,
    QueueTimeoutError,
)


def _client(**config_overrides):
    client = GLMWebClient.__new__(GLMWebClient)
    config = SimpleNamespace(
        glm_persistent_conversation=True,
        glm_conversation_id="",
        glm_conversation_file=None,
        blocked_tool_names=[],
        debug_dump_all=False,
        glm_history_max_chars=120000,
        glm_max_output_tokens=16384,
        glm_conversation_persist=True,
    )
    for key, value in config_overrides.items():
        setattr(config, key, value)
    client.config = config
    client.logger = logging.getLogger("test.conversation")
    client.logger.addHandler(logging.NullHandler())
    client._persistent_conversation_id = config.glm_conversation_id
    client._persistent_conversation_account = None
    client._conversation_lock = threading.Lock()
    client._conversation_use_lock = threading.RLock()
    return client


# --- C-01: Queue-Ghost ----------------------------------------------------


def test_timed_out_ticket_does_not_block_following_requests():
    """C-01: ein einzelner timeout hielt die serving-sequenz dauerhaft fest
    — danach lief KEIN weiterer chat/image/sse-request mehr durch."""
    logger = logging.getLogger("test.queue")
    logger.addHandler(logging.NullHandler())
    queue = ConcurrentRequestQueue(logger, wait_timeout=0, max_concurrency=1)

    first = queue.acquire("A")
    with pytest.raises(QueueTimeoutError):
        queue.acquire("B")
    first.release()

    # Vor dem Fix blockierte dieses Ticket dauerhaft.
    third = queue.acquire("C")
    third.release()


def test_multiple_timeouts_in_a_row_keep_queue_usable():
    logger = logging.getLogger("test.queue2")
    logger.addHandler(logging.NullHandler())
    queue = ConcurrentRequestQueue(logger, wait_timeout=0, max_concurrency=1)

    for _ in range(3):
        lease = queue.acquire("running")
        with pytest.raises(QueueTimeoutError):
            queue.acquire("timeout")
        lease.release()

    final = queue.acquire("after")
    final.release()


# --- C-03: Conversation-Isolation ----------------------------------------


def test_persistent_conversation_is_bound_to_its_account():
    """C-03: die conversation-id war ein globaler string. Ein kontowechsel
    trug den kontext in ein anderes konto."""
    client = _client()
    client.set_active_conversation_id("conv-a", account_index=0)

    assert client.conversation_for_account(0) == "conv-a"
    # kontowechsel -> frische historie statt kontextuebergang
    assert client.conversation_for_account(1) == ""


def test_persistent_conversation_is_exclusive_per_round():
    """C-03: zwei parallele runden teilten sich dieselbe upstream-historie
    (last-writer-wins). Die conversation gehoert jetzt exklusiv einer
    runde."""
    client = _client()
    client.set_active_conversation_id("conv-a", account_index=0)

    order: list[str] = []
    started = threading.Event()

    with client.exclusive_conversation(0):
        order.append("runde-1-hält")

        def second_round():
            with client.exclusive_conversation(0):
                order.append("runde-2-hält")

        thread = threading.Thread(target=second_round)
        thread.start()
        started.set()
        time.sleep(0.05)
        # runde 2 darf die conversation noch NICHT benutzen
        assert order == ["runde-1-hält"]
        order.append("runde-1-frei")
    thread.join(timeout=2)
    assert order == ["runde-1-hält", "runde-1-frei", "runde-2-hält"]


def test_exclusive_conversation_is_noop_without_persistence():
    client = _client(glm_persistent_conversation=False)
    with client.exclusive_conversation(0) as conv_id:
        assert conv_id == ""


def test_client_supplied_conversation_id_must_be_owned():
    """C-03: eine clientgelieferte conversation_id ist kein
    eigentumsnachweis — eine fremde id darf keine historie fortsetzen."""
    client = _client()
    client.set_active_conversation_id("conv-meins", account_index=0)

    # die eigene id darf verwendet werden
    assert client._resolve_target_conversation_id({"conversation_id": "conv-meins"}, 0) == "conv-meins"
    # eine fremde/geratene id wird ignoriert
    assert client._resolve_target_conversation_id({"conversation_id": "conv-fremd"}, 0) == ""
    # persistenz ohne client-id nutzt die eigene conversation des kontos
    assert client._resolve_target_conversation_id({}, 0) == "conv-meins"
    # ... und ein kontowechsel verwirft sie (der aufruf mit konto 1 loest
    # den wechsel aus, danach ist die historie bewusst leer)
    assert client._resolve_target_conversation_id({"conversation_id": "conv-meins"}, 1) == ""
    assert client._resolve_target_conversation_id({}, 1) == ""


def test_new_session_flag_wins_over_persistent_conversation():
    client = _client()
    client.set_active_conversation_id("conv-meins", account_index=0)

    assert client._resolve_target_conversation_id({"new_session": True}, 0) == ""
    assert client._resolve_target_conversation_id({"reset_conversation": True}, 0) == ""


def test_no_persistent_conversation_without_flag():
    client = _client(glm_persistent_conversation=False)

    assert client._resolve_target_conversation_id({}, 0) == ""


# --- C-15: Loeschung am ERZEUGERKONTO ------------------------------------


def test_delete_conversation_targets_the_creating_account():
    """C-15: die conversation gehoert dem konto, das sie erzeugt hat.
    `delete_conversation` lief aber ueber `_call_with_account_failover`
    und konnte ein anderes konto waehlen — bei mehreren accounts wurde
    dann die falsche conversation geloescht und die eigentliche blieb
    serverseitig liegen (memory-/context-leck, haenger queue-slot)."""
    from glm2api.services.glm_client import GLMWebClient

    client = GLMWebClient.__new__(GLMWebClient)
    used_accounts = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    client.config = SimpleNamespace(
        glm_persistent_conversation=False,
        glm_delete_conversation=True,
        glm_assistant_id="a1",
        request_timeout=5,
        delete_conversation_url="https://example.invalid/delete",
    )
    client.logger = SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None)
    client.auth = SimpleNamespace(
        get_browser_headers=lambda: {},
        get_access_token_for_account=lambda i: (used_accounts.append(i), f"tok{i}")[1],
        read_json_response=lambda r: {"status": 0},
    )

    def send_request(account_index, access_token):
        used_accounts.append(account_index)
        return _Resp()

    # der gezielte pfad darf _call_with_account_failover nicht benutzen
    client._call_with_account_failover = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("failover darf bei bekanntem konto nicht greifen")
    )
    import glm2api.services.glm_client as mod

    original = mod.urllib.request.urlopen
    mod.urllib.request.urlopen = lambda request, timeout=None: _Resp()
    try:
        client.delete_conversation("conv-1", assistant_id="a1", account_index=2)
    finally:
        mod.urllib.request.urlopen = original

    assert 2 in used_accounts, "das erzeugerkonto muss den aufruf ausfuehren"
