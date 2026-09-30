"""Long-session regression harness for the glm2api -> OpenCode tool loop.

This deliberately simulates the client boundary: after glm2api emits valid
calls, OpenCode executes them and sends their tool results back in a NEW
request. Internal GLM correction rounds must never jump ahead of that result.
Run directly with: python -m pytest -q tests/test_long_session_recovery.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from glm2api.services.glm_client import GLMWebClient


class _Config:
    glm_stream_error_max_retries = 1
    glm_stream_error_retry_interval = 0.0
    glm_max_output_tokens = 4096
    glm_blocked_tool_follow_ups = 5
    glm_empty_response_max_retries = 0
    glm_history_max_chars = 120_000
    glm_request_deadline_seconds = 60.0
    request_timeout = 5
    blocked_tool_names = []
    debug_dump_all = False
    glm_assistant_id = "assistant"
    glm_delete_conversation = False
    glm_queue_wait_timeout = 5
    glm_max_concurrency = 1
    glm_base_url = "https://chatglm.cn/chatglm"
    glm_persistent_conversation = False


class _Response:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def close(self):
        self.closed = True


def _event(tool_calls=(), *, text=None, status="finish"):
    content = []
    for call_id, name, arguments in tool_calls:
        content.append(
            {
                "type": "tool_calls",
                "tool_calls": {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                },
            }
        )
    if text is not None:
        content.append({"type": "text", "text": text})
    return {
        "status": status,
        "parts": [{"logic_id": f"part-{status}", "status": status, "content": content}],
    }


def _payload():
    return {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "Audit important repo files read-only."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Read a local file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filePath": {"type": "string"}},
                        "required": ["filePath"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a read-only shell inspection.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
        ],
    }


def _make_scripted_build_client(rounds):
    """Return the actual proxy stream method wired to a deterministic GLM.

    A round tuple is (events, returned tool results). Events are exposed to
    the real accumulator, mapper, request-scope loop guard and follow-up
    decision. Tool results are appended only after the proxy has returned
    calls, just like OpenCode does after executing them.
    """
    client = GLMWebClient.__new__(GLMWebClient)
    client.config = _Config()
    client.logger = SimpleNamespace(
        warning=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    client.request_queue = SimpleNamespace(
        acquire=lambda _name: SimpleNamespace(ticket=0, released=False, release=lambda: None)
    )
    client.auth = SimpleNamespace(
        get_account_count=lambda: 1,
        get_access_token_for_account=lambda _index: "test-token",
    )
    client.delete_conversation = lambda _cid, assistant_id=None, account_index=None: None
    client._iter_sse_events = lambda response: iter(response._events)
    state = {"upstream_calls": 0, "payloads": [], "calls": [], "results": [], "outputs": []}

    def open_round(payload, preferred_account_index=None, filtered_tools=None):
        index = state["upstream_calls"]
        state["upstream_calls"] += 1
        state["payloads"].append(payload)
        if index >= len(rounds):
            return _Response([_event(text="Audit complete from returned tool results.")]), "assistant"
        events, tool_results = rounds[index]
        state["results"].append(list(tool_results))
        return _Response(events), "assistant"

    client._open_chat_stream = open_round
    return client, state


def _tool_calls_from_chunks(chunks):
    calls = []
    for chunk in chunks:
        if not chunk.startswith("data: {"):
            continue
        try:
            item = json.loads(chunk.removeprefix("data: ").strip())
        except json.JSONDecodeError:
            continue
        delta = item.get("choices", [{}])[0].get("delta", {})
        calls.extend(delta.get("tool_calls", []) or [])
    return calls


def _run_scripted_build_rounds(rounds):
    """Run each proxy response as a distinct OpenCode request/execute/return
    cycle, so cross-request history and tool results behave like Build mode.
    """
    client, state = _make_scripted_build_client(rounds)
    history = list(_payload()["messages"])
    state["calls"] = []
    state["results"] = []
    state["outputs"] = []

    for _index in range(len(rounds)):
        request = _payload()
        request["messages"] = list(history)
        chunks = [chunk.decode("utf-8") for chunk in client.stream_chat_completion(request)]
        state["outputs"].append(chunks)
        calls = _tool_calls_from_chunks(chunks)
        state["calls"].extend(calls)
        script_results = {
            str(result.get("call_id", "")): result
            for result in rounds[_index][1]
        }
        returned_results = []
        if calls:
            history.append({"role": "assistant", "tool_calls": calls})
            for call in calls:
                function = call.get("function", {})
                arguments = function.get("arguments", {}) if isinstance(function, dict) else {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                result = script_results.get(str(call.get("id", "")))
                if result is not None and isinstance(arguments, dict):
                    if str(arguments.get("filePath", "")) != str(result.get("file_path", "")):
                        result = None
                if result is None:
                    continue
                returned_results.append(result)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": result["call_id"],
                        "content": result["content"],
                    }
                )
        state["results"].append(returned_results)

    # Once all scripted tool results have been executed and returned, give the
    # model a final client request and a clear result-backed closing answer.
    final_request = _payload()
    final_request["messages"] = history
    state["payloads"].append(final_request)
    final_chunks = [
        chunk.decode("utf-8")
        for chunk in client.stream_chat_completion(final_request)
    ]
    state["outputs"].append(final_chunks)
    state["final_text"] = "".join(final_chunks)
    state["round"] = state["upstream_calls"]
    return state


def test_long_session_waits_for_client_tool_results_before_correction():
    """Four distinct file reads span four OpenCode requests.

    Baseline bug: after round 1 remapped open->read, glm2api starts an
    internal GLM correction before OpenCode executes the read. That round
    consumes the next scripted GLM response with no tool output in history.
    Correct behavior returns the read first, then subsequent client requests
    carry real results and the proxy does not synthesize stale corrections.
    """
    paths = [f"/workspaces/MAIN/audit-{index}.md" for index in range(4)]
    rounds = []
    for index, path in enumerate(paths):
        native = (f"open-{index}", "open", {"open": [{"ref_id": path}]})
        result = {
            "call_id": f"open-{index}",
            "name": "read",
            "content": f"real file result {index}: {path}",
            "file_path": path,
        }
        rounds.append(([_event([native])], [result]))

    state = _run_scripted_build_rounds(rounds)

    # Every model request follows an OpenCode tool hand-off, plus one final
    # answer request; an internal proxy correction must not consume a script
    # round before a tool result has been returned.
    assert state["round"] == len(paths) + 1, (
        f"expected {len(paths)} client tool-result rounds plus final answer; got {state['round']}"
    )
    delivered_reads = [call for call in state["calls"] if call.get("function", {}).get("name") == "read"]
    assert len(delivered_reads) == len(paths), f"valid reads lost: {delivered_reads}"
    assert all(
        f"real file result {index}" in str(state["payloads"][index + 1]["messages"])
        for index in range(len(paths))
    ), "the next model round must include the actual prior OpenCode tool result"
    assert "Audit complete" in state["final_text"]
    assert not any("[native_remap_notice]" in str(payload) for payload in state["payloads"]), (
        "successful tool results should not trigger stale pre-execution correction payloads"
    )


def test_24_round_mixed_open_drift_and_invalid_references_recovers_without_stale_turns():
    """Stress 24 request/response rounds with duplicate opens and bad refs.

    Every fifth round includes an unmappable search ref. A valid read follows
    the invalid call, testing that policy feedback does not discard useful
    calls; duplicate native opens test the cross-round loop guard. The model
    receives concrete results on the next client request and eventually
    closes with a real final answer.
    """
    rounds = []
    expected_paths = []
    for index in range(24):
        path = f"/workspaces/MAIN/audit/section-{index}.md"
        expected_paths.append(path)
        calls = []
        if index % 5 == 0:
            calls.append((f"bad-{index}", "open", {"open": [{"ref_id": f"turn{index}search0"}]}))
        calls.append((f"open-a-{index}", "open", {"open": [{"ref_id": path}]}))
        if index % 4 == 0:
            # Duplicate same target in one model turn: guard should allow at
            # most two, while preserving the first valid result path.
            calls.extend([
                (f"open-b-{index}", "open", {"open": [{"ref_id": path}]}),
                (f"open-c-{index}", "open", {"open": [{"ref_id": path}]}),
            ])
        results = [
            {
                "call_id": call_id,
                "name": "read",
                "content": f"READ_RESULT[{index}] {path}",
                "file_path": path,
            }
            for call_id, name, _arguments in calls
            if name == "open"
        ][:2]
        rounds.append(([_event(calls)], results))

    state = _run_scripted_build_rounds(rounds)
    all_delivered = state["calls"]

    # The proxy should make exactly one upstream call per incoming OpenCode
    # request, never consume the next model round as an internal correction.
    assert state["round"] == len(rounds) + 1, (state["round"], len(rounds) + 1)
    delivered_reads = [call for call in all_delivered if call.get("function", {}).get("name") == "read"]
    delivered_paths_by_round: list[set[str]] = []
    for response_chunks in state["outputs"][: len(rounds)]:
        paths_in_response = set()
        for call in _tool_calls_from_chunks(response_chunks):
            function = call.get("function", {})
            arguments = function.get("arguments", {}) if isinstance(function, dict) else {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if isinstance(arguments, dict) and function.get("name") == "read":
                paths_in_response.add(str(arguments.get("filePath", "")))
        delivered_paths_by_round.append(paths_in_response)
    survived_paths = {
        expected_paths[index]
        for index, actual_paths in enumerate(delivered_paths_by_round)
        if expected_paths[index] in actual_paths
    }
    assert len(survived_paths) >= 23, (
        f"only {len(survived_paths)}/24 distinct intended reads reached OpenCode"
    )
    for index, expected_path in enumerate(expected_paths):
        next_messages = state["payloads"][index + 1]["messages"]
        assert f"READ_RESULT[{index}] {expected_path}" in str(next_messages), (
            f"client request {index + 1} lacks the actual result for {expected_path}"
        )
    # Invalid search refs are blocked and named honestly; they are never
    # rewritten as paths or fake URLs.
    stream = "".join(chunk for response in state["outputs"] for chunk in response)
    assert "[blocked_tool_notice]" in stream
    assert not any(
        "turn" in str(call.get("function", {}).get("arguments", ""))
        for call in delivered_reads
    )
    # This harness scores distinct intended reads, not duplicate calls, so
    # repeats cannot inflate the 95% protocol-survival threshold.
    survival = len(survived_paths) / len(expected_paths)
    assert survival >= 0.95, f"distinct read survival={survival:.1%}, expected >=95%"


def test_long_session_history_is_bounded_by_client_results_not_proxy_internals():
    """Prevent a response from smuggling correction text as if it were a
    tool result or manufacturing evidence before the Build client replies."""
    rounds = []
    for index in range(12):
        path = f"/workspaces/MAIN/read-{index}.md"
        call = (f"c{index}", "open", {"open": [{"ref_id": path}]})
        rounds.append(([_event([call])], [{
            "call_id": f"c{index}",
            "name": "read",
            "content": f"actual OpenCode output for {path}",
            "file_path": path,
        }]))

    state = _run_scripted_build_rounds(rounds)
    for index in range(1, len(rounds) + 1):
        prior_payload = state["payloads"][index]
        serialized = json.dumps(prior_payload.get("messages", []), ensure_ascii=False)
        assert f"actual OpenCode output for /workspaces/MAIN/read-{index - 1}.md" in serialized
        assert "[native_remap_notice]" not in serialized
        assert "[loop_guard_notice]" not in serialized
