import json
from glm2api.services.translator import (
    BLOCKED_NATIVE_TOOL_NAMES,
    GLMEventAccumulator,
    compress_history_messages,
    convert_messages,
    extract_history_tool_call_signatures,
    repair_raw_tool_args,
    sanitize_control_characters,
    sanitize_tool_call_payload,
    normalize_file_path,
    strip_meta_chatter,
)
from glm2api.utils.tool_parser import strip_unparseable_call_fragments
import pytest


def test_convert_messages_injects_json_tool_prompt_and_history():
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "查天气"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city":"上海"}',
                        }
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "晴",
            },
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "查询天气",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
    )

    prompt = converted[0]["content"][0]["text"]

    assert 'Assistant: {"tool_calls":[{"name":"get_weather","arguments":{"city":"上海"}}]}[]' in prompt
    assert '[{"call_id":"call_1","name":"get_weather","content":"晴"}]' in prompt
    assert "<ml_tool_calls>" not in prompt
    assert "# TOOL USE PROTOCOL" in prompt
    assert "tool_calls" in prompt
    assert "arguments" in prompt
    assert "Parameter names must exactly match the schema." in prompt
    assert "# BLOCKED TOOLS" not in prompt
    assert "No other tools exist" in prompt
    # Re-Anchor nach Tool-Result-Runden aktiv
    assert "System instruction — highest priority" in prompt


def test_accumulator_build_response_maps_xml_to_openai_tool_calls():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"get_weather"})
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "text",
                            "text": "<|DSML|tool_calls><|DSML|invoke name=\"get_weather\">"
                            "<|DSML|parameter name=\"city\">上海</|DSML|parameter>"
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert message["content"] is None
    assert message["tool_calls"][0]["function"]["name"] == "get_weather"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"city":"上海"}'


def test_streaming_empty_response_after_blocked_tool_has_visible_fallback():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"bash"})
    accumulator.blocked_tool_attempt_names.append("open_url")
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [],
                }
            ],
        }
    )

    chunks = accumulator.finalize("finish")
    output = "".join(chunks)

    assert "unavailable tool" in output
    assert "open_url" in output
    # T-13: ein turn, der nur an einem blockierten protokoll endet, darf
    # nicht als regulaerer 'stop' ausgewiesen werden.
    assert '"finish_reason":"error"' in output


def test_non_streaming_empty_response_after_blocked_tool_has_visible_fallback():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"bash"})
    accumulator.blocked_tool_attempt_names.append("open_url")
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [],
                }
            ],
        }
    )

    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    assert "unavailable tool" in message["content"]
    assert "open_url" in message["content"]
    # T-18/C-18: leerer turn nach blockiertem aufruf ist kein erfolgreicher
    # 'stop' (parität zum stream-pfad seit diesem fix).
    assert response["choices"][0]["finish_reason"] == "error"


def test_accumulator_streaming_tool_call_emits_assistant_role_before_tool_delta():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"write"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "text",
                            "text": "<|DSML|tool_calls><|DSML|invoke name=\"write\">"
                            "<|DSML|parameter name=\"filePath\">test.txt</|DSML|parameter>"
                            "<|DSML|parameter name=\"content\"></|DSML|parameter>"
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    final_chunks = accumulator.finalize(status)

    assert chunks == []
    assert '"delta":{"role":"assistant"}' in final_chunks[0]
    assert '"tool_calls"' in final_chunks[1]
    assert '"finish_reason":"tool_calls"' in final_chunks[2]


def test_accumulator_streaming_extracts_tool_call_from_reasoning_fallback():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"write"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "think",
                            "think": "I should call the tool.\n"
                            "<|DSML|tool_calls><|DSML|invoke name=\"write\">"
                            "<|DSML|parameter name=\"filePath\">test.txt</|DSML|parameter>"
                            "<|DSML|parameter name=\"content\"></|DSML|parameter>"
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    final_chunks = accumulator.finalize(status)

    assert chunks
    assert '"reasoning_content"' in chunks[0]
    assert '"delta":{"role":"assistant"}' in final_chunks[0]
    assert '"tool_calls"' in final_chunks[1]
    assert '\\"filePath\\":\\"test.txt\\"' in final_chunks[1]


def test_accumulator_build_response_extracts_tool_call_from_reasoning_fallback():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"write"})
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "think",
                            "think": "<|DSML|tool_calls><|DSML|invoke name=\"write\">"
                            "<|DSML|parameter name=\"filePath\">test.txt</|DSML|parameter>"
                            "<|DSML|parameter name=\"content\"></|DSML|parameter>"
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert message["content"] is None
    assert message["tool_calls"][0]["function"]["name"] == "write"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"filePath":"test.txt","content":""}'


def test_sanitize_shell_command_argument_from_json_string():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": '["powershell.exe","-Command","Get-ChildItem -Force"]',
            "workdir": "E:\\Projects\\2api\\glm2api",
        },
    )

    assert cleaned == {
        "command": ["powershell.exe", "-Command", "Get-ChildItem -Force"],
        "workdir": "E:\\Projects\\2api\\glm2api",
    }


def test_sanitize_shell_command_argument_keeps_quoted_sequence_untouched():
    # Kein Windows/PowerShell-Rewrite mehr: der proxy laeuft unter Linux,
    # ein shell-command wird 1:1 durchgereicht.
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": '"powershell.exe", "-Command", "Get-ChildItem -Force"',
        },
    )

    assert cleaned == {
        "command": '"powershell.exe", "-Command", "Get-ChildItem -Force"',
    }


def test_sanitize_shell_command_argument_keeps_plain_string_untouched():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": "Get-ChildItem",
        },
    )

    assert cleaned == {
        "command": "Get-ChildItem",
    }


def test_sanitize_shell_command_argument_keeps_cmdlet_array_untouched():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": ["Get-ChildItem", "-Recurse", "-Filter", "*.txt"],
        },
    )

    assert cleaned == {
        "command": ["Get-ChildItem", "-Recurse", "-Filter", "*.txt"],
    }


def test_sanitize_shell_command_argument_keeps_native_executable_array():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": ["git", "status", "--short"],
        },
    )

    assert cleaned == {
        "command": ["git", "status", "--short"],
    }


def test_accumulator_drops_tool_preamble_and_repairs_shell_command_array():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"shell"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "text",
                            "text": "我将创建文件。\n\n"
                            '<|DSML|tool_calls><|DSML|invoke name="shell">'
                            '<|DSML|parameter name="command"><![CDATA[["powershell.exe", "-Command", "pwd"]]></|DSML|parameter>'
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    final_chunks = accumulator.finalize(status)

    assert chunks == []
    assert "我将创建文件" not in "".join(final_chunks)
    assert '"tool_calls"' in final_chunks[1]
    assert '\\"command\\":[\\"powershell.exe\\",\\"-Command\\",\\"pwd\\"]' in final_chunks[1]


def test_accumulator_defers_visible_text_when_tools_available():
    # Deferral nur bei potentiellem Tool-Protokoll im Parser-Pending;
    # normaler text streamt live (kein pauschales buffern mehr).
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"shell"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [{"type": "text", "text": "你好"}],
                }
            ],
        }
    )

    final_chunks = accumulator.finalize(status)

    # normaler text: sofort gestreamt (kein deferral ohne tool-partial)
    assert chunks != []
    assert '"content":"你好"' in chunks[0]
    assert any('"finish_reason":"stop"' in c for c in final_chunks)


def test_accumulator_defers_text_while_tool_protocol_pending():
    """Der angebrochene tool-protokoll-Anfang wird vom Parser gehalten und
    darf NICHT als Assistant-Content durchkommen. Die vorherige Fassung
    dieser Assertion ('tool' in combined) war tautologisch und hat das
    Fehlverhalten als erlaubt festgeschrieben (D-01)."""
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"bash"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [{"type": "text", "text": 'sieh vorher {"tool_calls":[{"name":"bash"'}],
                }
            ],
        }
    )
    final_chunks = accumulator.finalize(status or "stop")
    combined = "".join(chunks) + "".join(final_chunks)

    # die sichtbare prosa darf kommen ...
    assert "sieh vorher" in combined
    # ... das angebrochene protokoll-fragment darf NICHT als content raus
    assert '{"tool_calls":[{"name":"bash"' not in combined
    # ein unvollstaendiger call ist bewusst kein call — aber auch kein text
    assert "tool_calls" not in combined


def test_parity_matrix_tool_call_detection_is_chunk_independent():
    """V-01: Tool-Call-Erkennung darf nicht von der Chunk-Grenze abhaengen.
    Dasselbe Payload muss bei jedem Split identisch erkannt werden."""
    from glm2api.utils.tool_parser import StreamingToolParser, parse_tool_calls_from_text

    payloads = {
        "wrapper_inline": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]',
        "wrapper_pretty": '{\n  "tool_calls": [\n    {"name":"bash","arguments":{"command":"ls"}}\n  ]\n}[]',
        "bare_array_pretty": '[\n  {\n    "name": "bash",\n    "arguments": {"command": "ls"}\n  }\n]',
        "bare_object": '{"name":"bash","arguments":{"command":"ls"}}',
        "bare_after_text": 'Kurze Vorrede.\n{"name":"bash","arguments":{"command":"ls"}}',
    }
    for label, text in payloads.items():
        _, expected_calls = parse_tool_calls_from_text(text, {"bash", "read"})
        expected = [c["function"]["name"] for c in expected_calls]
        assert expected, f"{label}: final-parser muss den call erkennen"
        for size in (1, 3, 7, 13, 40, len(text)):
            parser = StreamingToolParser(allowed_tool_names={"bash", "read"})
            visible = "".join(
                parser.consume(text[i : i + size]) for i in range(0, len(text), size)
            )
            tail, calls = parser.flush()
            got = [c["function"]["name"] for c in calls]
            assert got == expected, f"{label} bei chunk={size}: {got} != {expected}"
            assert '"arguments"' not in visible + tail, f"{label} bei chunk={size}: protokoll geleakt"


