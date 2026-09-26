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
    # Ein GESPERRTER aufruf ist kein fehler, sondern eine vollstaendige
    # antwort ("dieses werkzeug gibt es nicht"). Als `error` gegangen,
    # wertete der echte client das als stream-fehler und wiederholte den
    # turn mit 5-minuten-backoff — endlosschleife, weil das modell `open`
    # bei jedem versuch erneut aufrief (natives GLM-werkzeug).
    assert '"finish_reason":"stop"' in output


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
    assert response["choices"][0]["finish_reason"] == "stop"


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
    # Ein gesperrtes protokoll ohne ergebnis ist eine vollstaendige
    # antwort mit sichtbarem hinweis -> `stop`, KEIN fehler. Als `error`
    # loeste es beim echten client eine retry-schleife aus (5 min
    # backoff, ohne fortschritt).
    assert '"finish_reason":"stop"' in final_chunks[1]


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
    # T-04: die schleife wird gebrochen, aber NICHT auf einen einzigen
    # aufruf reduziert — bis zu zwei identische aufrufe pro turn sind
    # zulaessig (ein wiederholungsversuch ist plausibel, 36 gleiche
    # aufrufe sind es nicht). Vorher ueberlebte hier nur der erste.
    assert len(tool_calls) == 2


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
    # Ein GESPERRTER aufruf endet regulaer: als `error` wertete der
    # echte client das als stream-fehler und wiederholte den turn mit
    # 5-minuten-backoff endlos (agentenlauf 2026-09-26).
    assert response["choices"][0]["finish_reason"] == "stop"
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

    # `tool_choice=required` verletzt ist ein echter vertragsbruch, kein
    # gesperrter aufruf: der client MUSS etwas bekommen, das er ausfuehren
    # kann. Daher bleibt es hier bei `error` (anders als beim gesperrten
    # aufruf, der eine vollstaendige antwort ist).
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
    # A-14: auch die Reparaturtherk selbst darf nicht wie ein Parameter
    # aussehen — `$invalid_arguments` ist im JSON-Schema fuer Meta-Keys
    # reserviert und nicht als Werkzeug-Faehigkeit lesbar.
    assert "$invalid_arguments" in serialized
    assert "_unusable_args" not in serialized


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


# --- P1-Nachtrag aus der unabhängigen Prüfrunde --------------------------


def test_native_call_is_not_executable_without_declared_tools():
    """T-02 (im Nachtrag gefunden): die Wildcard-Semantik war nur im
    Text-Parser behoben. Im nativen Pfad (`meta_data`/content-item
    `tool_calls`) uebersprang die pruefung bei `allowed_tool_names=None`
    komplett — ein Request OHNE Tools fuehrte einen nativen Call aus."""
    for name, arguments in (
        ("open_url", {"url": "https://x.com"}),
        ("OPEN_URL", {"url": "https://x.com"}),
        ("execute_sandbox_code", {"code": "open('/etc/hosts').read()"}),
        ("read", {"filePath": "/a"}),
    ):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
        accumulator.consume_event(
            _event(
                "c",
                "p1",
                status="finish",
            )
        )
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
                                "tool_calls": {"name": name, "id": f"i-{name}", "arguments": arguments},
                            }
                        ],
                    }
                ],
            }
        )
        accumulator.finalize("finish")
        response = accumulator.build_response()

        assert not (response["choices"][0]["message"].get("tool_calls") or []), name
        assert name in accumulator.blocked_tool_attempt_names, name
        # Ein GESPERRTER aufruf ist keine fehlerhafte runde, sondern eine
        # vollstaendige antwort ("dieses werkzeug gibt es nicht"). Als
        # `error` wertete der echte client das als stream-fehler und
        # wiederholte den turn mit 5-minuten-backoff endlos — gemessen am
        # agentenlauf 2026-09-26, wo `open` (natives GLM-werkzeug) bei jedem
        # versuch erneut aufgerufen wurde. Der aufruf selbst wird weiterhin
        # NICHT ausgeliefert (das sichert die zeile davor).
        assert response["choices"][0]["finish_reason"] == "stop", name


def test_valid_call_survives_a_blocked_call_in_the_same_event():
    """D-05: ein gesperrter nativer Call brach den ganzen Parts-Durchlauf
    ab. Ein gueltiger Call, der im selben Event SPÄTER kam, ging verloren —
    reihenfolgeabhängig."""
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
                                "name": "open_url",
                                "id": "b1",
                                "arguments": {"url": "https://x.com"},
                            },
                        },
                        {
                            "type": "tool_calls",
                            "tool_calls": {
                                "name": "read",
                                "id": "a1",
                                "arguments": {"filePath": "/a.py"},
                            },
                        },
                    ],
                }
            ],
        }
    )
    accumulator.finalize("finish")
    response = accumulator.build_response()

    calls = response["choices"][0]["message"].get("tool_calls") or []
    assert [call["function"]["name"] for call in calls] == ["read"], (
        "der gueltige call darf nicht am gesperrten verloren gehen"
    )
    assert "open_url" in accumulator.blocked_tool_attempt_names


def test_raw_argument_recovery_ends_at_the_field_boundary():
    """T-23: das Feldende wurde mit `rfind('"')` bestimmt — das findet das
    LETZTE Anführungszeichen. Aus
    `{"filePath":"/a","content":"hello","other":"z"}` wurde so
    `content='hello","other":"z'` — bei einem Bash-Auftrag eine
    ausführungsrelevante Datenbeschädigung."""
    from glm2api.services.translator import repair_raw_tool_args

    assert repair_raw_tool_args("write", '{"filePath":"/a","content":"hello","other":"z"}') == {
        "filePath": "/a",
        "content": "hello",
    }
    assert repair_raw_tool_args("bash", '{"command":"ls -la","cwd":"/tmp","timeout":5}') == {
        "command": "ls -la"
    }
    # escapes im wert werden nicht als feldende missverstanden
    assert repair_raw_tool_args("write", '{"filePath":"/a","content":"mit \\"x\\" drin","other":1}') == {
        "filePath": "/a",
        "content": 'mit "x" drin',
    }


def test_scalar_parameters_are_not_retyped():
    """T-23: stringified JSON wurde in JEDEM parameter entpackt —
    `{"url": "{\\"a\\":1}"}` wurde zu `{"url": {"a": 1}}`, ein stiller
    Typwechsel ohne Schema."""
    from glm2api.services.translator import sanitize_tool_call_payload

    assert sanitize_tool_call_payload("webfetch", {"url": '{"a":1}'}) == {"url": '{"a":1}'}
    assert sanitize_tool_call_payload("custom", {"q": "[1,2]"}) == {"q": "[1,2]"}
    assert sanitize_tool_call_payload("read", {"filePath": '["x"]'}) == {"filePath": '["x"]'}


def test_meta_chatter_filter_keeps_legitimate_sentences():
    """T-17: ein Schlüsselwort irgendwo in der Zeile löschte die ganze
    Zeile. Aus 'Die Datei ist da, aber open ist nicht dasselbe wie read.'
    wurde ''. Meta-Chatter steht am Zeilenanfang."""
    assert strip_meta_chatter(
        "Die Datei ist da, aber open ist nicht dasselbe wie read."
    ) == "Die Datei ist da, aber open ist nicht dasselbe wie read."
    assert strip_meta_chatter("Das Ergebnis ist 42.") == "Das Ergebnis ist 42."
    # am Zeilenanfang wird weiterhin entfernt
    assert strip_meta_chatter("Ergebnis:\nopen ist nicht verfügbar\nWeiter gehts.") == (
        "Ergebnis:\nWeiter gehts."
    )
    assert strip_meta_chatter("- open ist nicht verfügbar") == ""


def test_meta_chatter_filter_runs_in_both_paths():
    """T-17: der Filter lief nur im Stream-Pfad. Mit Tool-Calls blieb er
    im Non-Stream-Pfad ungefiltert — Paritätsbruch (Stream lieferte '',
    Non-Stream den Meta-Text als Antwort)."""
    text = "Ergebnis:\nopen ist nicht verfügbar\nWeiter gehts."
    protocol = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}'

    with_call = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    with_call.consume_event(_event("c", "p1", text=f"{text}\n{protocol}", status="finish"))
    with_call.finalize("finish")
    with_call_response = with_call.build_response()

    # ohne Tool-Call ist der meta-text die Antwort und bleibt stehen
    without_call = GLMEventAccumulator(model="m", allowed_tool_names=None)
    without_call.consume_event(_event("c", "p1", text=text, status="finish"))
    without_call.finalize("finish")
    without_call_response = without_call.build_response()

    assert with_call_response["choices"][0]["finish_reason"] == "tool_calls"
    assert not (with_call_response["choices"][0]["message"].get("content") or "").strip()
    assert "open ist nicht verfügbar" in (
        without_call_response["choices"][0]["message"]["content"]
    )


# --- T-03, T-04, T-05, T-06: Dedup und Leer-Erkennung -------------------


def test_turn_with_only_unusable_calls_is_a_failure_not_an_empty_success():
    """T-06: `write` ohne content, `read` ohne filePath, `bash` ohne
    command — der Call wurde verworfen und der Turn galt danach als leerer
    ERFOLG: `finish_reason=stop`, `content=None`, und der Leer-Retry feuerte
    nicht. Der Client bekam eine leere, erfolgreiche Antwort und blieb
    stehen."""
    for payload in (
        '{"tool_calls":[{"name":"write","arguments":{"filePath":"/a.py"}}]}[]',
        '{"tool_calls":[{"name":"read","arguments":{}}]}[]',
        '{"tool_calls":[{"name":"bash","arguments":{}}]}[]',
    ):
        accumulator = GLMEventAccumulator(
            model="m", allowed_tool_names={"write", "read", "bash"}
        )
        accumulator.consume_event(_event("c", "p1", text=payload, status="finish"))
        accumulator.finalize("finish")
        response = accumulator.build_response()

        # T-06 bleibt `error`: hier war der aufruf ERLAUBT und scheiterte an
        # einem fehlenden pflichtargument. Dem client fehlt damit etwas
        # Brauchbares, ein Retry ist berechtigt.
        #
        # Anders liegt der Fall bei einem GESPERRTEN aufruf (dort `stop`):
        # der war vollstaendig formuliert und wurde nur abgelehnt. Als
        # `error` wertete der echte client das als stream-fehler und
        # wiederholte den turn mit 5-minuten-backoff endlos (agentenlauf
        # 2026-09-26).
        assert response["choices"][0]["finish_reason"] == "error", payload
        assert accumulator.truncated_turn is True, payload


