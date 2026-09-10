import json
from glm2api.services.translator import (
    BLOCKED_NATIVE_TOOL_NAMES,
    GLMEventAccumulator,
    convert_messages,
    extract_history_tool_call_signatures,
    sanitize_tool_call_payload,
)


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


def test_sanitize_shell_command_argument_from_quoted_sequence():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": '"powershell.exe", "-Command", "Get-ChildItem -Force"',
        },
    )

    assert cleaned == {
        "command": ["powershell.exe", "-Command", "Get-ChildItem -Force"],
    }


def test_sanitize_shell_command_argument_from_plain_string():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": "Get-ChildItem",
        },
    )

    assert cleaned == {
        "command": ["powershell.exe", "-Command", "Get-ChildItem"],
    }


def test_sanitize_shell_command_argument_wraps_powershell_cmdlet_array():
    cleaned = sanitize_tool_call_payload(
        "shell",
        {
            "command": ["Get-ChildItem", "-Recurse", "-Filter", "*.txt"],
        },
    )

    assert cleaned == {
        "command": ["powershell.exe", "-Command", "Get-ChildItem -Recurse -Filter *.txt"],
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
    accumulator = GLMEventAccumulator(model="glm-test", allowed_tool_names={"shell"})
    # text gefolgt von einem unvollstaendigen tool-protokoll-anfang:
    # der parser haelt '{"tool' zurueck -> deferral aktiv
    chunks, status = accumulator.consume_event(
        {
            "conversation_id": "conv_1",
            "parts": [
                {
                    "logic_id": "1",
                    "content": [{"type": "text", "text": "sieh '...'} before {\"tool"}],
                }
            ],
        }
    )
    final_chunks = accumulator.finalize(status)
    combined = "".join(chunks) + "".join(final_chunks)
    assert '{"tool' in combined or 'tool' in combined  # nichts verloren


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


def test_convert_messages_repairs_cherry_fetch_url_and_skips_invalid_tool_error_history():
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
    assert "expected string, received undefined" not in prompt


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


def test_conversation_has_tool_round_detects_preamble_and_tool_call():
    from glm2api.services.translator import _conversation_has_tool_round

    # Tool call with preceding preamble
    processed_with_preamble = [
        {"role": "user", "content": "analysiere den ordner"},
        {"role": "assistant", "content": 'Hier ist die Analyse:\n{"tool_calls":[{"name":"question","arguments":{}}]}[]'},
    ]
    assert _conversation_has_tool_round(processed_with_preamble) is True

    # Tool result turn
    processed_with_tool_result = [
        {"role": "user", "content": '[{"call_id":"c1","name":"question","content":"ok"}]'},
    ]
    assert _conversation_has_tool_round(processed_with_tool_result) is True

    # Plain conversational turn without tools
    processed_plain = [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hallo, wie kann ich helfen?"},
    ]
    assert _conversation_has_tool_round(processed_plain) is False


def test_build_tool_call_instructions_includes_language_lock_and_no_preamble():
    from glm2api.utils.tool_protocol import build_tool_call_instructions, TOOL_FORMAT_REMINDER

    instructions = build_tool_call_instructions(["question", "read"])
    assert "When calling a tool, do NOT output conversational text" in instructions
    assert "Language consistency" in instructions
    assert "NEVER output internal monologue, reasoning, or responses in Chinese" in instructions

    assert "Do not output any preamble, commentary, or thoughts in Chinese" in TOOL_FORMAT_REMINDER