def test_parity_matrix_stream_and_non_stream_agree_on_garbage():
    """V-05/D-06: stream- und non-stream-pfad muessen fuer dasselbe
    payload zum selben ergebnis kommen — roh-json darf in keinem pfad
    durchgehen."""
    from glm2api.utils.tool_parser import parse_tool_calls_from_text, StreamingToolParser

    payloads = [
        'Vorrede.\n{"name":"bash","arguments":{"command":"ls"',
        'Vorrede.\n{"name":"bash","arguments":{"command":"ls"}}',
        'Hier ist JSON: {"name":"service","version":"1"}',
        'User: [{"call_id":"c1","name":"bash","content":"ok"}]\nFertig.',
    ]
    for text in payloads:
        clean_final, calls_final = parse_tool_calls_from_text(text, {"bash"})
        parser = StreamingToolParser(allowed_tool_names={"bash"})
        visible = "".join(parser.consume(text[i : i + 5]) for i in range(0, len(text), 5))
        tail, calls_stream = parser.flush()
        assert [c["function"]["name"] for c in calls_final] == [
            c["function"]["name"] for c in calls_stream
        ], f"stream/non-stream weichen ab bei {text[:40]!r}"
        assert '"arguments"' not in visible + tail or not calls_final, (
            f"protokoll geleakt bei {text[:40]!r}"
        )
        assert "call_id" not in (visible + tail), f"transcript-echo geleakt bei {text[:40]!r}"


def test_mixed_valid_and_blocked_call_delivers_valid_call():
    """V-02: ein erlaubter call neben einem blockierten muss ausgeliefert
    werden, und der blockierte name muss trotzdem protokolliert sein."""
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"read"})
    text = (
        'Schritt:\n{"tool_calls":['
        '{"name":"read","arguments":{"filePath":"/etc/hostname"}},'
        '{"name":"open_url","arguments":{"url":"http://example.com"}}'
        ']}[]'
    )
    accumulator.consume_event(
        {
            "conversation_id": "conv_mixed",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }
    )
    chunks = accumulator.finalize(status="finish")
    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    names = [tc["function"]["name"] for tc in (message.get("tool_calls") or [])]
    assert "read" in names, "gueltiger call wurde verworfen"
    assert "open_url" in accumulator.blocked_tool_attempt_names, (
        "blockierter versuch wurde nicht protokolliert"
    )
    assert "undeclared tool" not in "".join(chunks), (
        "negativ-text darf gueltige calls nicht ueberschreiben"
    )


def test_accumulator_reports_unavailable_dsml_tool_instead_of_empty_response():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"shell"})
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "text",
                            "text": '<|DSML|tool_calls><|DSML|invoke name="search">'
                            '<|DSML|parameter name="search_query"><![CDATA[{"q":"阿房宫赋","recency":365}]></|DSML|parameter>'
                            "</|DSML|invoke></|DSML|tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    final_chunks = accumulator.finalize(status)

    assert chunks == []
    assert "undeclared tool" in final_chunks[0]
    assert "`search`" in final_chunks[0]
    # T-13: blockiertes protokoll ohne ergebnis -> finish_reason "error"
    assert '"finish_reason":"error"' in final_chunks[1]


def test_convert_messages_respects_tool_choice_none_and_specific():
    none_converted = convert_messages(
        messages=[{"role": "user", "content": "直接回答"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "查询天气",
                    "parameters": {"type": "object"},
                },
            }
        ],
        tool_choice="none",
    )
    none_prompt = none_converted[0]["content"][0]["text"]
    assert "# TOOL SCHEMAS" not in none_prompt

    specific_converted = convert_messages(
        messages=[{"role": "user", "content": "查天气"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "查询天气",
                    "parameters": {"type": "object"},
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "get_weather"}},
    )
    specific_prompt = specific_converted[0]["content"][0]["text"]
    assert "You must call exactly `get_weather`." in specific_prompt


def test_convert_messages_filters_native_url_tools_and_reinforces_tool_awareness():
    converted = convert_messages(
        messages=[{"role": "user", "content": "打开 https://example.com"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "open_url",
                    "description": "Open URL",
                    "parameters": {"type": "object"},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp__CherryFetch__fetchJson",
                    "description": "Fetch JSON",
                    "parameters": {"type": "object"},
                },
            },
        ],
        blocked_tool_names=BLOCKED_NATIVE_TOOL_NAMES,
    )

    prompt = converted[0]["content"][0]["text"]

    assert "Tool: open_url" not in prompt
    assert "Server-side native tools" not in prompt
    assert "Tool: mcp__CherryFetch__fetchJson" in prompt
    assert "no browser, no open_url, no web.search" in prompt


def test_convert_messages_drops_blocked_tool_call_history():
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "打开 https://example.com"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_bad",
                        "function": {
                            "name": "open_url",
                            "arguments": '{"url":"https://example.com"}',
                        },
                    }
                ],
            },
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__CherryFetch__fetchJson",
                    "description": "Fetch JSON",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    prompt = converted[0]["content"][0]["text"]

    assert "name=\"open_url\"" not in prompt
    assert "Tool: mcp__CherryFetch__fetchJson" in prompt


def test_convert_messages_repairs_cherry_fetch_url_and_keeps_its_tool_result():
    # T-15: der call wurde normalisiert (param_name -> url mit fallback-url).
    # Das ERGEBNIS gehoert zu genau diesem, vom client ausgefuehrten call
    # und wird zurueckgegeben — auch wenn es ein Fehler ist. Vorher wurde
    # es verworfen, damit bekam das Modell gar kein Feedback und glaubte,
    # der Schritt sei erfolgreich. Neu ist der FEHLER sichtbar, mit dem der
    # Modell den naechsten Versuch korrigieren kann.
    converted = convert_messages(
        messages=[
            {
                "role": "user",
                "content": "使用工具访问 https://opendata.baidu.com/api.php?query=1.1.1.1&co=&resource_id=6006&oe=utf8",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_bad",
                        "function": {
                            "name": "mcp__CherryFetch__fetchJson",
                            "arguments": '{"param_name":"url"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_bad",
                "content": "{\"isError\":true,\"content\":[{\"type\":\"text\",\"text\":\"Invalid input: expected string, received undefined\"}]}",
            },
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__CherryFetch__fetchJson",
                    "description": "Fetch a JSON file from a URL",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            }
        ],
    )

    prompt = converted[0]["content"][0]["text"]

    assert (
        '{"tool_calls":[{"name":"mcp__CherryFetch__fetchJson","arguments":{"url":"https://opendata.baidu.com/api.php?query=1.1.1.1&co=&resource_id=6006&oe=utf8"}}]}[]'
        in prompt
    )
    # T-15: das fehler-ergebnis des reparierten calls wird mitgeliefert
    # (call-id passt) — das Modell sieht den Fehler und kann korrigieren.
    assert "expected string, received undefined" in prompt


def test_accumulator_repairs_param_name_only_tool_call_with_fallback_url():
    accumulator = GLMEventAccumulator(
        model="glm-test",
        allowed_tool_names={"mcp__CherryFetch__fetchJson"},
        fallback_tool_url="https://opendata.baidu.com/api.php?query=1.1.1.1&co=&resource_id=6006&oe=utf8",
    )
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "text",
                            "text": "<ml_tool_calls><ml_tool_call><ml_tool_name>mcp__CherryFetch__fetchJson</ml_tool_name>"
                            "<ml_parameters><param_name><![CDATA[url]]></param_name></ml_parameters>"
                            "</ml_tool_call></ml_tool_calls>",
                        }
                    ],
                }
            ],
        }
    )

    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert message["content"] is None
    assert message["tool_calls"][0]["function"]["name"] == "mcp__CherryFetch__fetchJson"
    assert (
        message["tool_calls"][0]["function"]["arguments"]
        == '{"url":"https://opendata.baidu.com/api.php?query=1.1.1.1&co=&resource_id=6006&oe=utf8"}'
    )


def test_extract_history_tool_call_signatures():
    sigs = extract_history_tool_call_signatures([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "write", "arguments": '{"filePath": "/tmp/x.txt", "content": "hello"}'}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "assistant", "tool_calls": [{"id": "call_2", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}]},
    ])
    assert sigs == {
        'write:{"content":"hello","filePath":"/tmp/x.txt"}',
        'bash:{"command":"ls"}',
    }


def test_accumulator_drops_echoed_native_tool_call():
    sigs = {'write:{"content":"hello","filePath":"/tmp/x.txt"}'}
    accumulator = GLMEventAccumulator(
        model="glm-test",
        allowed_tool_names={"read", "write"},
        history_tool_call_signatures=sigs,
    )
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {"type": "tool_calls", "tool_calls": {"id": "call_echo_1", "name": "write", "arguments": '{"content": "hello", "filePath": "/tmp/x.txt"}'}},
                        {"type": "tool_calls", "tool_calls": {"id": "call_echo_2", "name": "write", "arguments": '{"filePath":"/tmp/x.txt","content":"hello"}'}},
                        {"type": "tool_calls", "tool_calls": {"id": "call_new", "name": "read", "arguments": '{"filePath":"/tmp/x.txt"}'}},
                    ],
                }
            ],
        }
    )
    response = accumulator.build_response()
    tool_calls = response["choices"][0]["message"].get("tool_calls", [])
    assert [tc["function"]["name"] for tc in tool_calls] == ["read"]
    assert response["choices"][0]["finish_reason"] == "tool_calls"


def test_accumulator_signature_dedup_for_repeated_native_parts():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"read"})
    for i in range(36):
        accumulator.consume_event(
            {
                "conversation_id": "conv_1",
                "parts": [
                    {
                        "logic_id": "1",
                        "content": [
                            {"type": "tool_calls", "tool_calls": {"id": f"call_dup_{i}", "name": "read", "arguments": '{"filePath":"/a"}'}}
                        ],
                    }
                ],
            }
        )
    response = accumulator.build_response()
    tool_calls = response["choices"][0]["message"].get("tool_calls", [])
    assert len(tool_calls) == 1