def test_valid_call_still_works_after_the_unusable_check():
    """Gegenprobe: ein gültiger Call darf nicht als 'unbrauchbar' gelten."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event(
            "c",
            "p1",
            text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]',
            status="finish",
        )
    )
    accumulator.finalize("finish")
    response = accumulator.build_response()

    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert accumulator.truncated_turn is False


def test_same_call_from_two_sources_is_delivered_once():
    """T-03: derselbe Aufruf aus nativem Pfad UND Text-Pfad wurde doppelt
    ausgeliefert — die Identität ist die Call-ID, ein Text-Call bekommt aber
    bei jedem Parse eine frische UUID."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event(
            "c",
            "p1",
            status="finish",
        )
    )
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
                                "id": "n1",
                                "arguments": {"filePath": "/a.txt"},
                            },
                        }
                    ],
                }
            ],
        }
    )
    accumulator.consume_event(
        _event(
            "c",
            "p2",
            text='{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.txt"}}]}[]',
            status="finish",
        )
    )
    accumulator.finalize("finish")
    calls = accumulator.build_response()["choices"][0]["message"].get("tool_calls") or []

    assert [call["function"]["name"] for call in calls] == ["read"], "doppelter call"


def test_two_deliberate_identical_native_calls_both_survive():
    """T-04: zwei Calls mit eigener ID und gleichen Argumenten sind ZWEI
    Aufrufe. Vorher blieb nur der erste."""
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
                            "tool_calls": {"name": "read", "id": "A", "arguments": {"filePath": "/x"}},
                        },
                        {
                            "type": "tool_calls",
                            "tool_calls": {"name": "read", "id": "B", "arguments": {"filePath": "/x"}},
                        },
                    ],
                }
            ],
        }
    )
    accumulator.finalize("finish")
    calls = accumulator.build_response()["choices"][0]["message"].get("tool_calls") or []

    assert sorted(call["id"] for call in calls) == ["A", "B"]


def test_identical_call_loop_is_broken_at_two():
    """T-04: die Degenerationsschleife (live: 36 identische Sandbox-Calls)
    darf nicht 36 Ausführungen erzeugen. Zwei identische Aufrufe bleiben
    zulässig — ein Wiederholungsversuch ist plausibel."""
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"read"})
    for index in range(36):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {
                        "logic_id": "1",
                        "content": [
                            {
                                "type": "tool_calls",
                                "tool_calls": {
                                    "id": f"call_dup_{index}",
                                    "name": "read",
                                    "arguments": '{"filePath":"/a"}',
                                },
                            }
                        ],
                    }
                ],
            }
        )
    calls = accumulator.build_response()["choices"][0]["message"].get("tool_calls", [])

    assert len(calls) == 2


def test_reasoning_call_is_delivered_once_in_the_stream():
    """T-05: ein Call im Reasoning-Kanal lag doppelt vor — einmal aus den
    Deltas und einmal aus der Auswertung im finalize. Im Stream kamen zwei
    Chunks mit unterschiedlichen IDs an."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(
        _event(
            "c",
            "p1",
            status="finish",
        )
    )
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
                            "type": "think",
                            "think": 'Ich lese: {"tool_calls":[{"name":"read","arguments":{"filePath":"/r.txt"}}]}',
                        }
                    ],
                }
            ],
        }
    )
    chunks = accumulator.finalize("finish")
    ids = []
    for chunk in chunks:
        if '"tool_calls"' in chunk:
            ids.extend(
                call.get("id")
                for call in json.loads(chunk[6:].strip())["choices"][0]["delta"].get("tool_calls") or []
            )

    assert len(ids) == 1, f"doppelte calls im stream: {ids}"


# --- T-07 (Preamble) und D-06 (Stream-Reihenfolge) -----------------------


def _stream_visible(text: str, chunk_size: int, allowed=None):
    """Was der Client im Stream tatsaechlich sieht (nur content-deltas)."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=allowed or {"read", "bash"})
    streamed: list[str] = []
    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + chunk_size]}]}
                ],
            }
        )
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            if delta.get("content"):
                streamed.append(delta["content"])
    accumulator.finalize("finish")
    return "".join(streamed), accumulator


@pytest.mark.parametrize("text", [
    "Hier ist die Anleitung.",
    "Die Datei ist nicht leer.",
    "Ergebnis: alles geprueft und dokumentiert.",
])
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 11])
def test_stream_never_loses_characters_of_plain_prose(text, chunk_size):
    """D-06: der Stream stellte Prosa um und verlor zeichen. Ein reiner
    whitespace-delta wurde zurueckgehalten und kam nur in der finalen
    antwort wieder — im stream fehlte er
    ('Hier ist die Anleitung.' -> 'Hier ist dieAnleitung.')."""
    streamed, _accumulator = _stream_visible(text, chunk_size)

    # Was im stream fehlt, muss spaeter in der finalen antwort kommen —
    # zusammen muss es exakt die eingabe ergeben.
    message = _accumulator.build_response()["choices"][0]["message"]
    final = message.get("content") or ""

    assert streamed + final == text or final == text, (
        f"zeichenverlust: stream={streamed!r} final={final!r} erwartet={text!r}"
    )


@pytest.mark.parametrize("preamble", [
    "I will read the file now.\n",
    "Let me check the file.\n",
    "Ich lese die Datei jetzt.\n",
])
def test_preamble_is_suppressed_when_a_call_follows(preamble):
    """T-07: die Praeambel-Erkennung kannte nur deutsche Muster. Die live
    vorgekommenen englischen Varianten liefen unerkannt durch. Ist die
    Praeambel nicht unterdrueckt, steht sie als Antwort vor dem Call."""
    protocol = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}'
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    for index in range(0, len(preamble), 5):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": preamble[index : index + 5]}]}
                ],
            }
        )
    for index in range(0, len(protocol), 9):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": protocol[index : index + 9]}]}
                ],
            }
        )
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert [call["function"]["name"] for call in (message.get("tool_calls") or [])] == ["read"]
    assert not (message.get("content") or "").strip(), "praeambel steht als antwort vor dem call"


# --- S-05 (Stream-Reihenfolge des deferred-puffers) ------------------------


def _stream_including_finalize(text: str, chunk_size: int, allowed=None) -> str:
    """Was der Client im stream wirklich sieht — INKLUSIVE des finalize-flush.

    `_stream_visible` (D-06) liest nur die deltas aus `consume_event` und
    vergleicht `streamed + build_response().content`. `build_response()`
    liefert aber den *gecachten* volltext, nicht das, was im stream ankam.
    Genau dadurch blieb S-05 unsichtbar: der sichtbare stream war verstuem-
    melt, der cached volltext aber korrekt. Diese variante sammelt daher
    auch die chunks aus `finalize()` — das ist der pfad, ueber den der
    deferred-puffer beim client landet.
    """
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=allowed or {"read", "bash"})
    streamed: list[str] = []

    def collect(chunks):
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])

    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + chunk_size]}]}
                ],
            }
        )
        collect(chunks)
    collect(accumulator.finalize("finish"))
    return "".join(streamed)


# Live-Befund 2026-09-26, glm-5.3, session `glm2api limited 3`: der
# abschnitt nach einem code-fence kam HINTER dem davor. Der fence wurde mitten
# in einem delta geschlossen (`fence_pending` war fuer dieses delta noch
# wahr) -> der gepufferte text kam erst im finalize und stand damit hinter
# dem zwischenzeitlich direkt gestreamten rest.
_S05_TEXTS = {
    "plain-fence": "Vorher\n```\nalpha\nbeta\n```\nNachher",
    "fence-inline": "Vorher ```alpha``` Nachher",
    "fence-then-prose": "Text\n\n```\ncode\n```\n\nFertig. Ende.",
    "list-with-url": (
        "1. **URL-Inhalt** (`http://127.0.0.1:8899/data.txt`, geholt via `bash` + `curl`):\n"
        "   ```\n   alpha\n   beta\n   gamma\n   ```\n"
        "2. **README** (via `read`): existiert.\n"
        "3. **Ergebnisdatei**: geschrieben (bestaetigt)."
    ),
    "fence-last": "Text\n\n```\ncode\n```",
    "no-fence": "1. **A** (`http://127.0.0.1:8899/x.txt`):\n   alpha\n2. **B** Ende.",
}


@pytest.mark.parametrize("label", sorted(_S05_TEXTS))
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 17, 25, 40, 100])
def test_stream_preserves_order_across_code_fences(label, chunk_size):
    """S-05: der stream muss den sichtbaren text in modellreihenfolge
    ausgeben. Vor dem fix wurde der gepufferte abschnitt umgestellt, und bei
    mehreren chunk-groessen ging text verloren oder kam doppelt."""
    text = _S05_TEXTS[label]
    got = _stream_including_finalize(text, chunk_size)
    assert got.split() == text.split(), (
        f"{label} (chunk={chunk_size}): reihenfolge/verlust im stream\n"
        f"  IST : {got!r}\n  SOLL: {text!r}"
    )


def test_stream_still_flushes_prose_early_instead_of_buffering_to_the_end():
    """Gegenprobe zur reihenfolge-fix: der puffer darf nicht zumpuffer werden.

    Ohne fence und ohne protokoll wird prosa weiterhin sofort gestreamt —
    der fix haengt nur am `deferred_visible_text`, nicht am normalen pfad.
    """
    text = "Erste Zeile. Zweite Zeile. Dritte Zeile."
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    early: list[str] = []
    for index in range(0, len(text), 7):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + 7]}]}
                ],
            }
        )
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            if delta.get("content"):
                early.append(delta["content"])
    assert len("".join(early)) > len(text) // 2, (
        f"normale prosa wird nicht mehr gestreamt, sondern bis zum finalize gepuffert: {early!r}"
    )