def test_accumulator_ignores_unallowed_native_tool_call_blocks():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"get_weather"})
    accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": {
                                "id": "call_open_url",
                                "name": "open_url",
                                "arguments": '{"url":"https://example.com"}',
                            },
                        }
                    ],
                }
            ],
        }
    )

    response = accumulator.build_response()
    message = response["choices"][0]["message"]

    # T-18/C-18: der non-stream-pfad weist einen blockierten native-call
    # jetzt genauso aus wie der stream-pfad — 'error', nicht 'stop'. Vorher
    # gab es hier eine stream/non-stream-paritaetsabweichung, die die tests
    # festgeschrieben hatten.
    assert response["choices"][0]["finish_reason"] == "error"
    assert "tool_calls" not in message


def test_accumulator_keeps_markdown_block_separators_between_parts():
    accumulator = GLMEventAccumulator(model="glm-test")

    first_chunks, _ = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [
                        {"type": "text", "text": "## 查询结果：IP 地址 `1.1.1.1` 的归属地信息"},
                    ],
                }
            ],
        }
    )
    second_chunks, _ = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "2",
                    "content": [
                        {"type": "text", "text": "| 字段 | 值 |\n|---|---|\n| 查询 IP | `1.1.1.1` |"},
                    ],
                }
            ],
        }
    )

    assert first_chunks
    assert second_chunks[0].find("\\n\\n") != -1

    response = accumulator.build_response()
    assert response["choices"][0]["message"]["content"] == (
        "## 查询结果：IP 地址 `1.1.1.1` 的归属地信息\n\n"
        "| 字段 | 值 |\n|---|---|\n| 查询 IP | `1.1.1.1` |"
    )


def test_merge_part_texts_finish_without_part_status_no_duplicate():
    # Regression K-1: finish-status nur top-level im event, nicht im part —
    # der volltext darf den akkumulierten delta-text nicht duplizieren
    accumulator = GLMEventAccumulator(model="glm-test")
    accumulator.consume_event(
        {"conversation_id": "c", "parts": [{"logic_id": "1", "content": [{"type": "text", "text": "Hallo "}]}]}
    )
    accumulator.consume_event(
        {"conversation_id": "c", "parts": [{"logic_id": "1", "content": [{"type": "text", "text": "Welt"}]}]}
    )
    accumulator.consume_event(
        {"conversation_id": "c", "status": "finish", "parts": [{"logic_id": "1", "content": [{"type": "text", "text": "Hallo Welt"}]}]}
    )
    response = accumulator.build_response()
    assert response["choices"][0]["message"]["content"] == "Hallo Welt"


def test_merge_part_texts_finish_with_part_status_still_works():
    accumulator = GLMEventAccumulator(model="glm-test")
    accumulator.consume_event(
        {"conversation_id": "c", "parts": [{"logic_id": "1", "content": [{"type": "text", "text": "A"}]}]}
    )
    accumulator.consume_event(
        {"conversation_id": "c", "parts": [{"logic_id": "1", "status": "finish", "content": [{"type": "text", "text": "AB"}]}]}
    )
    response = accumulator.build_response()
    assert response["choices"][0]["message"]["content"] == "AB"


def test_convert_messages_keeps_tool_result_for_id_repaired_call():
    # Regression N-2: tool_call OHNE id bekommt call_repaired_N — die
    # tool-result mit genau dieser id darf nicht verworfen werden
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "uhrzeit?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "get_time", "arguments": '{"timezone":"Europe/Berlin"}'}}],
            },
            {"role": "tool", "tool_call_id": "call_repaired_0", "content": "15:23 MESZ"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "zeit",
                    "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}},
                },
            }
        ],
    )
    prompt = converted[0]["content"][0]["text"]
    assert "15:23 MESZ" in prompt


def test_sanitize_bash_repairs_broken_python_dict_quotes():
    # LLM-Quoting-Versagen: x'key' statt x['key'] in python-commands.
    # Compile-Oracle repariert NUR wenn das resultat wirklich kompiliert.
    broken = 'python3 -c "\nimport json\ncreds = json.load(f)\nexpiry = creds\'expiry_date\' / 1000\nx = {\'a\': creds\'access_token\', \'r\': creds\'refresh_token\'}\n"'
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": json.dumps({"command": broken})}}]},
        ],
        tools=[{"type": "function", "function": {"name": "bash", "description": "run", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}],
    )
    prompt = converted[0]["content"][0]["text"]
    assert "creds['expiry_date']" in prompt
    assert "creds['access_token']" in prompt


def test_sanitize_bash_never_touches_working_python():
    good = "python3 -c \"x = 'a' + 'b'\""
    payload = sanitize_tool_call_payload("bash", {"command": good})
    assert payload["command"] == good
    good2 = "python3 -c \"print(x['key'])\""
    payload2 = sanitize_tool_call_payload("bash", {"command": good2})
    assert payload2["command"] == good2
    # nicht-python unberuehrt
    payload3 = sanitize_tool_call_payload("bash", {"command": "echo 'hello'"})
    assert payload3["command"] == "echo 'hello'"


def test_repair_skips_doubly_broken_commands():
    # wenn neben den quotes auch die kommentar-struktur zerstoert ist,
    # greift das repair nicht (oracle-verbatim) — kein wildes umschreiben
    doubly_broken = 'python3 -c "\n# Kopf\n     kein kommentar\nx = creds\'k\'\n"'
    from glm2api.services.translator import repair_python_command_quotes
    assert repair_python_command_quotes(doubly_broken) == doubly_broken


def test_consume_event_defers_text_delta_containing_protocol_fragment():
    """Re-Befund C (22:35, Doppelausgabe Call+Text): Ein Text-Delta, das
    Protokoll-Fragmente enthält, darf nie sofort als content-Delta raus —
    es muss ins Deferred-Buffer (finalize safety-net parst + cleant dort)."""
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"bash"})
    chunks, _ = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [{"type": "text", "text": "Ergebnis: "}],
                }
            ],
        }
    )
    chunks2, _ = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "2",
                    "content": [
                        {
                            "type": "text",
                            "text": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]',
                        }
                    ],
                }
            ],
        }
    )
    def _payload(c):
        if c.startswith("data: "):
            c = c[6:]
        c = c.strip()
        if not c or c == "[DONE]":
            return {"choices": [{}]}
        return json.loads(c)


    all_content = "".join(
        _payload(c)["choices"][0]["delta"].get("content", "")
        for c in chunks + chunks2
        if _payload(c)["choices"][0].get("delta")
    )
    assert '{"tool_calls"' not in all_content

    final_chunks = accumulator.finalize("finish")
    final_content = "".join(
        _payload(c)["choices"][0].get("delta", {}).get("content", "")
        for c in final_chunks
        if _payload(c)["choices"][0].get("delta")
    )
    finish_reasons = [
        _payload(c)["choices"][0].get("finish_reason") for c in final_chunks
    ]
    assert '{"tool_calls"' not in final_content
    assert "tool_calls" in finish_reasons


def test_compress_history_noop_under_budget():
    from glm2api.services.translator import compress_history_messages

    messages = [
        {"role": "system", "content": "Du bist hilfreich."},
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hi!"},
    ]
    assert compress_history_messages(messages, 100000) == messages
    assert compress_history_messages(messages, 0) == messages  # 0 = deaktiviert


def test_compress_history_compacts_older_rounds_keeps_recent_intact():
    from glm2api.services.translator import compress_history_messages

    messages: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(40):
        messages.append({"role": "user", "content": f"Runde {i}: " + "x" * 500})
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {"name": "bash", "arguments": f'{{"command": "echo {i}"}}'},
                    }
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"call_{i}", "name": "bash", "content": f"output {i}" * 20})
    messages.append({"role": "user", "content": "Finale Frage?"})

    compressed = compress_history_messages(messages, 8000)
    assert compressed is not messages
    assert len(compressed) < len(messages)
    # summary-eintrag ganz vorn
    assert compressed[0]["role"] == "user"
    assert "compacted" in str(compressed[0]["content"])
    # die letzte user-nachricht bleibt unangetastet
    assert compressed[-1] == {"role": "user", "content": "Finale Frage?"}
    # kein verwaistes tool-result: jeder tool-rolle in compressed geht ein
    # assistant-mit-tool_calls voraus
    for idx, msg in enumerate(compressed):
        if msg.get("role") == "tool":
            assert idx > 0 and compressed[idx - 1].get("role") == "assistant" and compressed[idx - 1].get("tool_calls")
    # budget grob eingehalten (summary-snippets + letzte runden)
    total = 0
    for msg in compressed:
        content = msg.get("content")
        total += len(content) if isinstance(content, str) else 0
        calls = msg.get("tool_calls")
        if isinstance(calls, list):
            import json as _json

            total += len(_json.dumps(calls))
    assert total < 20000


def test_sanitize_tool_call_payload_unpacks_stringified_json_array_and_dict():
    # Stringified array (e.g. questions: "[{...}]")
    raw_array = json.dumps([{"question": "Was tun?", "header": "Auswahl", "options": []}])
    payload = sanitize_tool_call_payload("question", {"questions": raw_array})
    assert isinstance(payload, dict)
    assert isinstance(payload["questions"], list)
    assert payload["questions"][0]["question"] == "Was tun?"

    # Stringified dict
    raw_dict = json.dumps({"key": "val"})
    payload_dict = sanitize_tool_call_payload("custom_tool", {"meta": raw_dict})
    assert isinstance(payload_dict, dict)
    assert isinstance(payload_dict["meta"], dict)
    assert payload_dict["meta"]["key"] == "val"

    # Plain strings remain untouched
    payload_plain = sanitize_tool_call_payload("read", {"filePath": "/path/to/file"})
    assert isinstance(payload_plain, dict)
    assert payload_plain["filePath"] == "/path/to/file"


def test_conversation_history_compression_respects_budget():
    """Die Nachricht, die das Budget sprengt, wird summarisiert statt
    unveraendert weitergereicht (frueher: off-by-one behielt sie vollstaendig
    und das Budget riess um ein Vielfaches)."""
    messages = [
        {"role": "user", "content": "alte runde"},
        {"role": "user", "content": "B" * 5000},
        {"role": "user", "content": "neueste frage"},
    ]

    compressed = compress_history_messages(messages, 100)

    assert len(compressed) == 2
    assert "compacted" in str(compressed[0]["content"])
    assert compressed[-1]["content"] == "neueste frage"
    # die budget-sprengende message darf nicht mehr roh im output stehen
    assert all("B" * 5000 not in str(entry.get("content", "")) for entry in compressed)


def test_conversation_history_compression_always_keeps_newest_message():
    messages = [
        {"role": "user", "content": "a" * 1000},
        {"role": "user", "content": "b" * 1000},
    ]

    compressed = compress_history_messages(messages, 100)

    assert compressed[-1]["content"] == "b" * 1000


def test_conversation_history_compression_never_splits_assistant_tool_pair():
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "1", "function": {"name": "read", "arguments": "{}"}}],
    }
    tool_result = {"role": "tool", "tool_call_id": "1", "content": "R" * 100}
    newest = {"role": "user", "content": "x" * 100}

    compressed = compress_history_messages([assistant, tool_result, newest], 150)

    # paar entweder komplett roh oder komplett in der summary — nie einzeln
    assert [entry["role"] for entry in compressed] == ["user", "user"]
    assert compressed[-1]["content"] == "x" * 100


def test_compress_history_disabled_returns_messages_unchanged():
    messages = [{"role": "user", "content": "hallo"}]

    assert compress_history_messages(messages, 0) is messages


def test_repair_raw_tool_args_preserves_utf8_umlauts():
    """Regression: der _raw-repairpfad nutzte .decode('unicode_escape')
    (latin-1-semantik) und machte aus 'hübsch' -> 'hÃ¼bsch'."""
    raw = '"filePath": "/tmp/x.py", "content": "wort = \\"hübsch\\"\\nprint(wort)"'

    repaired = repair_raw_tool_args("write", raw)

    assert repaired is not None
    assert repaired["content"] == 'wort = "hübsch"\nprint(wort)'


def test_repair_raw_tool_args_decodes_literal_control_char_escape():
    """Modell emittiert \\u0014 statt 'ü' (THEMA 3). Der repairpfad darf das
    escape nicht zu einem echten steuerzeichen materialisieren — der
    C0-sanitizer ersetzt es anschliessend durch '?'."""
    raw = '"filePath": "/tmp/x.py", "content": "zur\\u0014ck"'

    repaired = repair_raw_tool_args("write", raw)
    assert repaired is not None
    assert "\x14" in str(repaired["content"])

    sanitized = sanitize_tool_call_payload("write", repaired)
    assert sanitized is not None
    assert sanitized["content"] == "zur?ck"


def test_repair_raw_tool_args_bash_command_preserves_umlauts():
    raw = '"command": "echo \\"grüße\\" && ls"'

    repaired = repair_raw_tool_args("bash", raw)

    assert repaired is not None
    assert repaired["command"] == 'echo "grüße" && ls'


def test_sanitize_control_characters_replaces_c0_but_keeps_whitespace():
    cleaned, count = sanitize_control_characters("a\x00b\x14c\nd\te\rf\x7f")

    assert cleaned == "a?b?c\nd\te\rf?"
    assert count == 3


def test_sanitize_control_characters_keeps_valid_utf8():
    text = "schöne Grüße — 日本語 ✅"

    cleaned, count = sanitize_control_characters(text)

    assert cleaned == text
    assert count == 0


def test_sanitize_tool_call_payload_replaces_control_chars_in_nested_arguments():
    cleaned = sanitize_tool_call_payload(
        "bash",
        {"command": "echo \x05 ok", "notes": ["a\x00b", {"deep": "c\x14d"}]},
    )

    assert cleaned is not None
    assert cleaned["command"] == "echo ? ok"
    assert cleaned["notes"] == ["a?b", {"deep": "c?d"}]


def test_sanitize_tool_call_payload_keeps_valid_utf8_content():
    cleaned = sanitize_tool_call_payload(
        "write",
        {"filePath": "/tmp/übung.md", "content": "Grüße aus München — 日本語"},
    )

    assert cleaned is not None
    assert cleaned["content"] == "Grüße aus München — 日本語"


def test_accumulator_sanitizes_control_chars_in_visible_text():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names=None)
    accumulator.consume_event(
        {
            "conversation_id": "conv_cc",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [{"type": "text", "text": "zur\x14ck bitte"}],
                }
            ],
        }
    )

    response = accumulator.build_response()
    content = response["choices"][0]["message"]["content"]

    assert content == "zur?ck bitte"


def test_usage_is_estimated_instead_of_placeholder():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names=None, prompt_chars=4000)
    accumulator.consume_event(
        {
            "conversation_id": "conv_usage",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [{"type": "text", "text": "h" * 800}],
                }
            ],
        }
    )

    usage = accumulator.build_response()["usage"]

    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] >= 200
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_finalize_reports_estimated_usage():
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names=None, prompt_chars=1200)
    accumulator.consume_event(
        {
            "conversation_id": "conv_usage2",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [{"type": "text", "text": "antwort"}],
                }
            ],
        }
    )

    chunks = accumulator.finalize(status="finish")

    assert '"prompt_tokens":300' in chunks[-2]
    assert '"total_tokens"' in chunks[-2]


def test_build_tool_call_instructions_includes_language_lock_and_no_preamble():
    from glm2api.utils.tool_protocol import build_tool_call_instructions, TOOL_FORMAT_REMINDER

    instructions = build_tool_call_instructions(["question", "read"])
    assert "When calling a tool, do NOT output conversational text" in instructions
    assert "Language consistency" in instructions
    assert "NEVER output internal monologue, reasoning, or responses in Chinese" in instructions

    assert "Do not output any preamble, commentary, or thoughts in Chinese" in TOOL_FORMAT_REMINDER


def test_native_open_maps_to_read_when_target_is_path():
    from glm2api.services.translator import map_native_open_tool_call, GLMEventAccumulator

    mapped = map_native_open_tool_call(
        '{"open":[{"ref_id": "/workspaces/benchmark", "lineno": 1}]}',
        allowed_tool_names={"bash", "read"},
    )
    assert mapped == ("read", {"filePath": "/workspaces/benchmark"})

    acc = GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "read"})
    event = {
        "status": "init",
        "parts": [
            {
                "id": "p1",
                "logic_id": "l1",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": "call_123",
                            "name": "open",
                            "arguments": '{"open":[{"ref_id": "/workspaces/benchmark", "lineno": 1}]}',
                        },
                    }
                ],
            }
        ],
    }
    chunks, status = acc.consume_event(event)
    assert status != "intervene"
    assert acc.blocked_tool_attempt_names == []
    assert len(acc._server_side_tool_calls) == 1
    assert acc._server_side_tool_calls[0]["function"]["name"] == "read"
    assert "/workspaces/benchmark" in str(acc._server_side_tool_calls[0]["function"]["arguments"])


def test_native_sandbox_maps_to_bash_when_bash_allowed():
    from glm2api.services.translator import map_native_sandbox_tool_call, GLMEventAccumulator

    mapped = map_native_sandbox_tool_call(
        '{"code": "import json\\ndata = json.dumps({\'a\': 1})\\nprint(data)"}',
        allowed_tool_names={"bash", "read"},
    )
    assert mapped is not None
    assert mapped[0] == "bash"
    assert "json.dumps" in mapped[1]["command"]


def test_native_sandbox_drops_side_effect_free_thinking_scratchpad():
    """Live-Fall 2026-09-25 (ses_f2a4cdf04ffewG5KS0GHp98eN5): das Modell
    nutzt den sandbox-kanal als denk-kratzer und sendet print("x"),
    print("done") & co. Ohne diesen filter wurden daraus 40 echte
    bash-aufrufe in einem turn."""
    from glm2api.services.translator import map_native_sandbox_tool_call, is_dummy_sandbox_code

    # denk-kratzer: keine wirkung
    for scratch in (
        'print("x")',
        'print("done")',
        "print('phase3-start')",
        "print('use write tool now')",
        "print('a')\nprint('b')\nprint('c')",
        "assert 1 == 1",
        "pass",
    ):
        assert is_dummy_sandbox_code('{"code": %s}' % __import__("json").dumps(scratch)) is True
        assert map_native_sandbox_tool_call('{"code": %s}' % __import__("json").dumps(scratch), {"bash"}) is None

    # echte aufgaben bleiben ausfuehrbar
    for work in (
        "import os\nos.makedirs('/tmp/x', exist_ok=True)",
        "x = 1 + 1\nopen('/tmp/v.txt','w').write(str(x))",
        "import subprocess\nsubprocess.run(['ls'])",
    ):
        assert is_dummy_sandbox_code('{"code": %s}' % __import__("json").dumps(work)) is False

    mapped_shell = map_native_sandbox_tool_call(
        '{"code": "pytest -v tests"}',
        allowed_tool_names={"bash", "read"},
    )
    assert mapped_shell == ("bash", {"command": "pytest -v tests"})

    mapped_no_bash = map_native_sandbox_tool_call(
        '{"code": "print(1)"}',
        allowed_tool_names={"read", "write"},
    )
    assert mapped_no_bash is None

    acc = GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "write"})
    event = {
        "status": "init",
        "parts": [
            {
                "id": "p2",
                "logic_id": "l2",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": "call_sb1",
                            "name": "execute_sandbox_code",
                            "arguments": '{"code": "pytest tests -q"}',
                        },
                    }
                ],
            }
        ],
    }
    chunks, status = acc.consume_event(event)
    assert status != "intervene"
    assert acc.blocked_tool_attempt_names == []
    assert len(acc._server_side_tool_calls) == 1
    assert acc._server_side_tool_calls[0]["function"]["name"] == "bash"
    assert "pytest tests -q" in str(acc._server_side_tool_calls[0]["function"]["arguments"])