def test_protocol_inside_fence_is_still_cleaned_before_it_reaches_the_client():
    """Gegenprobe zur sticky-regel: ein fence, der das protokoll umhuellt,
    wird NICHT vorzeitig rausgegeben — der finalize-unwrap muss ihn holen."""
    text = (
        "Hier ist der Aufruf:\n```json\n"
        '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]\n'
        "```\nFertig."
    )
    streamed = _stream_including_finalize(text, 6, allowed={"read"})
    assert '"tool_calls"' not in streamed, f"protokoll im client-stream: {streamed!r}"
    assert "```json" not in streamed, f"protokoll-fence nicht entpackt: {streamed!r}"


# --- S-06 (Whitespace-Artefakt neben tool-calls) ---------------------------


def _multi_block_call_turn(reads):
    """Mehrere protokollbloecke, durch zeilenumbrueche getrennt — so
    emittiert glm-5.3 parallele aufrufe (live: 7 reads in einem turn, der
    text-part danach bestand aus 12 leerzeilen).

    Der fuehrende umbruch ist der live gefundene ausloeser: er gehoert zu
    keinem block, wird also von keinem `[]`-terminator geschluckt und
    rutscht als sichtbarer whitespace in den stream."""
    blocks = [
        '{"tool_calls":[{"name":"read","arguments":{"filePath":"/f%d.py"}}]}[]' % index
        for index in range(reads)
    ]
    return "\n" + "\n".join(blocks) + "\n"


@pytest.mark.parametrize("reads", [1, 3, 7])
@pytest.mark.parametrize("chunk_size", [1, 3, 7, 13, 40, 200])
def test_no_whitespace_only_text_next_to_tool_calls(reads, chunk_size):
    """S-06: die leerzeilen ZWISCHEN den protokollbloecken sind ein
    strip-artefakt. Live gingen sie als text-part mit 12 leerzeilen an den
    client (leere assistant-nachricht in der TUI)."""
    text = _multi_block_call_turn(reads)
    got = _stream_including_finalize(text, chunk_size, allowed={"read"})
    assert got.strip() == "", f"whitespace-only text erreicht den client: {got!r}"


def test_whitespace_still_streams_before_the_first_call():
    """D-06-gegenprobe: VOR dem ersten aufruf ist ein whitespace-delta die
    trennende zeile zwischen zwei sichtbaren woertern und muss raus."""
    text = "Hier ist die Anleitung.\n\n"
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    streamed = []
    for index in range(0, len(text), 3):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + 3]}]}
                ],
            }
        )
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            if delta.get("content"):
                streamed.append(delta["content"])
    assert "".join(streamed).strip() == "Hier ist die Anleitung.", streamed


def test_non_stream_response_has_no_whitespace_only_content_with_calls():
    """S-06 im non-stream-pfad: `content` darf neben tool_calls nicht nur
    aus leerzeichen bestehen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    text = _multi_block_call_turn(2)
    for index in range(0, len(text), 9):
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {"logic_id": "p1", "content": [{"type": "text", "text": text[index : index + 9]}]}
                ],
            }
        )
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]
    assert len(message.get("tool_calls") or []) == 2
    assert not (message.get("content") or "").strip(), repr(message.get("content"))


@pytest.mark.parametrize("reads", [1, 3, 7])
@pytest.mark.parametrize("filler", ["\n", " ", "\n\n"], ids=["newline", "space", "blank"])
def test_native_calls_with_blank_text_parts_emit_no_blank_lines(reads, filler):
    """S-06, live-form: glm-5.3 liefert neben jedem nativen `tool_calls`-part
    eine eigene text-part, die nur aus leerzeichen besteht. Der part-merge
    setzte an jeder logic_id-grenze zusaetzlich einen absatzumbruch — 7 calls
    ergaben 14 leerzeilen als sichtbaren text (live-session: text-part aus 12
    leerzeilen neben 7 reads; in der TUI eine leere assistant-nachricht, im
    kontext dauerhaft ballast).

    Eine LEERE part (`""`) ist nicht der ausloeser — die trifft die
    `if rendered_text`-bedingung gar nicht. Getestet wird deshalb bewusst
    die whitespace-part."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    parts = []
    for index in range(reads):
        parts.append({"logic_id": f"t{index}", "content": [{"type": "text", "text": filler}]})
        parts.append(
            {
                "logic_id": f"c{index}",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": [
                            {"name": "read", "id": f"call{index}", "arguments": {"filePath": f"/f{index}.py"}}
                        ],
                    }
                ],
            }
        )
    streamed: list[str] = []
    for part in parts:
        chunks, _ = accumulator.consume_event(
            {"conversation_id": "c", "status": "finish", "parts": [part]}
        )
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])
    for chunk in accumulator.finalize("finish"):
        if not chunk.startswith("data: ") or "[DONE]" in chunk:
            continue
        try:
            delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        if delta.get("content"):
            streamed.append(delta["content"])

    message = accumulator.build_response()["choices"][0]["message"]
    assert len(message.get("tool_calls") or []) == reads
    assert "".join(streamed) == "", f"leerzeilen im stream: {''.join(streamed)!r}"
    # non-stream: `content` ist per OpenAI-vertrag None, sobald tool_calls
    # da sind (`"content": None if all_tool_calls or ...`).
    assert message.get("content") in ("", None), repr(message.get("content"))


def test_prose_around_native_calls_keeps_its_spacing():
    """Gegenprobe zu S-06: echter text um native calls herum muss
    unveraendert im stream ankommen — und die leerzeichen zwischen zwei
    woertern sind kein artefakt.

    Geprueft wird der STREAM, nicht `message["content"]`: bei tool_calls ist
    das per OpenAI-vertrag None, dort waere nichts zu sehen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    streamed: list[str] = []

    def collect(chunks):
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])

    collect(
        accumulator.consume_event(
            {"conversation_id": "c", "parts": [{"logic_id": "a", "content": [{"type": "text", "text": "Erster Teil."}]}]}
        )[0]
    )
    collect(
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "status": "finish",
                "parts": [
                    {
                        "logic_id": "c0",
                        "status": "finish",
                        "content": [
                            {"type": "tool_calls", "tool_calls": [{"name": "read", "id": "x", "arguments": {"filePath": "/a.py"}}]}
                        ],
                    }
                ],
            }
        )[0]
    )
    collect(
        accumulator.consume_event(
            {"conversation_id": "c", "parts": [{"logic_id": "b", "content": [{"type": "text", "text": "Zweiter Teil."}]}]}
        )[0]
    )
    collect(accumulator.finalize("finish"))

    message = accumulator.build_response()["choices"][0]["message"]
    assert len(message.get("tool_calls") or []) == 1
    text = "".join(streamed)
    assert "Erster Teil." in text and "Zweiter Teil." in text, repr(text)
    assert text.index("Erster Teil.") < text.index("Zweiter Teil."), "reihenfolge umgestellt"


def test_real_paragraphs_still_get_their_blank_line():
    """Gegenprobe: zwei echte, mit satzzeichen abgeschlossene absaetze
    bekommen ihren absatzumbruch weiterhin."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=None)
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "parts": [{"logic_id": "a", "content": [{"type": "text", "text": "Erster Absatz."}]}],
        }
    )
    accumulator.consume_event(
        {
            "conversation_id": "c",
            "parts": [{"logic_id": "b", "content": [{"type": "text", "text": "Zweiter Absatz."}]}],
        }
    )
    accumulator.finalize("finish")
    content = accumulator.build_response()["choices"][0]["message"].get("content") or ""
    assert content == "Erster Absatz.\n\nZweiter Absatz.", repr(content)


# --- S-07 (Protokoll-Narration statt Protokoll-Nutzung) -------------------

# Live-Befund 2026-09-26, session `glm2api verify 4`: ein turn mit 8
# korrekten parallelen `read`-calls lieferte zusaetzlich diesen monolog als
# sichtbaren text. Wörtlich der text-part, den opencode bekam.
_S07_LIVE_LEAK = (
    "Wrong tool calls above — correcting to the allowed tools:"
    "I must use `read`/`webfetch`/`bash` instead of `open`. Correct JSON protocol:\n\n"
)


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 7, 13, 40, 200])
def test_protocol_narration_never_reaches_the_client_next_to_calls(chunk_size):
    """S-07: das modell ERKLAERT das protokoll, statt es zu benutzen. Ohne
    den fix streamt der monolog unumkehrbar raus (der turn hat calls, also
    greift der finalize-strip nicht mehr)."""
    calls = "".join(
        '{"tool_calls":[{"name":"read","arguments":{"filePath":"/f%d.py"}}]}[]' % index
        for index in range(3)
    )
    text = _S07_LIVE_LEAK + calls
    got = _stream_including_finalize(text, chunk_size, allowed={"read"})
    assert "Wrong tool calls" not in got, f"protokoll-narration im stream: {got!r}"
    assert "instead of `open`" not in got, f"protokoll-narration im stream: {got!r}"
    assert "JSON protocol" not in got, f"protokoll-narration im stream: {got!r}"


@pytest.mark.parametrize("narration", [
    "Wrong tool calls above — correcting to the allowed tools.",
    "Correct JSON protocol:",
    "I must use `read` instead of `open`.",
    "Tool calls above were invalid.",
    "Correcting to the allowed tools now.",
    "Falsche Tool-Calls oben — ich korrigiere auf die erlaubten Tools.",
])
def test_strip_protocol_meta_narration_removes_each_live_form(narration):
    from glm2api.services.translator import strip_protocol_meta_narration

    assert strip_protocol_meta_narration(narration) == ""