def test_dummy_sandbox_code_is_dropped():
    from glm2api.services.translator import GLMEventAccumulator, is_dummy_sandbox_code

    assert is_dummy_sandbox_code('{"code": "print(\'noop\')"}')
    assert is_dummy_sandbox_code('{"code": "print(\'STOP using sandbox. Use write tool now.\')"}')
    assert is_dummy_sandbox_code('{"code": "raise SystemExit"}')
    assert is_dummy_sandbox_code('{"code": "placeholder"}')
    assert not is_dummy_sandbox_code('{"code": "pytest tests -q"}')

    acc = GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "write"})
    event = {
        "status": "init",
        "parts": [
            {
                "id": "p_dummy",
                "logic_id": "l_dummy",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": "call_sb_dummy",
                            "name": "execute_sandbox_code",
                            "arguments": '{"code": "print(\'noop\')"}',
                        },
                    }
                ],
            }
        ],
    }
    chunks, status = acc.consume_event(event)
    assert status != "intervene"
    assert len(acc._server_side_tool_calls) == 0


def test_repair_raw_tool_args_fixes_unescaped_triple_quotes():
    from glm2api.services.translator import sanitize_tool_calls

    broken_tool_calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {
                "name": "write",
                "arguments": {
                    "_raw": '{"filePath":"/workspaces/benchmark/ledgervault/store.py","content":"\\"\\"\\"docstring\\"\\"\\"\\ndef foo(): pass\\n"}'
                },
            },
        }
    ]
    sanitized = sanitize_tool_calls(broken_tool_calls)
    assert len(sanitized) == 1
    args = json.loads(sanitized[0]["function"]["arguments"])
    assert args["filePath"] == "/workspaces/benchmark/ledgervault/store.py"
    assert "def foo(): pass" in args["content"]


def test_sanitize_write_preserves_json_string_and_serializes_dict():
    from glm2api.services.translator import sanitize_tool_calls

    tool_calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {
                "name": "write",
                "arguments": {
                    "filePath": "rules.json",
                    "content": '{"max_error_rate_percent": 20}',
                },
            },
        },
        {
            "id": "c2",
            "type": "function",
            "function": {
                "name": "write",
                "arguments": {
                    "filePath": "rules2.json",
                    "content": {"max_error_rate_percent": 20},
                },
            },
        },
    ]
    sanitized = sanitize_tool_calls(tool_calls)
    assert len(sanitized) == 2
    args1 = json.loads(sanitized[0]["function"]["arguments"])
    assert isinstance(args1["content"], str)
    assert '{"max_error_rate_percent": 20}' in args1["content"]

    args2 = json.loads(sanitized[1]["function"]["arguments"])
    assert isinstance(args2["content"], str)
    assert '"max_error_rate_percent": 20' in args2["content"]


def test_sanitize_filePath_strips_file_uri_scheme():
    from glm2api.services.translator import sanitize_tool_calls

    tool_calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {
                "name": "read",
                "arguments": {
                    "filePath": "file:///workspaces/benchmark/src/doc_parser.py",
                },
            },
        }
    ]
    sanitized = sanitize_tool_calls(tool_calls)
    args = json.loads(sanitized[0]["function"]["arguments"])
    assert args["filePath"] == "/workspaces/benchmark/src/doc_parser.py"



def test_strip_meta_chatter_removes_hallucinated_transcript_echo():
    """Regression (Live-Fall ses_f2bc23762ffeoOkPYHAoqhwpwm): das Modell
    halluzinierte sein eigenes konversations-format inkl. erfundener
    tool-result-zeilen ('User: [{"call_id":"call_webfetch_rules",...}]')."""
    text = (
        'User: [{"call_id":"call_webfetch_rules","name":"webfetch","content":"{\\"ok\\":true}"}]\n'
        'User: [{"call_id":"call_pkill","name":"bash","content":"stopped"}]\n'
        'Hier ist der Abschlussbericht. Alles erledigt.'
    )

    cleaned = strip_meta_chatter(text)

    assert cleaned == "Hier ist der Abschlussbericht. Alles erledigt."


def test_strip_meta_chatter_keeps_normal_user_quotes():
    text = 'User: das ist eine normale zustandsmeldung\nAlles ok'

    cleaned = strip_meta_chatter(text)

    assert cleaned == text


def test_accumulator_strips_transcript_echo_from_final_text():
    """Live-Fall ses_f2bc23762ffeoOkPYHAoqhwpwm: das Modell schrieb sein
    eigenes konversations-format (User: [{"call_id":...}]) als antwort."""
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"read", "bash"})
    accumulator.consume_event(
        {
            "conversation_id": "conv_echo",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                'User: [{"call_id":"call_x","name":"read","content":"datei.txt"}]\n'
                                'Assistant: erledigt, alle Phasen abgeschlossen.'
                            ),
                        }
                    ],
                }
            ],
        }
    )

    response = accumulator.build_response()
    content = response["choices"][0]["message"]["content"]

    assert "call_id" not in content
    assert content == "Assistant: erledigt, alle Phasen abgeschlossen."


def test_native_open_mapping_rejects_tool_name_in_path():
    """Live-Fall 2026-09-25 (ses_f2a64f037ffeqVK86xKyAQYdSp): das Modell
    schrieb den Toolnamen selbst ins Argument
    ({'ref_id': 'read /workspaces/benchmark.md'}). Das ist eine Anweisung,
    kein Pfad — der Aufruf wurde zu einem Leseversuch auf einen nicht
    existierenden Dateinamen."""
    from glm2api.services.translator import map_native_open_tool_call

    assert map_native_open_tool_call({"ref_id": "read /workspaces/benchmark.md"}, {"read"}) is None
    assert map_native_open_tool_call({"ref_id": "bash ls -la"}, {"read"}) is None
    # echte ziele bleiben unberuehrt
    assert map_native_open_tool_call({"ref_id": "/workspaces/benchmark.md"}, {"read"}) == (
        "read",
        {"filePath": "/workspaces/benchmark.md"},
    )
    assert map_native_open_tool_call({"ref_id": "https://example.com"}, {"webfetch"}) == (
        "webfetch",
        {"url": "https://example.com"},
    )


def test_sandbox_mapping_is_capped_per_turn():
    """Schutznetz: ein entarteter turn darf nicht unbegrenzt sandbox-calls
    in echte bash-aufrufe umwandeln (live-fall: 40 calls)."""
    from glm2api.services.translator import GLMEventAccumulator, _MAX_MAPPED_SANDBOX_CALLS

    accumulator = GLMEventAccumulator(
        model="glm-test",
        allowed_tool_names={"bash", "read", "write"},
        fallback_tool_url=None,
    )
    parts = []
    for index in range(_MAX_MAPPED_SANDBOX_CALLS + 5):
        parts.append({
            "logic_id": f"p{index}",
            "tool_calls": {
                f"c{index}": {
                    "name": "execute_sandbox_code",
                    "arguments": json.dumps({"code": f"import os\nx{index} = {index}"}),
                }
            },
        })
    accumulator.consume_event({
        "conversation_id": "conv_cap",
        "status": "finish",
        "parts": parts,
    })
    message = accumulator.build_response()["choices"][0]["message"]

    assert len(message.get("tool_calls") or []) <= _MAX_MAPPED_SANDBOX_CALLS


def test_output_limit_caps_response_and_reports_length():
    """Der Upstream kennt keine Ausgabegrenze — der Proxy setzt sie selbst.
    Live-Fall 2026-09-25: 30k Zeichen / 24 Calls in einem Turn."""
    accumulator = GLMEventAccumulator(
        model="glm-test", allowed_tool_names=None, max_output_tokens=200,
    )
    chunks = []
    for index in range(50):
        emitted, _status = accumulator.consume_event({
            "conversation_id": "c_limit",
            "status": "update",
            "parts": [{"logic_id": f"p{index}", "status": "update",
                        "content": [{"type": "text", "text": "A" * 100}]}],
        })
        chunks.extend(emitted)

    final = accumulator.finalize(status="finish")
    payload = "".join(final)
    content = json.loads(final[-2][6:].strip())

    # 200 Token ~ 800 Zeichen; mehr wird nicht ausgeliefert
    assert sum(len(json.loads(c[6:].strip())["choices"][0]["delta"].get("content") or "")
               for c in chunks if c.startswith("data: ") and "[DONE]" not in c) <= 800
    assert accumulator.output_limit_reached is True
    assert content["choices"][0]["finish_reason"] == "length"


def test_output_limit_drops_incomplete_tool_call():
    accumulator = GLMEventAccumulator(
        model="glm-test", allowed_tool_names={"write"}, max_output_tokens=200,
    )
    # Text, der mitten im call-json abgeschnitten wird
    payload = "Hier kommt der Plan. " + '{"tool_calls":[{"name":"write","arguments":{"filePath":"/a.py","content":"' + ("x" * 5000) + '}}]}[]'
    for index in range(0, len(payload), 400):
        accumulator.consume_event({
            "conversation_id": "c_limit_call",
            "status": "update",
            "parts": [{"logic_id": f"p{index}", "status": "update",
                        "content": [{"type": "text", "text": payload[index:index + 400]}]}],
        })
    final = accumulator.finalize(status="finish")
    body = json.loads(final[-2][6:].strip())
    message = accumulator.build_response()["choices"][0]["message"]

    # ein abgeschnittener write-call darf NICHT ausgeliefert werden
    assert not (message.get("tool_calls") or []), "unvollstaendiger call wurde ausgeliefert"
    assert body["choices"][0]["finish_reason"] in {"length", "error", "stop"}


def test_output_limit_caps_final_text_not_only_deltas():
    """Regression 2026-09-25: die delta-kappung in consume_event() greift
    nicht fuer den aus dem cache zusammengesetzten endtext. Ohne diese
    zweite Kappung lieferte der Proxy finish_reason=length alongside
    12.367 ungekappte zeichen (max_tokens=30)."""
    accumulator = GLMEventAccumulator(
        model="glm-test", allowed_tool_names=None, max_output_tokens=200,
    )
    for index in range(30):
        accumulator.consume_event({
            "conversation_id": "c_final_cap",
            "status": "update",
            "parts": [{"logic_id": f"p{index}", "status": "update",
                        "content": [{"type": "text", "text": "B" * 1000}]}],
        })
    accumulator.finalize(status="finish")
    body = accumulator.build_response()

    content = body["choices"][0]["message"]["content"]
    assert len(content) <= 200 * 4, f"endtext ungekappt: {len(content)} zeichen"
    assert body["choices"][0]["finish_reason"] == "length"


# --- P1-Restgruppe (2026-09-25): T-05, T-06, T-10, T-12, T-15 -----------


def _event(cid, logic_id, text=None, think=None, status="update"):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if think is not None:
        content.append({"type": "think", "think": think})
    return {
        "conversation_id": cid,
        "status": status,
        "parts": [{"logic_id": logic_id, "status": status, "content": content}],
    }


def _call_names(response):
    message = response["choices"][0]["message"]
    return [call["function"]["name"] for call in (message.get("tool_calls") or [])]


def test_reasoning_call_is_kept_next_to_text_call_streaming():
    """T-05: der reasoning-fallback lief NUR, wenn der textparser nichts
    fand. Bei read im Text + write im Reasoning kam nur read an — der
    zweite Aufruf ging still verloren, obwohl das Modell ihn gemacht hat."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "write"})
    accumulator.consume_event(
        _event("c", "p1", text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}')
    )
    accumulator.consume_event(
        _event("c", "p2", think='Dann schreibe ich: {"tool_calls":[{"name":"write","arguments":{"filePath":"/b.py","content":"x"}}]}')
    )
    accumulator.finalize("finish")

    assert _call_names(accumulator.build_response()) == ["read", "write"]


def test_reasoning_call_is_kept_next_to_text_call_non_streaming():
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "write"})
    accumulator.consume_event(
        _event("c", "p1", text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}', status="finish")
    )
    accumulator.consume_event(
        _event("c", "p2", think='Dann schreibe ich: {"tool_calls":[{"name":"write","arguments":{"filePath":"/b.py","content":"x"}}]}')
    )

    assert _call_names(accumulator.build_response()) == ["read", "write"]


def test_reasoning_only_call_is_not_an_empty_turn():
    """T-06: ein turn, dessen einziger call im reasoning steht, galt als
    leer — der leer-retry half nicht und die echte tool-runde ging
    verloren."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", think='Ich lese: {"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}')
    )
    accumulator.finalize("finish")

    assert accumulator.is_empty_response() is False
    assert _call_names(accumulator.build_response()) == ["read"]


def test_blocked_call_in_reasoning_is_reported_not_leaked():
    """T-05: protokoll im reasoning darf dem client nicht als denktext
    gezeigt werden; der blockierte versuch wird stattdessen gemeldet."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", think='Ich oeffne: {"tool_calls":[{"name":"open_url","arguments":{"url":"https://x.com"}}]}', status="finish")
    )
    response = accumulator.build_response()

    assert "open_url" in accumulator.blocked_tool_attempt_names
    assert "tool_calls" not in str(response["choices"][0]["message"].get("reasoning_content") or "")


def test_blocked_attempt_in_function_syntax_is_detected():
    """T-10: `open_url("…")` war fuer die erkennung voellig blind — der
    turn endete als leerer stop."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", text='Ich rufe open_url("https://x.com") auf.', status="finish")
    )
    accumulator.finalize("finish")

    assert "open_url" in accumulator.blocked_tool_attempt_names


def test_blocked_attempt_case_variant_is_detected():
    """T-10/T-11: `OPEN_URL` umging die pruefung, weil der vergleich
    case-sensitiv war."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", text='Ich rufe OPEN_URL("https://x.com") auf.', status="finish")
    )
    accumulator.finalize("finish")

    assert any(name.lower() == "open_url" for name in accumulator.blocked_tool_attempt_names)


def test_allowed_tool_in_function_syntax_is_not_blocked():
    """Gegenprobe: eine erlaubte Tool-Nennung ist kein blockierter
    Versuch — sonst loest blosse Prosa negative Runden aus."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", text='Ich nutze read("config.py") fuer die Analyse.', status="finish")
    )
    accumulator.finalize("finish")

    assert accumulator.blocked_tool_attempt_names == []


def test_safety_net_call_without_content_is_dropped():
    """T-12: calls aus dem safety-net umgingen frueher die
    required-argument-pruefung — ein write ohne content ging als
    ausfuehrung an den client."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"write"})
    accumulator.consume_event(
        _event("c", "p1", text='{"tool_calls":[{"name":"write","arguments":{"filePath":"/a.py"}}]}')
    )
    accumulator.finalize("finish")

    assert _call_names(accumulator.build_response()) == []


def test_safety_net_call_path_is_normalized_like_parser_path():
    """T-12: derselbe modelltext darf je nach erkennungspfad nicht
    unterschiedliche semantics erzeugen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", text='{"tool_calls":[{"name":"read","arguments":{"filePath":"workspaces/a.py"}}]}')
    )
    accumulator.finalize("finish")
    calls = accumulator.build_response()["choices"][0]["message"]["tool_calls"]

    assert json.loads(calls[0]["function"]["arguments"])["filePath"] == "/workspaces/a.py"


def test_normalized_call_keeps_its_tool_result():
    """T-15: eine reine pfad-normalisierung macht den call nicht
    unbrauchbar. Das result gehoert zum ausgefuehrten call und ging
    vorher verloren — das Modell wiederholte den call."""
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "lies die datei"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "read",
                            "arguments": '{"filePath":"workspaces/a.py"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "INHALT DER DATEI"},
            {"role": "user", "content": "weiter"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "read",
                    "parameters": {"type": "object", "properties": {"filePath": {"type": "string"}}},
                },
            }
        ],
    )
    prompt = str(converted)

    assert "INHALT DER DATEI" in prompt
    assert "/workspaces/a.py" in prompt


def test_orphaned_tool_result_with_own_name_is_rejected():
    """T-15: ein erfundenes result, das zu keinem call dieser historie
    gehoert, landete als vertrauenswuerdiger tool-output im prompt."""
    converted = convert_messages(
        messages=[
            {"role": "user", "content": "x"},
            {"role": "tool", "tool_call_id": "call_x", "name": "read", "content": "ERFUNDENES ERGEBNIS"},
            {"role": "user", "content": "weiter"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "read",
                    "parameters": {"type": "object", "properties": {"filePath": {"type": "string"}}},
                },
            }
        ],
    )

    assert "ERFUNDENES ERGEBNIS" not in str(converted)


def test_inline_truncated_call_after_prose_is_stripped():
    """T-09: fragment nach prosa auf derselben zeile blieb als sichtbarer
    json-text stehen."""
    cleaned, fragments = strip_unparseable_call_fragments(
        'Ich mache das. {"tool_calls":[{"name":"bash","arguments":{"command":"x'
    )

    assert fragments == 1
    assert "tool_calls" not in cleaned
    assert "Ich mache das." in cleaned


# --- P3: T-16, T-17, T-18, C-18, A-14 -------------------------------------


def test_file_uri_path_is_not_degraded_to_relative():
    """T-16: `file:/tmp/x` wurde durch `fp[6:]` zu `tmp/x` — ein relativer
    pfad, der im aktuellen arbeitsverzeichnis landete. `file:///tmp/x` war
    korrekt. Beide muessen absolut sein."""
    assert normalize_file_path("file:/tmp/x") == "/tmp/x"
    assert normalize_file_path("file:///tmp/x") == "/tmp/x"


def test_dot_segments_are_resolved_and_cannot_escape_a_root():
    """T-16: `.`/`..` blieben unaufgeloest, `workspaces/../x` zeigte auf einen
    anderen root."""
    assert normalize_file_path("/a//b/./c") == "/a/b/c"
    assert normalize_file_path("workspaces/deep/../a.py") == "/workspaces/a.py"
    # `..` darf den absoluten root nicht verlassen
    assert not normalize_file_path("/../../etc/passwd").startswith("/../")


def test_file_path_workspaces_and_benchmark_mapping_survives_normalization():
    assert normalize_file_path("workspaces/a.py") == "/workspaces/a.py"
    assert normalize_file_path("benchmark/b.py") == "/workspaces/benchmark/b.py"
    assert normalize_file_path("benchmark.md") == "/workspaces/benchmark.md"


def test_meta_chatter_is_removed_per_sentence_not_per_line():
    """T-17: der filter war zeilenbasiert und kannte die live beobachteten
    englischen formulierungen nicht. Nur der verdaechtige satz faellt —
    die eigentliche antwort auf derselben zeile bleibt."""
    stripped = strip_meta_chatter(
        "I'm sorry, I cannot use that tool. Die Antwort ist 42."
    )
    assert "42" in stripped
    assert "cannot use that tool" not in stripped

    assert strip_meta_chatter("I cannot access that URL. Ergebnis: 7.").strip() == "Ergebnis: 7."
    assert strip_meta_chatter("Es tut mir leid, ich kann das nicht. Ergebnis: 3.").strip() == "Ergebnis: 3."


def test_meta_chatter_filter_keeps_ordinary_answers():
    for text in (
        "Hier ist die Datei gelesen und der Inhalt stimmt.",
        "Das Ergebnis ist 42.",
        "The answer is 42.",
    ):
        assert strip_meta_chatter(text) == text


def test_tool_choice_required_is_enforced_streaming():
    """T-18: `tool_choice=required` stand nur im prompt. Ein turn mit prosa
    galt als regulaerer 'stop' — der client hatte einen tool-vertrag
    verlangt und bekam eine antwort."""
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"read"}, tool_choice_mode="required"
    )
    accumulator.consume_event(
        _event("c", "p1", text="Hier ist die Antwort, aber kein Tool.", status="finish")
    )
    accumulator.finalize("finish")
    response = accumulator.build_response()

    assert response["choices"][0]["finish_reason"] == "error"
    assert "[tool_choice_violation]" in (response["choices"][0]["message"]["content"] or "")