def _interleaved_narration_turn():
    """Die EXAKTE part-folge aus dem debug-log (live, glm-5.3, 8 reads).

    Die narration kommt VOR dem ersten aufruf (das T-07-handling
    verwirft sie) und NOCHMAL NACH den aufrufen. Genau die zweite
    passage lief als antwort zum client.
    """
    return [
        {"logic_id": "21436e", "status": "finish",
         "content": [{"type": "text", "text": "Wrong tool calls above — correcting to the allowed tools:"}]},
        {"logic_id": "bd7fc0", "status": "finish",
         "content": [{"type": "tool_calls", "tool_calls": [{"name": "read", "id": "a", "arguments": {"filePath": "/f1.py"}}]}]},
        {"logic_id": "dffe3c", "status": "finish", "content": [{"type": "text", "text": ""}]},
        {"logic_id": "be301b", "status": "finish",
         "content": [{"type": "tool_calls", "tool_calls": [{"name": "read", "id": "b", "arguments": {"filePath": "/f2.py"}}]}]},
        {"logic_id": "5c55d7", "status": "finish",
         "content": [{"type": "text", "text": "I must use `read`/`webfetch`/`bash` instead of `open`. Correct JSON protocol:"}]},
    ]


def test_narration_after_tool_calls_is_also_suppressed():
    """S-07 (verschachtelt): narration NACH den aufrufen. Die T-07-
    praeambel deckt nur die narration VOR dem ersten aufruf ab."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    streamed: list[str] = []

    def collect(chunks):
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])

    for part in _interleaved_narration_turn():
        collect(accumulator.consume_event({"conversation_id": "c", "status": "finish", "parts": [part]})[0])
    collect(accumulator.finalize("finish"))

    text = "".join(streamed)
    assert "Wrong tool calls" not in text, text
    assert "instead of `open`" not in text, text
    assert "JSON protocol" not in text, text
    message = accumulator.build_response()["choices"][0]["message"]
    assert len(message.get("tool_calls") or []) == 2


def test_real_prose_after_tool_calls_still_arrives():
    """Gegenprobe: nach den aufrufen darf echter text ankommen — nur
    protokoll-narration wird entfernt."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    streamed: list[str] = []

    def collect(chunks):
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])

    collect(accumulator.consume_event({"conversation_id": "c", "status": "finish", "parts": [
        {"logic_id": "c0", "status": "finish", "content": [
            {"type": "tool_calls", "tool_calls": [{"name": "read", "id": "a", "arguments": {"filePath": "/f1.py"}}]}]},
    ]})[0])
    collect(accumulator.consume_event({"conversation_id": "c", "parts": [
        {"logic_id": "t0", "content": [{"type": "text", "text": "Erste Datei gelesen, Inhalt: wert-1."}]},
    ]})[0])
    collect(accumulator.finalize("finish"))

    assert "wert-1" in "".join(streamed), streamed


@pytest.mark.parametrize("keep", [
    # der satz nennt `open_url`, redet aber ueber das WERKZEUG, nicht
    # ueber das protokoll — das ist eine echte antwort und muss bleiben.
    "Bitte beachte: open_url ist ein anderes Werkzeug als read.",
    "Die Datei ist da. Ich habe 8 Dateien gelesen.",
    "The file uses 200 instead of 100 lines.",
    "Bericht erstellt: 8 Dateien, Muster wert-1 bis wert-8.",
])
def test_strip_protocol_meta_narration_keeps_real_answers(keep):
    from glm2api.services.translator import strip_protocol_meta_narration

    assert strip_protocol_meta_narration(keep) == keep


def test_narration_stripped_from_text_only_answer():
    """S-07 im finalize-pfad: ein turn OHNE calls, dessen antwort nur aus
    narration besteht, wird nicht als antwort ausgeliefert."""
    from glm2api.services.translator import strip_meta_chatter

    assert strip_meta_chatter(_S07_LIVE_LEAK) == ""
    mixed = _S07_LIVE_LEAK + "Fertig. Der Bericht liegt unter /tmp/bericht.md."
    assert strip_meta_chatter(mixed) == "Fertig. Der Bericht liegt unter /tmp/bericht.md."


# --- S-08 (file:// + unauflösbare native refs + erfundene Inventur) --------


@pytest.mark.parametrize("ref_id,expected", [
    # S-08, live: der allererste aufruf der session
    # `glm2api-Ordner-Analyse` war `file:///workspaces/MAIN/glm2api`.
    ("file:///workspaces/MAIN/glm2api", ("read", {"filePath": "/workspaces/MAIN/glm2api"})),
    ("file:///workspaces/MAIN/llm-proxies/glm2api/", ("read", {"filePath": "/workspaces/MAIN/llm-proxies/glm2api/"})),
    # prozent-encoding muss aufgeloest werden, sonst existiert die datei nicht
    ("file:///workspaces/MAIN/mein%20ordner/a.md", ("read", {"filePath": "/workspaces/MAIN/mein ordner/a.md"})),
    ("file://localhost/tmp/x.txt", ("read", {"filePath": "/tmp/x.txt"})),
    # fremder host ist fuer uns nicht erreichbar
    ("file://server/share/x", None),
    # die CHATGLM-eigenen referenzen bleiben unauflösbar — das ist korrekt
    # und wird durch den hinweistext (S-08) aufgefangen, nicht durch mapping
    ("turn2search0", None),
    ("turn1fetch0", None),
    # Kontrollgruppe: die schon vorher funktionierenden formen
    ("https://example.com", ("webfetch", {"url": "https://example.com"})),
    ("/workspaces/MAIN/x", ("read", {"filePath": "/workspaces/MAIN/x"})),
])
def test_native_open_maps_file_urls(ref_id, expected):
    """S-08: `file://` ist die natuerlichste form fuer 'oeffne dieses lokale
    verzeichnis' und fiel vorher durch — kein http(s), also URL-pruefung
    nein, und `://` im ziel also T-21 'das ist eine URL, kein pfad'."""
    from glm2api.services.translator import map_native_open_tool_call

    payload = json.dumps({"open": [{"ref_id": ref_id, "lineno": 1}]})
    assert map_native_open_tool_call(payload, {"read", "webfetch", "bash"}) == expected


def test_blocked_notice_says_what_to_do_instead():
    """S-08: ein reines 'nein' laesst das modell raten. Live erklärte es
    sich danach 'nur das open-tool stehe mir zur verfügung' und erfand ein
    limit. Der hinweis muss den ausweg benennen."""
    from glm2api.services.glm_client import _blocked_notice_text

    notice = _blocked_notice_text(["open"])
    assert "NOT executed" in notice
    # der ausweg:
    assert "turn1fetch0" in notice and "own web search" in notice.lower()
    assert "Never call these IDs again" in notice
    assert "read" in notice and "glob" in notice and "bash" in notice and "webfetch" in notice
    assert "do not stop" in notice and "tool limit" in notice


@pytest.mark.parametrize("narration", [
    # live 2026-09-26, woertlich
    "In dieser Umgebung steht mir nur das `open`-Tool zur Verfügung, das ausschließlich Web-URLs öffnen kann — der Zugriff auf lokale Dateisystem-Pfade schlägt fehl (Fehler: „open url failed, scrape failed\").",
    "`open` funktioniert nur für Web-URLs, nicht für lokale Pfade.",
    "Ursache war ein Tool-Fehler meinerseits: Ich habe wiederholt das Tool `open` aufgerufen.",
    "Ich musste die Tool-Aufrufe jetzt stoppen.",
    "Die Analyse konnte in dieser Sitzung nicht durchgeführt werden.",
    "Ich kann den Ordner nicht analysieren: In dieser Umgebung steht mir nur das `open`-Tool zur Verfügung.",
    # live repro E
    "The `open` tool doesn't work for local filesystem — switching to `read`/`bash` as required.",
    "`open` ist in dieser Umgebung defekt/für lokale Pfade unzulässig (alle Versuche fehlgeschlagen, Tool-Limit erreicht), daher nur die Struktur, keine Dateiinhalte:",
    "Ich beende den fehlgeschlagenen `open`-Aufruf-Zyklus und wechsle auf `bash`.",
])
def test_hallucinated_tool_inventory_is_stripped(narration):
    """S-08: die erfundene werkzeug-inventur und die erfundete
    abbruch-erklaerung sind keine antwort, sie standen sichtbar beim client."""
    from glm2api.services.translator import strip_protocol_meta_narration

    assert strip_protocol_meta_narration(narration) == "", repr(
        strip_protocol_meta_narration(narration)
    )


def test_narration_removal_never_leaves_a_half_sentence():
    """S-08: mit klauselschnitt blieb ein fragment uebrig — live repro E
    wurde aus '`open` funktioniert nicht fuer lokale Dateien. Ich nutze jetzt
    `read` und `bash`' genau '` nutze `read`:` nicht fuer lokale Dateien.'.
    Der schnitt muss satz-aligned sein."""
    from glm2api.services.translator import strip_protocol_meta_narration

    text = (
        "The `open` tool doesn't work for local filesystem — switching to "
        "`read`/`bash` as required.Ich nutze jetzt `read` und `bash` für die Analyse."
    )
    assert strip_protocol_meta_narration(text) == "", repr(strip_protocol_meta_narration(text))


def test_legitimate_technical_mention_of_open_survives():
    """Gegenprobe: in einem ANALYSE-Bericht ueber den Proxy ist die Aussage
    '`open` ist hier nicht verfuegbar' echter Inhalt, keine Selbstbeschreibung
    des modells."""
    from glm2api.services.translator import strip_protocol_meta_narration

    text = "Analyse abgeschlossen — 8 Dateien, 36 MB. `open` ist hier nicht verfügbar."
    assert strip_protocol_meta_narration(text) == text


@pytest.mark.parametrize("selftalk", [
    # live repro E/F, woertlich
    "`open` ist nur für Web-URLs — für Dateisystem nutze ich jetzt `read`/`bash`:Ich muss das Tool `open` sofort stoppen — es ist ein Web-Tool und bei Dateisystempfaden wirkungslos.",
    "`open` kann keine Dateien lesen. Ich verwende jetzt die richtigen Tools (`read`, `bash`):Ich muss den Vorgang hier abbrechen: Ich habe wiederholt `open` aufgerufen.",
    "Ich nutze jetzt `read` und `bash` für die Analyse.",
    "Ich beende den fehlgeschlagenen `open`-Aufruf-Zyklus und wechsle auf `bash`.",
])
def test_self_steering_is_stripped_in_the_stream(selftalk):
    """S-08: die phrasenliste gegen die narration waechst ins uferlose
    (live repro F: drei woertlich neue formen in einem lauf). Der robuste
    anteil ist die STRUKTUR — erster person + steuer-verb + werkzeug."""
    from glm2api.services.translator import strip_self_steering

    assert strip_self_steering(selftalk) == "", repr(strip_self_steering(selftalk))