def test_tool_choice_required_is_satisfied_by_a_call():
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"read"}, tool_choice_mode="required"
    )
    accumulator.consume_event(
        _event(
            "c",
            "p1",
            text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a"}}]}',
            status="finish",
        )
    )
    accumulator.finalize("finish")
    response = accumulator.build_response()

    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert "tool_choice_violation" not in str(response)


def test_tool_choice_auto_is_not_penalised():
    """Gegenprobe: ohne vertrag bleibt ein prosa-turn ein ganz normaler stop."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(_event("c", "p1", text="Eine normale Antwort.", status="finish"))
    accumulator.finalize("finish")

    assert accumulator.build_response()["choices"][0]["finish_reason"] == "stop"


def test_stop_sequence_truncates_visible_text():
    """C-18: `stop` konnte der upstream nicht durchsetzen, der proxy schon."""
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names=None, stop_sequences=("ENDE",)
    )
    accumulator.consume_event(_event("c", "p1", text="Vorher. ENDE Nachher.", status="finish"))
    accumulator.finalize("finish")

    assert accumulator.build_response()["choices"][0]["message"]["content"] == "Vorher."


def test_serializer_does_not_invent_raw_argument_semantics():
    """A-14: bei kaputtem argument-json erfand der serializer `{"raw": …}`.
    Beim history-roundtrip spiegelte das Modell den call mit anderen
    argumenten und glaubte, `raw` sei ein echter parameter."""
    from glm2api.utils.tool_protocol import serialize_tool_call_block

    serialized = serialize_tool_call_block("read", "{kaputt")

    assert '"raw"' not in serialized
    assert "_unusable_args" in serialized


def test_history_compression_keeps_multi_tool_round_atomic():
    """T-14: bei `assistant(c1,c2) + tool(c1) + tool(c2)` erkannte der
    paar-schutz nur das erste result als partner. `tool(c2)` blieb als
    eigenstaendige message im prompt — ein result ohne seinen call. Das
    erzeugt beim modell fehlende rueckmeldung und wiederholte calls."""
    messages = [
        {"role": "user", "content": "aufgabe " * 40},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"filePath":"/a"}'}},
                {"id": "c2", "type": "function", "function": {"name": "read", "arguments": '{"filePath":"/b"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "A" * 100},
        {"role": "tool", "tool_call_id": "c2", "content": "B" * 100},
        {"role": "user", "content": "weitere aufgabe " * 40},
    ]

    for budget in (1000, 700, 400, 200, 100):
        body = compress_history_messages(messages, budget)
        result_ids = [m.get("tool_call_id") for m in body if m.get("role") == "tool"]
        call_ids = [
            call.get("id")
            for message in body
            if message.get("role") == "assistant"
            for call in (message.get("tool_calls") or [])
        ]
        # jedes result hat seinen call — und umgekehrt kein call ohne result
        for result_id in result_ids:
            assert result_id in call_ids, f"verwaistes result {result_id} bei budget={budget}"
        if call_ids:
            assert sorted(result_ids) == sorted(call_ids), f"call ohne result bei budget={budget}"


# --- P4: T-19, T-20, T-21, T-22 -------------------------------------------


def test_part_order_follows_arrival_not_lexicographic_sort():
    """T-20: `insort` sortierte die logic-ids als strings — ab zehn parts
    kam `p10` zwischen `p1` und `p2`, der sichtbare text wurde zerwuerfelt."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    for index in range(1, 13):
        accumulator.consume_event(_event("c", f"p{index}", text=f"[{index}]"))
    text, _reasoning = accumulator.render_full_output()

    assert text.replace("\n", "") == "".join(f"[{index}]" for index in range(1, 13))


def test_part_merge_writes_status_and_does_not_duplicate_non_text():
    """T-19: der berechnete eingangs-status wurde nie geschrieben (das part
    behielt sein 'init'), und non-text-items wurden bei jedem update erneut
    angehaengt — ein bild stand nach fuenf updates fuenfmal im content."""
    from glm2api.services.translator import _merge_part_texts

    image = {"type": "image", "url": "x.png"}
    existing = {"logic_id": "p1", "status": "init", "content": [{"type": "text", "text": "A"}, image]}

    for _ in range(5):
        merged = _merge_part_texts(
            existing, {"status": "init", "content": [{"type": "text", "text": "B"}, image]}, "init"
        )
    assert sum(1 for item in merged["content"] if item.get("type") == "image") == 1
    assert merged["content"][0]["text"] == "AB"

    finished = _merge_part_texts(existing, {"status": "finish", "content": [{"type": "text", "text": "AB"}]}, "finish")
    assert finished["status"] == "finish", "der finish-status muss im part landen"


def test_finalize_is_idempotent():
    """T-22: ein zweiter `finalize()` spulte den parser erneut und gab
    dieselben tool_calls ein zweites mal aus — in einer kette aus
    finalize/retry/prepend-notice entstehen doppelte calls beim client."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event("c", "p1", text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a"}}]}', status="finish")
    )
    first = accumulator.finalize("finish")
    second = accumulator.finalize("finish")
    third = accumulator.finalize("stop")

    assert any('"tool_calls"' in chunk for chunk in first)
    assert second == []
    assert third == []


def test_bare_domain_is_mapped_as_url_not_as_file():
    """T-21: `example.com` fiel durch den punkt-check in die
    datei-erkennung und wurde als read auf einen nicht existierenden
    namen abgebildet."""
    from glm2api.services.translator import map_native_open_tool_call

    mapped = map_native_open_tool_call({"url": "example.com"}, allowed_tool_names={"webfetch", "read"})

    assert mapped == ("webfetch", {"url": "https://example.com"})


def test_native_open_multiple_targets_are_not_silently_dropped():
    """T-21: nur `open[0]` wurde abgearbeitet, der rest verschwand ohne
    spur. Der erste mappbare gewinnt, der rest wird protokolliert."""
    from glm2api.services.translator import map_native_open_tool_call

    mapped = map_native_open_tool_call(
        {"open": [{"url": "https://a.com"}, {"url": "https://b.com"}]},
        allowed_tool_names={"webfetch"},
    )

    assert mapped is not None and mapped[0] == "webfetch"


def test_native_call_without_id_is_not_silently_dropped():
    """C-13: der echo-filter verlangte eine `tool_id`. Serverseitige calls
    OHNE id fielen ersatzlos weg — auch dann, wenn sie sich von jedem
    historischen call unterschieden. Empirisch kam ein `read` auf einen
    NEUEN pfad nicht an, der agent las die runde als abgeschlossen."""
    history = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "c1", "function": {"name": "read", "arguments": '{"filePath":"/a.py"}'}}
            ],
        }
    ]
    signatures = extract_history_tool_call_signatures(history)

    def build(file_path):
        accumulator = GLMEventAccumulator(
            model="m", allowed_tool_names={"read"}, history_tool_call_signatures=signatures
        )
        accumulator = GLMEventAccumulator(
            model="m", allowed_tool_names={"read"}, history_tool_call_signatures=signatures
        )
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "status": "finish",
                "parts": [
                    {
                        "logic_id": "p1",
                        "status": "finish",
                        "content": [
                            {
                                "type": "tool_calls",
                                "tool_calls": {"name": "read", "arguments": {"filePath": file_path}},
                            }
                        ],
                    }
                ],
            }
        )
        accumulator.finalize("finish")
        return accumulator.build_response()

    # echtes echo (identische signatur aus der historie) bleibt unterdrueckt
    assert (build("/a.py")["choices"][0]["message"].get("tool_calls") or []) == []
    # eine gewollte wiederholung mit neuem ziel kommt an
    calls = build("/neu.py")["choices"][0]["message"].get("tool_calls") or []
    assert [call["function"]["name"] for call in calls] == ["read"]


# --- T-20 (interleaving): ein protokoll ueber viele logic_ids -----------


def test_protocol_split_across_logic_ids_stays_one_call():
    """ChatGLM zerlegt einen einzigen logischen text ueber viele
    `logic_id`s (live: 166 ids in einem turn). Der accumulator haengte die
    part-texte mit `\\n\\n` zusammen — der trenner zerriss das JSON mitten
    im `content`, der parser fand keinen call mehr und der rest landete
    als sichtbarer text."""
    protocol = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    for index in range(0, len(protocol), 7):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {
                        "logic_id": f"s{index}",
                        "content": [{"type": "text", "text": protocol[index : index + 7]}],
                    }
                ],
            }
        )
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    calls = message.get("tool_calls") or []
    assert [call["function"]["name"] for call in calls] == ["read"]
    assert not (message.get("content") or "").strip(), "protokollreste im content"
    assert json.loads(calls[0]["function"]["arguments"])["filePath"] == "/a.py"


def test_protocol_continuation_survives_every_chunk_size():
    """Gegenprobe ueber alle chunk-grenzen: der call darf nicht von der
    fragmentierung abhaengen."""
    protocol = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    for chunk_size in (1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 31, 47):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
        for index in range(0, len(protocol), chunk_size):
            accumulator.consume_event(
                {
                    "conversation_id": "c",
                    "parts": [
                        {
                            "logic_id": f"s{index}",
                            "content": [{"type": "text", "text": protocol[index : index + chunk_size]}],
                        }
                    ],
                }
            )
        accumulator.finalize("finish")
        message = accumulator.build_response()["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        assert [call["function"]["name"] for call in calls] == ["read"], f"chunk_size={chunk_size}"
        assert not (message.get("content") or "").strip(), f"chunk_size={chunk_size} leakt"


def test_prose_parts_are_still_separated_by_a_blank_line():
    """Gegenprobe: echte, getrennte text-parts duerfen NICHT
    zusammenschmelzen — die fortsetzungs-regel greift nur bei
    angebrochenen protokoll-strukturen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    accumulator.consume_event(_event("c", "p1", text="Erster Absatz."))
    accumulator.consume_event(_event("c", "p2", text="Zweiter Absatz."))
    text, _reasoning = accumulator.render_full_output()

    assert text == "Erster Absatz.\n\nZweiter Absatz."