@pytest.mark.parametrize("keep", [
    # PAARTEMPEL: die vergangenheitsform ist ein BERICHT, keine steuerung
    "Ich habe 8 Dateien mit `read` gelesen und die Werte geprüft.",
    # erst-person ohne werkzeug-bezug
    "Ich muss den Bericht bis 18 Uhr abgeben.",
    # finale antwort mit technischer aussage ueber open
    "Analyse abgeschlossen — 8 Dateien, 36 MB. `open` ist hier nicht verfügbar.",
])
def test_real_sentences_survive_the_self_steering_filter(keep):
    from glm2api.services.translator import strip_self_steering

    assert strip_self_steering(keep) == keep


def test_self_steering_only_applies_while_the_turn_still_has_calls():
    """S-08: der filter darf den FINALEN bericht nicht entschaerfen. Er
    haengt an der bedingung 'turn hat bereits calls'."""
    narration = "Ich nutze jetzt `read` und `bash` für die Analyse."
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    for part in (
        {
            "logic_id": "c0",
            "status": "finish",
            "content": [
                {"type": "tool_calls", "tool_calls": [{"name": "read", "id": "a", "arguments": {"filePath": "/a.py"}}]}
            ],
        },
        {"logic_id": "t0", "content": [{"type": "text", "text": narration}]},
    ):
        chunks, _ = accumulator.consume_event(
            {"conversation_id": "c", "status": "finish", "parts": [part]}
        )
        streamed = [
            json.loads(chunk[6:].strip())["choices"][0]["delta"].get("content")
            for chunk in chunks
            if chunk.startswith("data: ") and "[DONE]" not in chunk
        ]
    assert not [item for item in streamed if item and item.strip()], streamed


def test_self_steering_never_cuts_a_stream_delta_mid_sentence():
    """S-08: ein stream-delta beginnt mitten im satz. Ein satzweiter
    schnitt darauf erzeugt ein halbwort — live gemessen: aus
    '…fuer Dateisystem nutze ich jetzt `bash`:' wurde
    '`isystem nutze ich jetzt `bash`:'. Im stream darf deshalb NUR
    entfernt werden, was vollstaendig im stueck liegt."""
    from glm2api.services.translator import strip_self_steering

    mid_sentence = "`open` ist hier nur für lokale Dateisystem nutze ich jetzt `bash`:"
    assert strip_self_steering(mid_sentence, require_complete_sentence=True) == mid_sentence

    complete = "Ich nutze jetzt `read` und `bash` für die Analyse. Danach lese ich die Dateien."
    assert strip_self_steering(complete, require_complete_sentence=True) == (
        "Danach lese ich die Dateien."
    )


def test_invented_limit_claim_is_also_filtered_in_the_stream():
    """S-08: der limit-filter sass nur im finalize-pfad. Mid-run-text wird
    aber direkt gestreamt und sieht ihn nie — live stand genau diese zeile
    als assistant-nachricht im client:
    '**Analyse abgebrochen** — das Tool-Limit (8/8) ist erreicht; ich
     musste `open` stoppen.'"""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    narration = (
        "**Analyse abgebrochen** — das Tool-Limit (8/8) ist erreicht; ich musste "
        "`open` stoppen. Ergebnis aus den bisherigen Aufrufen: 8 Dateien."
    )
    chunks, _ = accumulator.consume_event(
        {
            "conversation_id": "c",
            "status": "finish",
            "parts": [
                {
                    "logic_id": "c0",
                    "status": "finish",
                    "content": [
                        {"type": "tool_calls", "tool_calls": [{"name": "read", "id": "a", "arguments": {"filePath": "/a.py"}}]}
                    ],
                },
                {"logic_id": "t0", "content": [{"type": "text", "text": narration}]},
            ],
        }
    )
    streamed = "".join(
        json.loads(chunk[6:].strip())["choices"][0]["delta"].get("content") or ""
        for chunk in chunks
        if chunk.startswith("data: ") and "[DONE]" not in chunk
    )
    assert "Tool-Limit" not in streamed, streamed
    assert "abgebrochen" not in streamed, streamed
    assert "8 Dateien" in streamed, streamed



@pytest.mark.parametrize("keep", [
    "Ich habe 8 Dateien gelesen und die Werte geprueft.",
    "Bericht erstellt: 8 Dateien, Muster wert-1 bis wert-8.",
    "Die Analyse fand 3 Konfigurationsdateien und 12 Testdateien.",
])
def test_real_answers_survive_the_inventory_filter(keep):
    from glm2api.services.translator import strip_protocol_meta_narration

    assert strip_protocol_meta_narration(keep) == keep


@pytest.mark.parametrize("claim,expected", [
    # live repro D 2026-09-26, wortwoertlich der erste satz der antwort
    (
        "Tool-Limit erreicht — hier die Analyse basierend auf den gesammelten Daten:\n\n# Analyse: `glm2api`",
        "# Analyse: `glm2api`",
    ),
    # live, aeltere session `glm2api-Ordner-Analyse`
    ("Tool-Limit (8/8 Runden) erreicht, ich kann nicht weitermachen.", ""),
    ("Ich habe die Analyse abgebrochen: Tokenlimit erreicht.", ""),
    ("Es gibt keine Tools mehr in dieser Umgebung.", ""),
    # live repro E: das 'Tool-Limit' stand nicht am anfang, gerettet hat
    # nur das stopp-wort 'fehlgeschlagen'
    (
        "`open` ist hier unzulässig (alle Versuche fehlgeschlagen, Tool-Limit erreicht), daher nur die Struktur.",
        "",
    ),
    # ein NACKTES 'Limit' ist kein claim, sondern ein gesprächsthema —
    # der text bleibt unangetastet, inklusive '.env.' (dessen punkt ist
    # kein satzende)
    (
        "Der Bericht enthält 8 Dateien. Das Limit liegt laut .env bei 131072.",
        "Der Bericht enthält 8 Dateien. Das Limit liegt laut .env bei 131072.",
    ),
])
def test_invented_limit_claim_is_stripped(claim, expected):
    """S-08: die erfundene limit-meldung ist die schaedlichste form — das
    modell hoert danach auf zu arbeiten und liefert dem client eine fertige
    antwort samt abbruchgrund."""
    from glm2api.services.translator import strip_invented_limit_claim

    assert strip_invented_limit_claim(claim) == expected


@pytest.mark.parametrize("keep", [
    # OHNE abbruchwort und NICHT am anfang: ein technischer bericht ueber
    # die limit-KONFIGURATION bleibt stehen. Das ist der gewollte
    # tradeoff — eine limit-erwaehnung in den ersten 200 zeichen wird
    # entfernt, weiter hinten nicht.
    "# Konfiguration\nBei GLM_MAX_OUTPUT_TOKENS=131072 greift finish_reason=length.",
    "Ich habe 8 Dateien gelesen. Die Werte sind ok.",
])
def test_limit_mentions_in_technical_reports_survive(keep):
    from glm2api.services.translator import strip_invented_limit_claim

    assert strip_invented_limit_claim(keep) == keep


def test_limit_claim_reaches_the_client_path():
    """S-08: der filter haengt an `strip_meta_chatter`, damit er im
    finalize-pfad (turn ohne calls) UND im stream-pfad greift."""
    from glm2api.services.translator import strip_meta_chatter

    text = "Tool-Limit erreicht — hier die Analyse:\n\n# Analyse: glm2api"
    assert strip_meta_chatter(text) == "# Analyse: glm2api"


def test_native_tool_call_as_list_is_parsed_with_all_guards():
    protocol = {"name": "read", "id": "a", "arguments": {"filePath": "/a.py"}}

    allowed = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    allowed.consume_event(
        {
            "conversation_id": "c",
            "status": "finish",
            "parts": [
                {"logic_id": "p", "status": "finish", "content": [{"type": "tool_calls", "tool_calls": [protocol]}]}
            ],
        }
    )
    allowed.finalize("finish")
    calls = allowed.build_response()["choices"][0]["message"].get("tool_calls") or []
    assert [call["function"]["name"] for call in calls] == ["read"]

    # die Wächter der Listenform gelten genauso
    for tools, entry, label in (
        (None, protocol, "keine Tools deklariert"),
        ({"bash"}, protocol, "Tool nicht erlaubt"),
        ({"read"}, {"name": "open_url", "id": "b", "arguments": {"url": "https://x"}}, "gesperrtes native tool"),
    ):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names=tools)
        accumulator.consume_event(
            {
                "conversation_id": "c",
                "status": "finish",
                "parts": [
                    {"logic_id": "p", "status": "finish", "content": [{"type": "tool_calls", "tool_calls": [entry]}]}
                ],
            }
        )
        accumulator.finalize("finish")
        response = accumulator.build_response()

        assert not (response["choices"][0]["message"].get("tool_calls") or []), label
        # Ein GESPERRTER aufruf ist keine fehlerhafte runde, sondern eine
        # vollstaendige antwort ("dieses werkzeug gibt es nicht"). Als
        # `error` wertete der echte client das als stream-fehler und
        # wiederholte den turn mit 5-minuten-backoff endlos — gemessen am
        # agentenlauf 2026-09-26, wo `open` (natives GLM-werkzeug) bei jedem
        # versuch erneut aufgerufen wurde. Der aufruf selbst wird weiterhin
        # NICHT ausgeliefert (das sichert die zeile davor).
        assert response["choices"][0]["finish_reason"] == "stop", label


# --- S-12: tool_choice none ist eine verbotssplicht --------------------


def test_tool_choice_none_refuses_a_spontaneous_call():
    """S-12: `tool_choice: none` blendete nur die tool-schemata aus dem
    prompt. Ein trotzdem erzeugter aufruf wurde regulaer ausgeliefert —
    der client, der tools ausdruecklich verboten hat, bekam trotzdem einen
    strukturierten tool-call (das inverse routing-problem zu `required`)."""
    accumulator = GLMEventAccumulator(
        model="m",
        allowed_tool_names={"bash"},
        tool_choice_mode="none",
    )
    accumulator.consume_event({
        "conversation_id": "c",
        "parts": [{"logic_id": "p1", "content": [
            {"type": "text", "text": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]'}]}],
    })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert not message.get("tool_calls"), "der aufruf darf nicht ausgeliefert werden"
    assert "tool_choice_violation" in (message.get("content") or "")
    assert "bash" in (message.get("content") or "")


def test_tool_choice_none_non_stream_matches_stream():
    """Paritaet: der non-stream-pfad muss denselben aufruf verweigern."""
    accumulator = GLMEventAccumulator(
        model="m",
        allowed_tool_names={"bash"},
        tool_choice_mode="none",
    )
    accumulator.consume_event({
        "conversation_id": "c",
        "parts": [{"logic_id": "p1", "content": [
            {"type": "text", "text": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]'}]}],
    })
    response = accumulator.build_response("finish")
    message = response["choices"][0]["message"]

    assert not message.get("tool_calls")
    assert "tool_choice_violation" in (message.get("content") or "")
    assert response["choices"][0]["finish_reason"] == "error"


def test_tool_choice_none_still_allows_plain_text():
    """Gegenprobe: `none` heisst 'keine tools', nicht 'keine antwort'."""
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"bash"}, tool_choice_mode="none",
    )
    accumulator.consume_event({
        "conversation_id": "c",
        "parts": [{"logic_id": "p1", "content": [{"type": "text", "text": "Hier ist die Antwort."}]}],
    })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert not message.get("tool_calls")
    assert "Hier ist die Antwort." in (message.get("content") or "")
    assert "tool_choice_violation" not in (message.get("content") or "")


# --- T-20: die delta-berechnung muss nicht ueber alle parts laufen -------


def _measure_part_accumulation(count: int) -> float:
    """Sekunden fuer `count` getrennte logic_ids (T-20-Messung)."""
    import time

    text = "hier ist ein text. " * 3
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"bash"}, max_output_tokens=16384
    )
    start = time.perf_counter()
    for index in range(count):
        accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": text}]}],
        })
    accumulator.finalize("finish")
    accumulator.build_response()
    return time.perf_counter() - start


def test_t20_delta_computation_scales_linearly():
    """T-20: `_compute_deltas()` lief pro event ueber ALLE bekannten
    parts. Gemessen superlinear: 3,5 s / 1000 parts, 20,7 s / 2000 parts,
    je verdopplung 4-7x. Nach der Korrektur: 0,33 s / 0,89 s, Faktor ~2.

    Der vergleich laeuft ueber eine GROSSE strecke (8x), weil kleine
    absolute zeiten im ci-umfeld verrauschen. Quadratisch waere Faktor
    64, linear Faktor 8 — die schranke 24 trennt das mit grossem
    abstand und ist trotzdem weit ueber dem linearen erwartungswert."""
    _measure_part_accumulation(200)  # aufwaermen: erstlauf fuellt caches

    small = _measure_part_accumulation(2000)
    large = _measure_part_accumulation(16000)

    growth = large / max(small, 1e-4)
    # gemessen: 8x parts kosten ~3,9x zeit (das ausgabe-budget greift
    # frueh, danach wird nichts mehr zusammengefuegt). Linear waere 8x,
    # quadratisch 64x — 24 trennt das mit grossem abstand.
    assert growth < 24.0, f"zu superlinear: 8x parts kosteten {growth:.1f}x zeit (linear ~8x, quadratisch ~64x)"


def test_t20_optimisation_keeps_the_output_identical():
    """Gegenprobe zur Optimierung: es darf kein inhalt verloren gehen."""
    text = "hier ist ein text. " * 3
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    for index in range(200):
        accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": text}]}],
        })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    content = message.get("content") or ""
    assert content.count("hier ist ein text.") == 200 * 3