def test_text_continues_protocol_predicate():
    """Die Heuristik selbst: offene struktur + JSON-spuren = fortsetzung,
    normale prosa bleibt unangetastet."""
    from glm2api.utils.tool_parser import text_continues_protocol

    assert text_continues_protocol('{"tool_') is True
    assert text_continues_protocol('Ich pruefe das. {"tool_calls":[{') is True
    assert text_continues_protocol('{"tool_calls":[{"name":"read","arguments":{"url"') is True
    # vollstaendiges protokoll -> keine fortsetzung
    assert text_continues_protocol('{"tool_calls":[{"name":"read","arguments":{}}]}[]') is False
    # prosa mit klammer oder offenem string -> keine fortsetzung
    assert text_continues_protocol("normale { klammer am ende") is False
    assert text_continues_protocol('Hallo "unterminierter string') is False
    assert text_continues_protocol("Erster Absatz.") is False
    assert text_continues_protocol("") is False


# --- Schlussabgleich (F-5h): die nachgeprueften befunde ---------------


def test_request_without_declared_tools_produces_no_call():
    """T-02 (Kritisch, im Schlussabgleich als OFFEN wiedergefunden):
    `allowed_tool_names=None` galt nur im Text-Parser als 'keine Tools'.
    Ein natives `open` wurde trotzdem zu `webfetch` — mit
    `finish_reason='tool_calls'`. Ein nachgelagerter Agent haette
    ausgefuehrt."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": {"name": "open", "arguments": {"url": "https://x.com"}},
                        }
                    ],
                }
            ],
        }
    )
    accumulator.finalize("finish")
    response = accumulator.build_response()

    assert not (response["choices"][0]["message"].get("tool_calls") or [])
    assert response["choices"][0]["finish_reason"] != "tool_calls"


def test_url_is_never_mapped_to_a_file_read():
    """T-02: ohne `webfetch` wurde eine URL als `read` mit der URL als
    filePath abgebildet — ein unerfuellbarer Leseauftrag."""
    from glm2api.services.translator import map_native_open_tool_call

    assert map_native_open_tool_call({"url": "https://x.com"}, allowed_tool_names={"read"}) is None
    assert map_native_open_tool_call({"path": "/a.py"}, allowed_tool_names={"read"}) == (
        "read",
        {"filePath": "/a.py"},
    )


def test_valid_protocol_with_terminator_is_not_stripped():
    """P-09: der 'unparseable'-Stripper loeschte JEDES vollstaendige
    protokoll samt allem, was danach im selben part stand."""
    from glm2api.utils.tool_parser import strip_unparseable_call_fragments

    complete = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    cleaned, fragments = strip_unparseable_call_fragments(complete)

    assert fragments == 0
    assert cleaned == complete

    truncated = 'text {"tool_calls":[{"name":"read","arguments":'
    cleaned_truncated, fragments_truncated = strip_unparseable_call_fragments(truncated)
    assert fragments_truncated == 1
    assert cleaned_truncated == "text"


def test_dsml_repair_does_not_touch_argument_data():
    """P-10: `replace('">>', '">')` lief global und verletzte ein
    semantisch gueltiges argument — bei einem bash-auftrag eine
    ausfuehrungsrelevante datenbeschädigung."""
    from glm2api.utils.tool_parser import _repair_malformed_dsml

    block = '<|DSML|invoke name="bash"><![CDATA[{"command": "printf \'a">>b\'"}]]><|DSML|>'
    repaired = _repair_malformed_dsml(block)

    assert "a\">>b" in repaired, "argument-daten wurden veraendert"
    # die tag-reparatur greift weiterhin ausserhalb von CDATA
    assert '">>' not in _repair_malformed_dsml('<|DSML|invoke name="x">><|DSML|>')


def test_string_valued_image_url_does_not_crash():
    """T-23: `image_url` als String brach mit AttributeError ab und wurde
    zum 500er."""
    from glm2api.services.translator import extract_text_content

    assert extract_text_content([{"type": "image_url", "image_url": "https://x/a.png"}]) == (
        "[image:https://x/a.png]"
    )
    assert extract_text_content([{"type": "file", "file_url": "https://x/b.pdf"}]) == (
        "[file:https://x/b.pdf]"
    )


def test_null_call_id_does_not_become_the_string_none():
    """T-11: `str(None)` erzeugte die id "None" — erfunden, aber scheinbar
    gueltig."""
    from glm2api.services.translator import GLMEventAccumulator

    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "p1",
                    "status": "finish",
                    "content": [
                        {
                            "type": "tool_calls",
                            "tool_calls": {
                                "name": "read",
                                "id": None,
                                "arguments": {"filePath": "/a"},
                            },
                        }
                    ],
                }
            ],
        }
    )
    accumulator.finalize("finish")
    calls = accumulator.build_response()["choices"][0]["message"].get("tool_calls") or []

    assert calls, "der call selbst darf nicht verloren gehen"
    assert calls[0]["id"] != "None"


@pytest.mark.parametrize("status", ["error", "aborted", "cancelled", "timeout", "truncated", "intervene"])
def test_failed_terminal_status_is_not_reported_as_stop(status):
    """T-13/S-08: jeder fehlgeschlagene terminalstatus endete als
    `stop` + `[DONE]`. Eine abgebrochene runde ist ein fehler."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(_event("c", "p1", text="teilantwort", status="finish"))
    chunks = accumulator.finalize(status)

    finish_reason = None
    for chunk in chunks:
        if chunk.startswith("data: ") and "[DONE]" not in chunk:
            finish_reason = json.loads(chunk[6:].strip())["choices"][0].get("finish_reason")
    assert finish_reason == "error", f"status={status}"
    assert not any("[DONE]" in chunk for chunk in chunks), f"status={status}"
    assert accumulator.build_response()["choices"][0]["finish_reason"] == "error"


@pytest.mark.parametrize("status", [None, "", "finish", "stop"])
def test_successful_terminal_status_still_reports_stop(status):
    """Gegenprobe: regulaere abschluesse bleiben unveraendert."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(_event("c", "p1", text="ganze antwort", status="finish"))
    chunks = accumulator.finalize(status)

    assert any("[DONE]" in chunk for chunk in chunks)
    assert accumulator.build_response()["choices"][0]["finish_reason"] == "stop"


def test_rendering_stays_within_a_time_budget():
    """T-20: das Rendern lief quadratisch und wurde durch die eigene
    zwischenloesung zunaechst noch schlechter (18,4 s fuer 1000 parts
    gegenueber 3,5 s im urspruenglichen audit).

    Erreicht wurde: der Aufbau ist inkrementell — neue Parts werden
    angehaengt, der Klammer-/String-Zustand fortgeschrieben, nur
    geaenderte Parts neu gerendert. 1000 Parts benoetigen damit ~2,4 s
    statt 18,4 s.

    Ehrlich offen: das Wachstum ist weiterhin superlinear, weil
    `_render_full_output()` und `_compute_deltas()` pro Event ueber alle
    bekannten Logic-IDs laufen. Eine echte Komplexitaetskorrektur
    braucht einen ereignis-basierten Part-Index — das ist ein Umbau,
    kein Feinschliff. Der Test sichert daher die *gemessene*
    Verbesserung ab, statt Linearitaet zu behaupten."""
    import time

    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    start = time.monotonic()
    for index in range(500):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": f"p{index}", "content": [{"type": "text", "text": "ab"}]}
                ],
            }
        )
    duration = time.monotonic() - start

    # grosszuegige schranke: genug, um die 18,4-s-regression zu fangen,
    # ohne auf einem lahmem runner flaky zu werden
    assert duration < 8.0, f"500 parts brauchten {duration:.1f}s — die inkrementelle aufbaut?"


def test_incremental_render_matches_full_rebuild():
    """Der inkrementelle aufbau muss dasselbe ergeben wie ein
    vollstaendiges neu zusammenbauen DESSELBEN inputs — sonst
    beschleunigt er auf kosten der richtigkeit (T-20)."""
    text_parts = ["Die Datei", " ist da", ".", "Naechster", " Absatz."]
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    for index, part_text in enumerate(text_parts):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": f"p{index}", "content": [{"type": "text", "text": part_text}]}
                ],
            }
        )
    incremental, _reasoning = accumulator.render_full_output()

    # vollstaendiger neuaufbau: zwischenspeicher und inkrementellen
    # zustand leeren, dann erneut rendern
    accumulator._cached_full_text = ""
    accumulator._render_cache_dirty = True
    accumulator._joined_state.clear()
    rebuilt, _ = accumulator.render_full_output()

    assert incremental == rebuilt, "inkrementell und neuaufbau weichen ab"
    assert incremental == "Die Datei ist da.\n\nNaechster Absatz."


def test_part_continuation_rules():
    """T-20: mitten im satz wird ohne trenner gehaengt, nach einem
    satzzeichen mit absatzumbruch, vor einem block-marker (markdown)
    ebenfalls."""
    def rendered(texts):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
        for index, part_text in enumerate(texts):
            accumulator.consume_event(
                {
                    "conversation_id": "c",
                    "parts": [
                        {"logic_id": f"p{index}", "content": [{"type": "text", "text": part_text}]}
                    ],
                }
            )
        return accumulator.render_full_output()[0]

    # mitten im satz -> forsetzung
    assert rendered(["Die Datei", " ist da"]) == "Die Datei ist da"
    # nach satzzeichen -> absatz
    assert rendered(["Erster Absatz.", "Zweiter Absatz."]) == "Erster Absatz.\n\nZweiter Absatz."
    # markdown-blockstart -> absatz
    assert rendered(["## Titel", "| a |"]) == "## Titel\n\n| a |"