def test_t20_continuing_parts_are_not_separated():
    """Die eigentliche T-20-symptomatik, gegenprobe zur optimierung:
    ein text, der MITTEN IM SATZ ueber mehrere parts verteilt ist
    ("Die Datei" / "DieDatei"), darf an der part-grenze nicht
    zerrissen werden. Hier ist der satz nicht beendet, also darf
    kein absatzumbruch entstehen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    for index, piece in enumerate(["Die Datei", " ist im ", "Repository gefunden"]):
        accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": piece}]}],
        })
    accumulator.finalize("finish")
    content = accumulator.build_response()["choices"][0]["message"].get("content") or ""

    assert "Die Datei ist im Repository gefunden" in content
    assert "\n\n" not in content


def test_output_cap_does_not_shrink_the_budget():
    """Regression (2026-09-25, gefunden am wiederaufgenommenen
    agentenlauf): der performance-guard im render-pfad verglich gegen
    `_output_budget_remaining()` — also gegen ein budget, aus dem der
    bereits gesendete text (und das reasoning) schon abgezogen war.
    Zaehlte man den aufgebauten text noch einmal dagegen, halbierte sich
    die grenze: gemessen 16 629 statt 32 768 zeichen, also 50,7 % —
    `finish_reason: length` bei JEDEM turn. Mit `reasoning_effort: max`
    (das frisst `_output_chars` zusaetzlich) blieb fast nichts ueber.

    Der vertrag: was der stream-pfad liefern wuerde, muss auch geliefert
    werden. Der guard darf nur den quadratischen aufbau abbrechen."""
    for max_tokens in (2048, 8192):
        accumulator = GLMEventAccumulator(
            model="m", allowed_tool_names={"read"}, max_output_tokens=max_tokens,
        )
        part = "hier ist ein textabsatz. " * 10
        for index in range(2000):
            accumulator.consume_event({
                "conversation_id": "c",
                "status": "process",
                "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": part}]}],
            })
        accumulator.finalize("finish")
        choice = accumulator.build_response()["choices"][0]
        content = choice["message"].get("content") or ""
        budget = max_tokens * 4  # _CHARS_PER_TOKEN_ESTIMATE

        assert len(content) >= budget * 0.99, (
            f"max_tokens={max_tokens}: nur {len(content)} von {budget} zeichen geliefert "
            f"({len(content) / budget * 100:.1f}%)"
        )
        assert choice["finish_reason"] == "length", "die grenze muss weiterhin greifen"


def test_reasoning_cannot_consume_the_whole_output_budget():
    """Regression (2026-09-25, zweite): an einer echten opencode-session
    mit `reasoning_effort: max` fraess das denkkanal das GANZE budget.
    Log: `reasoning_len=61 820`, der client bekam 1 768 zeichen
    reasoning, NULL text, NULL tool_calls, `finish_reason: length` —
    ein abgeschlossener, erfolgreicher turn, in dem fuer den agenten
    nichts zu tun war. Der auftrag war unerfuellbar.

    Der denkkanal darf hoechstens `_REASONING_BUDGET_SHARE` des budgets
    nehmen; der rest ist fuer die lieferung reserviert."""
    from glm2api.services.translator import (
        _CHARS_PER_TOKEN_ESTIMATE,
        _REASONING_BUDGET_SHARE,
    )

    max_tokens = 8192
    budget = max_tokens * _CHARS_PER_TOKEN_ESTIMATE

    # reasoning, das das doppelte des budgets fuer sich beansprucht
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names={"read", "bash"}, max_output_tokens=max_tokens,
    )
    # `type: "think"` ist die reale GLM-reasoning-form (aus dem log)
    for index, part in enumerate(["Ich denke nach. " * 3000, "Noch mehr nachdenken. " * 1000]):
        accumulator.consume_event({
            "conversation_id": "c",
            "status": "process",
            "parts": [{"logic_id": f"r{index}", "content": [{"think": part}]}],
        })
    accumulator.consume_event({
        "conversation_id": "c",
        "status": "process",
        "parts": [{"logic_id": "t0", "content": [{"type": "text", "text": "Hier ist die Antwort."}]}],
    })
    accumulator.finalize("finish")
    message = accumulator.build_response()["choices"][0]["message"]

    assert _REASONING_BUDGET_SHARE < 1.0, "das reasoning darf nie das ganze budget nehmen"
    assert (message.get("content") or "").strip(), (
        "der lieferkanal muss text bekommen — sonst ist der turn fuer den "
        "agenten unbrauchbar"
    )
    # und das budget selbst bleibt voll ausgeschoepft
    text_only = GLMEventAccumulator(model="m", allowed_tool_names={"read"}, max_output_tokens=max_tokens)
    for index in range(2000):
        text_only.consume_event({
            "conversation_id": "c",
            "status": "process",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": "hier ist ein textabsatz. " * 10}]}],
        })
    text_only.finalize("finish")
    only_text = text_only.build_response()["choices"][0]["message"].get("content") or ""
    assert len(only_text) >= budget * 0.99, f"nur {len(only_text)} von {budget} zeichen"


def test_blocked_tool_is_stop_but_a_broken_turn_is_still_error():
    """Der unterschied ist der ganze fix.

    Ein GESPERRTER aufruf ist eine vollstaendige antwort: das modell hat
    geantwortet, der hinweis sagt ausdruecklich, dass nichts ausgefuehrt
    wurde. Als `error` wertete der echte client das als stream-fehler und
    wiederholte den turn mit exponentiellem backoff (5 min gemessen) —
    endlosschleife, weil `open` bei jedem versuch erneut aufgerufen wird.

    Ein ABGESCHNITTENER turn dagegen fehlt dem client wirklich etwas
    Brauchbares — dort bleibt `error` richtig, ein Retry ist berechtigt.
    """
    # (a) gesperrter aufruf -> stop
    blocked = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    blocked.consume_event({
        "conversation_id": "c",
        "status": "finish",
        "parts": [{"logic_id": "p1", "content": [
            {"type": "text", "text": '{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]'}]}],
    })
    blocked.finalize("finish")
    blocked_choice = blocked.build_response()["choices"][0]
    assert blocked_choice["finish_reason"] == "stop"
    assert "unavailable tool" in (blocked_choice["message"].get("content") or "")

    # (b) abgeschnittener turn -> error bleibt
    truncated = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    truncated.consume_event({
        "conversation_id": "c",
        "status": "finish",
        "parts": [{"logic_id": "p1", "content": [{"type": "text", "text": '{"tool_calls":[{"name":"bash","arguments":{"command":"ls -'}]}],
    })
    truncated.finalize("finish")
    assert truncated.build_response()["choices"][0]["finish_reason"] == "error"


def test_blocked_only_turn_ends_cleanly_in_both_paths():
    """Die praezise trennung, an beiden abschluss-pfaden.

    Ein GESPERRTER aufruf ist eine vollstaendige antwort: das werkzeug
    gibt es nicht, das modell hat das gemerkt und weitergearbeitet. Als
    `error` ging dieser turn im echten agentenlauf in eine endlose
    retry-schleife (5 min backoff je versuch, 2026-09-26).

    Ein ERLAUBTER aufruf mit fehlendem pflichtargument ist dagegen ein
    echter fehlschlag — dort bleibt `error`, und genau diese
    unterscheidung ist der kern des fixes. Beide pfade muessen dasselbe
    sagen, sonst haengt der client je nach aufrufpfad.
    """
    blocked = '{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]'
    unusable = '{"tool_calls":[{"name":"write","arguments":{"filePath":"/a.py"}}]}[]'

    for payload, allowed, expected in (
        (blocked, {"bash"}, "stop"),
        (unusable, {"write", "read", "bash"}, "error"),
    ):
        for path in ("stream", "non-stream"):
            accumulator = GLMEventAccumulator(model="m", allowed_tool_names=allowed)
            accumulator.consume_event(
                _event("c", "p1", text=payload, status="process")
            )
            if path == "stream":
                accumulator.finalize("finish")
                finish = accumulator.build_response()["choices"][0]["finish_reason"]
            else:
                finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
            assert finish == expected, f"{path} / {payload[:40]} -> {finish}, erwartet {expected}"


# --- S-09 (Narration ueber Delta-Grenzen) + Nachbesserung -----------------
#
# S-09 haelt text VOR dem parser zurueck, solange sein letzter satz noch
# narration werden kann — sonst sieht kein filter beide haelfte eines
# satzes in einem string (live repro M: 'Der `open`-Tool-Aufruf
# funktioniert ... fuer lokale Pfade - ich nutze stattdessen `read`/`bash`:'
# lief ueber drei stream-deltas und kam komplett durch).
#
# Der Nachtrag: der ausloeser matcht auch `tool_calls`, und damit griff er
# auf das JSON-PROTOKOLL des aufrufs selbst. Folge war keine verzoegerung,
# sondern ein echter fehler — der parser sah den aufruf erst im `finalize`,
# und T-06 (`dropped_call_count` -> `truncated_turn` -> `error`) war da
# schon entschieden. Zwei tests wurden rot und blieben es.


def _feed_deltas(deltas, allowed=None):
    """Delta-folge streamen; liefert (sichtbarer_stream, accumulator).

    Der stream wird INKLUSIVE der `finalize`-chunks gesammelt — der
    deferred-puffer landet beim client ueber diesen pfad, nicht ueber
    `build_response().content` (das ist nur der gecachte volltext).
    """
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names=allowed or {"read", "bash"}
    )
    streamed: list[str] = []

    def collect(chunks):
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
            if delta.get("content"):
                streamed.append(delta["content"])

    for index, text in enumerate(deltas):
        chunks, _ = accumulator.consume_event(
            {
                "conversation_id": "c",
                "parts": [
                    {
                        "logic_id": f"p{index}",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        )
        collect(chunks)
    collect(accumulator.finalize("finish"))
    return "".join(streamed), accumulator


# Live repro M (2026-09-26 19:29, 20 tool-calls im turn): ein text-part
# enthielt drei varianten desselben selbstgespraechs, aneinandergeklebt,
# weil die saetze ueber mehrere deltas liefen.
_S09_NARRATION = (
    "Der `open`-Tool-Aufruf funktioniert in dieser Umgebung nicht zuverlässig für "
    "lokale Pfade – ich nutze stattdessen `read`/`bash`:\n"
    "The `open` tool only works for web URLs — for local files I need to use "
    "`read`/`bash`:"
)


def _s09_deltas(chunk_size: int):
    """Der repro-M-text als delta-kette, jeweils mitten im satz zerschnitten."""
    call = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    deltas = [call]
    for index in range(0, len(_S09_NARRATION), chunk_size):
        deltas.append(_S09_NARRATION[index : index + chunk_size])
    return deltas


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 13, 29, len(_S09_NARRATION)])
def test_mid_run_narration_across_delta_boundaries_is_stripped(chunk_size):
    """S-09: die narration laeuft ueber mehrere deltas; ohne den
    carry-holdback sieht der filter nie beide haelfte eines satzes und
    alles kommt durch (live: drei varianten aneinandergeklebt)."""
    streamed, _accumulator = _feed_deltas(_s09_deltas(chunk_size))

    assert "nur das `open`-Tool" not in streamed
    assert "only works for web URLs" not in streamed, streamed
    assert "Tool-Aufruf funktioniert" not in streamed, streamed


@pytest.mark.parametrize("chunk_size", [1, 5, 17, 40])
def test_narration_holdback_still_delivers_a_valid_call(chunk_size):
    """Gegenprobe zum holdback: verzoegerung ist erlaubt, textverlust nicht.
    Der aufruf muss ankommen — egal wo die delta-grenzen fallen."""
    streamed, accumulator = _feed_deltas(_s09_deltas(chunk_size))

    names = [
        call["function"]["name"]
        for call in (accumulator.build_response()["choices"][0]["message"].get("tool_calls") or [])
    ]
    assert names == ["read"], (chunk_size, names, streamed)


@pytest.mark.parametrize("chunk_size", [1, 4, 11, 33])
def test_narration_holdback_never_hides_an_unusable_call(chunk_size):
    """Der eigentliche schaden des fehlalarm-alten holdbacks (S-09-Nachtrag).

    `read` ohne `filePath` ist ein ERLAUBTER aufruf mit fehlendem
    pflichtargument: T-06 sagt da `error`, weil dem client etwas
    Brauchbares fehlt. Der holdback hat den aufruf erst im `finalize`
    freigegeben — zu spaet fuer die einstufung. Ergebnis war der leere
    ERFOLG: `stop` mit leerem inhalt, der agent blieb stehen.
    """
    payload = '{"tool_calls":[{"name":"read","arguments":{}}]}[]'
    deltas = [payload[index : index + chunk_size] for index in range(0, len(payload), chunk_size)]

    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        for index, text in enumerate(deltas):
            accumulator.consume_event(_event("c", f"p{index}", text=text))
        if path == "stream":
            accumulator.finalize("finish")
            finish = accumulator.build_response()["choices"][0]["finish_reason"]
        else:
            finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
        assert finish == "error", f"{path} / chunk={chunk_size} -> {finish}, erwartet error"


def test_unusable_call_behind_narration_prose_is_still_an_error():
    """Der alltagsfall aus repro M: erst narration, dann der (unbrauchbare)
    aufruf. Die narration wird herausgefiltert, der aufruf muss trotzdem
    eingestuft werden — beides in einem turn."""
    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        accumulator.consume_event(
            _event("c", "p1", text="Der `open`-Aufruf funktioniert hier nicht, ich nutze `read`.")
        )
        accumulator.consume_event(
            _event("c", "p2", text='{"tool_calls":[{"name":"read","arguments":{}}]}[]')
        )
        if path == "stream":
            accumulator.finalize("finish")
            finish = accumulator.build_response()["choices"][0]["finish_reason"]
        else:
            finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
        assert finish == "error", f"{path} -> {finish}, erwartet error"


def test_blocked_call_behind_narration_prose_still_ends_with_stop():
    """Gegenprobe zur selben stelle: ein GESPERRTER aufruf ist eine
    vollstaendige antwort und endet mit `stop` — als `error` wiederholte
    der echte client den turn endlos (5 min backoff, agentenlauf
    2026-09-26)."""
    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        accumulator.consume_event(
            _event("c", "p1", text="Der `open`-Aufruf funktioniert hier nicht, ich nutze `read`.")
        )
        accumulator.consume_event(
            _event("c", "p2", text='{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]')
        )
        if path == "stream":
            accumulator.finalize("finish")
            finish = accumulator.build_response()["choices"][0]["finish_reason"]
        else:
            finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
        assert finish == "stop", f"{path} -> {finish}, erwartet stop"


def test_complete_sentence_never_waits_for_the_next_delta():
    """Der holdback darf nicht die auslieferung verzoegern, wenn gar nichts
    mehr kommt: ein text mit Satzende geht sofort raus."""
    _streamed, accumulator = _feed_deltas(["Ich nutze jetzt `read` fuer die Datei."])
    assert accumulator._narration_carry == ""


def test_long_unterminated_sentence_is_released_by_the_length_deckel():
    """Prosa ohne Satzende, laenger als der deckel: weiter warten hat keinen
    sinn, der text muss fliessen (sonst haengt eine ausgabe ohne
    satzgrenze bis zum turn-ende)."""
    long_prose = "Der Bericht nennt open als Werkzeug und " + ("beschreibt die Dateien " * 40)
    _streamed, accumulator = _feed_deltas([long_prose])
    assert accumulator._narration_carry == ""


# --- contains_tool_markup: die entscheidung, die der holdback vorher traf --


@pytest.mark.parametrize("text", [
    '{"tool_calls":[{"name":"read","arguments":{}}]}[]',
    '{"tool_calls":',
    'prefix {"tool_calls": [{"name": "bash"}]}',
    "… <tool_calls_begin> …",
    "… </tool_call_end> …",
    "… <tool_call> …",
])
def test_contains_tool_markup_recognises_protocol(text):
    from glm2api.utils.tool_protocol import contains_tool_markup

    assert contains_tool_markup(text) is True, text


@pytest.mark.parametrize("text", [
    "",
    "Der `open`-Aufruf funktioniert hier nicht, ich nutze stattdessen `read`.",
    "I need to use read instead of open.",
    "Das Tool-Limit (8/8) ist erreicht.",
    "Ich öffne die Datei mit dem Editor.",
    "Ein Beispiel: {\"name\": \"beispiel\"} sieht so aus.",
])
def test_contains_tool_markup_leaves_prose_alone(text):
    from glm2api.utils.tool_protocol import contains_tool_markup

    assert contains_tool_markup(text) is False, text


# --- Abschluss-Einstufung: chunkgroessen-unabhaengig (S-09-Nachtrag) ---------
#
# `dropped_call_count` zaehlt TEIL-PARSE-VERSUCHE, nicht unbrauchbare
# aufrufe, und haengt deshalb an der zerschnittenheit des upstream-texts
# (gemessen: derselbe gesperrte aufruf ergibt chunk=100 -> 1, chunk=3 -> 4,
# chunk=1 -> 0). Folge war der schlimmste fehler der ganzen reihe: ein
# GESPERRTER aufruf, der ueber mehrere deltas kam, endete als `error` — also
# genau der fall, fuer den commit c8135d9 den `stop` eingefuehrt hatte. Der
# echte client wertete das als stream-fehler und wiederholte den turn mit
# 5-minuten-backoff endlos (agentenlauf 2026-09-26). Gemessen in 9 von 15
# chunk-groessen, in BEIDEN abschluss-pfaden.


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 5, 7, 9, 11, 13, 17, 21, 29, 37, 55, 100])
def test_blocked_call_split_across_deltas_ends_with_stop(chunk_size):
    """Ein gesperrter aufruf ist eine vollstaendige antwort — in jeder
    zerschnittenheit. `error` hiesse: retry-schleife."""
    payload = '{"tool_calls":[{"name":"open_url","arguments":{"url":"https://x"}}]}[]'
    deltas = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]

    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
        for index, text in enumerate(deltas):
            accumulator.consume_event(_event("c", f"p{index}", text=text))
        if path == "stream":
            accumulator.finalize("finish")
            finish = accumulator.build_response()["choices"][0]["finish_reason"]
        else:
            finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
        assert finish == "stop", f"{path} / chunk={chunk_size} -> {finish}, erwartet stop"


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 19, 100])
def test_unusable_call_split_across_deltas_ends_as_error(chunk_size):
    """Gegenprobe: `read` ohne `filePath` ist ERLAUBT und fehlt dem client ->
    `error` (T-06). In jeder zerschnittenheit, sonst sieht der agent einen
    leeren, erfolgreichen turn und bleibt stehen."""
    payload = '{"tool_calls":[{"name":"read","arguments":{}}]}[]'
    deltas = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]

    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        for index, text in enumerate(deltas):
            accumulator.consume_event(_event("c", f"p{index}", text=text))
        if path == "stream":
            accumulator.finalize("finish")
            finish = accumulator.build_response()["choices"][0]["finish_reason"]
        else:
            finish = accumulator.build_response("finish")["choices"][0]["finish_reason"]
        assert finish == "error", f"{path} / chunk={chunk_size} -> {finish}, erwartet error"


@pytest.mark.parametrize("chunk_size", [1, 4, 12, 60])
def test_valid_call_split_across_deltas_still_executes(chunk_size):
    """Der gesperrte/unbrauchbare fall wird jetzt am TEXT entschieden. Der
    normale fall darf davon unberuehrt bleiben: der aufruf muss laufen."""
    payload = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    deltas = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]

    for path in ("stream", "non-stream"):
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        for index, text in enumerate(deltas):
            accumulator.consume_event(_event("c", f"p{index}", text=text))
        if path == "stream":
            accumulator.finalize("finish")
            message = accumulator.build_response()["choices"][0]["message"]
        else:
            message = accumulator.build_response("finish")["choices"][0]["message"]
        names = [c["function"]["name"] for c in (message.get("tool_calls") or [])]
        assert names == ["read"], f"{path} / chunk={chunk_size} -> {names}"


def test_text_attempted_tools_separates_prose_from_protocol():
    """Die entscheidungsgrundlage: protokoll im text und die namen, die
    darin stehen. Prosa liefert (leer, False) — sonst wuerde jeder
    erwaehnte werkzeugname den turn als fehlschlag einstufen."""
    from glm2api.services.translator import GLMEventAccumulator

    cases = [
        ('{"tool_calls":[{"name":"read","arguments":{}}]}[]', {"read"}, True),
        ('{"tool_calls":[{"name":"open_url","arguments":{}}]}[]', {"open_url"}, True),
        # abgeschnitten, aber der NAME ist lesbar — genau deshalb kann die
        # entscheidung fallen, ohne auf den parser-zustand zu schauen
        ('{"tool_calls":[{"name":"read","arguments":{"filePa', {"read"}, True),
        # abgeschnitten, und der name ist nicht lesbar: protokoll da,
        # namen leer -> "dem client fehlt etwas" -> `error`
        ('{"tool_calls":[{"nam', set(), True),
        ("Ich nutze jetzt `read` fuer die Datei.", set(), False),
        ("", set(), False),
    ]
    for text, expected_names, expected_protocol in cases:
        accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
        accumulator._cached_full_text = text
        names, has_protocol = accumulator._text_attempted_tools()
        assert names == expected_names, (text, names)
        assert has_protocol is expected_protocol, (text, has_protocol)


# --- DSML ueber Part-Grenzen (2026-09-26) ---------------------------------
#
# Der part-merge schuetzte nur JSON: `{"tool_calls":` ist eine offene
# Klammer, da wird nichts eingefuegt. DSML/XML hat keine Klammern, und die
# entscheidung fiel an `_starts_new_block` — `|` und `>` am Part-Anfang
# gelten als Markdown-Bloecke (Tabelle, Zitat), sind im DSML aber
# Protokollzeichen. Folge: der merge setzte mitten im Markup einen
# Absatzumbruch, der Aufruf wurde zerschnitten und kam nicht mehr an; das
# zerschnittene Markup landete als Antworttext beim Client.
#
# Gemessen vor dem Fix: der Aufruf ging bei 34 von 147 Chunk-Groessen
# verloren (bei 126 von 147, bevor T-20 den Merge inkrementell machte) — und
# so war es seit dem ersten Commit, in dem glm2api im Repo liegt.

_DSML_CALL = (
    '<|DSML|tool_calls><|DSML|invoke name="read">'
    '<|DSML|parameter name="filePath"><![CDATA[/a.py]]></|DSML|parameter>'
    '</|DSML|invoke></|DSML|tool_calls>\n'
)


def _dsml_run(pieces, path):
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    for index, piece in enumerate(pieces):
        accumulator.consume_event(_event("c", f"p{index}", text=piece))
    if path == "stream":
        accumulator.finalize("finish")
        message = accumulator.build_response()["choices"][0]["message"]
    else:
        message = accumulator.build_response("finish")["choices"][0]["message"]
    return [call["function"]["name"] for call in (message.get("tool_calls") or [])]


@pytest.mark.parametrize("path", ["stream", "non-stream"])
def test_dsml_call_survives_every_chunk_size(path):
    """Jede Zerschnittenheit muss denselben Aufruf ergeben. Stichprobe ueber
    alle Chunk-Groessen (1 Zeichen bis zum ganzen Text) — das ist die Form,
    in der ChatGLM live liefert."""
    lost = [
        size
        for size in range(1, len(_DSML_CALL) + 1)
        if _dsml_run([_DSML_CALL[i : i + size] for i in range(0, len(_DSML_CALL), size)], path)
        != ["read"]
    ]
    assert not lost, f"{path}: Aufruf verloren bei Chunk-Groessen {lost[:12]}"


@pytest.mark.parametrize("path", ["stream", "non-stream"])
def test_dsml_call_after_prose_survives_part_split(path):
    """Der Live-Fall: Text und Markup in getrennten Parts, mit Schnitt
    mitten im Tag."""
    for split in range(0, len(_DSML_CALL), 7):
        pieces = ["Ich lese die Datei.\n", _DSML_CALL[:split], _DSML_CALL[split:]]
        assert _dsml_run(pieces, path) == ["read"], (path, split)


def test_markdown_blocks_still_get_a_paragraph_break():
    """Gegenprobe zum Fix: `|` und `>` am Part-Anfang sind AUSSERHALB von
    Markup genau das, wofuer sie gedacht sind. Ein Zitat und eine Tabelle
    muessen weiterhin als eigene Bloecke im Text landen."""
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read"})
    accumulator.consume_event(_event("c", "p1", text="Einleitung"))
    accumulator.consume_event(_event("c", "p2", text="> Zitat aus der Anleitung"))
    accumulator.consume_event(_event("c", "p3", text="| Spalte | Spalte |"))
    accumulator.finalize("finish")
    content = accumulator.build_response()["choices"][0]["message"]["content"] or ""

    assert "\n\n> Zitat aus der Anleitung" in content, content
    assert "\n\n| Spalte | Spalte |" in content, content


def test_markup_state_does_not_leak_into_prose():
    """Gegenprobe zum Gegen-Test: nach einem geschlossenen DSML-block muss
    der merge wieder normal arbeiten — ein haengender `in_call_run`-zustand
    wuerde jeden folgenden absatz verschlucken.

    Geprueft wird `_join_parts_incremental` direkt: der turn hat einen
    aufruf, und im non-stream-response ist `content` per OpenAI-vertrag leer,
    sobald `tool_calls` da sind — der cache sagt dann nichts ueber den
    merge aus.
    """
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"read", "bash"})
    parts: list[str] = []
    for index, text in enumerate([_DSML_CALL, "Fertig gelesen.", "> Zitat aus der Anleitung"]):
        accumulator.consume_event(_event("c", f"p{index}", text=text))
        parts.append(text)
        joined = accumulator._join_parts_incremental(parts, "text")

    assert "\n\n> Zitat aus der Anleitung" in joined, joined
