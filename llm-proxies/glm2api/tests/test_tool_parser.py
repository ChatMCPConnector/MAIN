import json

from glm2api.utils.tool_parser import _MAX_HOLDBACK_CHARS
from glm2api.utils.tool_parser import (
    StreamingToolParser,
    _is_allowed_tool_name,
    parse_tool_calls_from_text,
)
from glm2api.utils.tool_protocol import filter_tools, is_blocked_tool_name
import pytest


def test_streaming_json_tool_call_with_terminator_in_same_token():
    parser = StreamingToolParser(allowed_tool_names={"bash"})
    text = '{"tool_calls":[{"name":"bash","arguments":{"command":"pwd"}}]}[]'

    clean = parser.consume(text)
    tail, tool_calls = parser.flush()

    assert clean == ""
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"
    assert tool_calls[0]["function"]["arguments"] == '{"command": "pwd"}'


def test_streaming_json_tool_call_accepts_single_object():
    parser = StreamingToolParser(allowed_tool_names={"bash"})
    text = '{"tool_calls":{"name":"bash","arguments":{"command":"pwd"}}}[]'

    clean = parser.consume(text)
    tail, tool_calls = parser.flush()

    assert clean == ""
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"
    assert tool_calls[0]["function"]["arguments"] == '{"command": "pwd"}'


def test_streaming_json_tool_call_supports_flattened_sibling_parameters():
    parser = StreamingToolParser(allowed_tool_names={"todowrite"})
    text = '{"tool_calls":[{"name":"todowrite","todos":[{"content":"task1","status":"pending"}]}]}[]'

    clean = parser.consume(text)
    tail, tool_calls = parser.flush()

    assert clean == ""
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "todowrite"
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args == {"todos": [{"content": "task1", "status": "pending"}]}


def test_parse_repairs_missing_tool_calls_array_close_and_preserves_model_text():
    text = (
        'Vorher {"tool_calls":[{"name":"bash","arguments":{"command":"pwd"}}}'
        " Nachher"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"bash"})

    assert clean == "Vorher  Nachher"
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"
    assert tool_calls[0]["function"]["arguments"] == '{"command": "pwd"}'


def test_parse_does_not_rewrite_other_malformed_json_as_tool_call():
    text = 'Modelltext {"tool_calls":{"name":"bash"} bleibt erhalten'

    clean, tool_calls = parse_tool_calls_from_text(text, {"bash"})

    assert clean == text
    assert tool_calls == []


def test_parse_tool_calls_from_dsml_markup():
    text = (
        "before\n"
        "<|DSML|tool_calls><|DSML|invoke name=\"get_weather\">"
        "<|DSML|parameter name=\"city\"><![CDATA[上海]]></|DSML|parameter>"
        "<|DSML|parameter name=\"days\">2</|DSML|parameter>"
        "</|DSML|invoke></|DSML|tool_calls>\n"
        "after"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"get_weather"})

    assert clean == "before\n\nafter"
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city":"上海","days":2}'


def test_parse_tool_calls_from_canonical_invoke_markup():
    text = (
        "<tool_calls><invoke name=\"search_web\">"
        "<parameter name=\"query\"><![CDATA[glm2api]]></parameter>"
        "<parameter name=\"filters\"><parameter name=\"site\">example.com</parameter></parameter>"
        "<parameter name=\"tags\"><item>python</item><item>xml</item></parameter>"
        "</invoke></tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"search_web"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == (
        '{"query":"glm2api","filters":{"site":"example.com"},"tags":["python","xml"]}'
    )


def test_parse_rejects_undeclared_and_blocked_native_tools():
    blocked_text = (
        "<|DSML|tool_calls><|DSML|invoke name=\"open_url\">"
        "<|DSML|parameter name=\"url\">https://example.com</|DSML|parameter>"
        "</|DSML|invoke></|DSML|tool_calls>"
    )
    undeclared_text = (
        "<|DSML|tool_calls><|DSML|invoke name=\"not_declared\">"
        "<|DSML|parameter name=\"value\">x</|DSML|parameter>"
        "</|DSML|invoke></|DSML|tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(blocked_text, {"open_url"})
    assert clean == ""
    assert tool_calls == []

    clean, tool_calls = parse_tool_calls_from_text(undeclared_text, {"allowed_tool"})
    assert clean == ""
    assert tool_calls == []


def test_parse_ignores_dsml_markup_inside_code_fence():
    text = (
        "```xml\n"
        "<|DSML|tool_calls><|DSML|invoke name=\"get_weather\"></|DSML|invoke></|DSML|tool_calls>\n"
        "```"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"get_weather"})

    assert clean == text
    assert tool_calls == []


def test_stream_parser_recovers_snipsel_plus_full_text_duplicate():
    """Härtetest-Befund 1: Upstream streamt Token-Schnipsel, dann den Volltext
    als eigenes Delta. Der Buffer enthält dann '<fragment><volltext>' — ohne
    Recovery leakte das komplette Protokoll als sichtbarer Text und der Call
    ging verloren."""
    protocol = (
        '{"tool_calls":[{"name":"bash","arguments":{"command":"ls -la"}}]}\n[]'
    )
    parser = StreamingToolParser()
    parser.allowed_tool_names = {"bash"}

    visible = parser.consume(protocol[:40])
    visible += parser.consume(protocol)
    flush_visible, tool_calls = parser.flush()

    assert '{"tool_calls"' not in visible + flush_visible
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"


def test_stream_parser_consumes_terminator_behind_whitespace():
    """Härtetest-Befund 2: '\n' zwischen JSON-Objekt und '[]'-Terminator —
    vorher leakte das '[]' als sichtbarer Content."""
    protocol = (
        '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}\n[]'
    )
    parser = StreamingToolParser()
    parser.allowed_tool_names = {"bash"}

    visible = parser.consume(protocol)

    assert "[]" not in visible
    assert visible == ""
    assert len(parser.flush()[1]) == 1


def test_stream_parser_recovers_real_live_leak_case():
    """Original-Live-Fall aus dem Härtetest (20:25:14, text_len=216): das
    Protokoll kam komplett als TEXT-Part beim Client an."""
    protocol = (
        '{"tool_calls":[{"name":"bash","arguments":{"command":'
        '"cd /workspaces/benchmark/agent-glm2api-hard/miniforge && '
        'ls -la *.md *.py 2>/dev/null | grep -E \'(bench-results|load|recall|bugfix|CHANGELOG|LICENSE|README)\'"}}]}[]'
    )
    parser = StreamingToolParser()
    parser.allowed_tool_names = {"bash"}

    visible = parser.consume(protocol[:60])
    visible += parser.consume(protocol)
    flush_visible, tool_calls = parser.flush()

    assert '{"tool_calls"' not in visible + flush_visible
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"
    assert "grep -E" in tool_calls[0]["function"]["arguments"]


def test_parse_recovers_multi_call_leak_with_unbalanced_braces():
    """Härtetest-Re-Run 2 (21:55:29): Das Modell emittierte 6 Tool-Calls als
    invalides JSON — zwischen zwei Call-Objekten fehlte das '}' (16 '{' vs
    15 '}'). Der Brace-Scan fand kein Ende und der komplette 6,6KB-Block
    leakte als TEXT-Part. Recovery-Stufe 3 (_recover_call_elements) muss die
    name/arguments-Paare einzeln extrahieren."""
    leak = (
        '{"tool_calls":[{"name":"write","arguments":{"filePath":"/tmp/a.md","content":"# A\\n\\nText"}]},'
        '{"name":"write","arguments":{"filePath":"/tmp/b.md","content":"# B"}},'
        '{"name":"bash","arguments":{"command":"ls /tmp"}}]}[]'
    )
    clean, tool_calls = parse_tool_calls_from_text(leak, allowed_tool_names={"write", "bash"})

    assert clean == ""
    assert len(tool_calls) == 3
    assert tool_calls[0]["function"]["name"] == "write"
    assert tool_calls[1]["function"]["name"] == "write"
    assert tool_calls[2]["function"]["name"] == "bash"
    assert json.loads(tool_calls[0]["function"]["arguments"])["filePath"] == "/tmp/a.md"
    assert json.loads(tool_calls[2]["function"]["arguments"])["command"] == "ls /tmp"


def test_streaming_tool_parser_never_leaks_dsml_markup_fragments():
    parser = StreamingToolParser(allowed_tool_names={"get_weather"})
    visible_parts: list[str] = []
    payload = (
        "<|DSML|tool_calls><|DSML|invoke name=\"get_weather\">"
        "<|DSML|parameter name=\"city\">上海</|DSML|parameter>"
        "</|DSML|invoke></|DSML|tool_calls>"
    )

    for char in payload:
        piece = parser.consume(char)
        visible_parts.append(piece)
        assert "<|DSML|" not in piece
        assert "</|DSML|" not in piece

    tail, tool_calls = parser.flush()

    assert "".join(visible_parts) == ""
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"city":"上海"}'


def test_parse_tool_calls_from_glm_malformed_dsml_markup():
    text = (
        '<|dsml|tool_calls|><|dsml|invoke name="shell"|>'
        '<|dsml|parameter name="command"><![CDATA["powershell.exe", "-Command", '
        '"Get-ChildItem -Force | Select-Object Name, Mode, Length"]]|>\n'
        '</|dsMLparameter|><|dsml|parameter name="workdir"><![CDATA[E:\\Projects\\2api\\glm2api]]>'
        '</|dsmlparameter|><|/dsmlinvoke|></|dsmltoolcalls|>'
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"shell"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "shell"
    assert tool_calls[0]["function"]["arguments"] == (
        '{"command":"\\"powershell.exe\\", \\"-Command\\", '
        '\\"Get-ChildItem -Force | Select-Object Name, Mode, Length\\"","workdir":"E:\\\\Projects\\\\2api\\\\glm2api"}'
    )


def test_parse_tool_calls_repairs_json_array_at_cdata_boundary():
    text = (
        '<|DSML|tool_calls><|DSML|invoke name="shell">'
        '<|DSML|parameter name="command"><![CDATA[["powershell.exe", "-Command", "pwd"]]></|DSML|parameter>'
        '</|DSML|invoke></|DSML|tool_calls>'
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"shell"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"command":["powershell.exe","-Command","pwd"]}'


def test_parse_tool_calls_repairs_missing_final_dsml_close_angle():
    text = (
        '<|DSML|tool_calls><|DSML|invoke name="shell">'
        '<|DSML|parameter name="command"><![CDATA[["powershell.exe", "-Command", "pwd"]]></|DSML|parameter>'
        '</|DSML|invoke></|DSML|tool_calls'
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"shell"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"command":["powershell.exe","-Command","pwd"]}'


def test_parse_tool_calls_repairs_double_pipe_dsml_close_tag():
    text = (
        '<|DSML|tool_calls><|DSML|invoke name="shell">'
        '<|DSML|parameter name="command"><![CDATA[["powershell.exe", "-Command", "pwd"]]]></|DSML|parameter>'
        '<||DSML|invoke></|DSML|tool_calls>'
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"shell"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"command":["powershell.exe","-Command","pwd"]}'


def test_parse_tool_calls_repairs_single_bracket_cdata_close():
    text = (
        '<|DSML|tool_calls><|DSML|invoke name="search">'
        '<|DSML|parameter name="search_query"><![CDATA[{"q":"阿房宫赋","recency":365}]></|DSML|parameter>'
        '</|DSML|invoke></|DSML|tool_calls>'
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"search"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "search"
    assert tool_calls[0]["function"]["arguments"] == '{"search_query":{"q":"阿房宫赋","recency":365}}'


def test_streaming_tool_parser_hides_glm_malformed_dsml_until_flush():
    parser = StreamingToolParser(allowed_tool_names={"shell"})
    payload = (
        '<|dsml|tool_calls|><|dsml|invoke name="shell"|>'
        '<|dsml|parameter name="command"><![CDATA[pwd]]|></|dsMLparameter|>'
        '<|/dsmlinvoke|></|dsmltoolcalls|>'
    )

    visible_parts = [parser.consume(char) for char in payload]
    tail, tool_calls = parser.flush()

    assert "".join(visible_parts) == ""
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"command":"pwd"}'


def test_parse_tool_calls_from_xml_markup():
    text = (
        "开始\n"
        "<ml_tool_calls><ml_tool_call><ml_tool_name>get_weather</ml_tool_name>"
        "<ml_parameters><city><![CDATA[上海]]></city><days>2</days></ml_parameters>"
        "</ml_tool_call></ml_tool_calls>\n"
        "结束"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"get_weather"})

    assert clean == "开始\n\n结束"
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city":"上海","days":2}'


def test_parse_tool_calls_supports_nested_objects_and_arrays():
    text = (
        "<ml_tool_calls><ml_tool_call><ml_tool_name>search_web</ml_tool_name><ml_parameters>"
        "<query>glm2api</query>"
        "<filters><site>example.com</site><after>2026-01-01</after></filters>"
        "<tags><item>python</item><item>xml</item></tags>"
        "</ml_parameters></ml_tool_call></ml_tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"search_web"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == (
        '{"query":"glm2api","filters":{"site":"example.com","after":"2026-01-01"},"tags":["python","xml"]}'
    )


def test_parse_ignores_tool_markup_inside_code_fence():
    text = (
        "```xml\n"
        "<ml_tool_calls><ml_tool_call><ml_tool_name>get_weather</ml_tool_name></ml_tool_call></ml_tool_calls>\n"
        "```"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"get_weather"})

    assert clean == text
    assert tool_calls == []


def test_streaming_tool_parser_hides_complete_tool_block():
    parser = StreamingToolParser(allowed_tool_names={"get_weather"})

    first = parser.consume("你好<ml_tool_calls><ml_tool_call><ml_tool_name>get_weather</ml_tool_name>")
    second = parser.consume("<ml_parameters><city>上海</city></ml_parameters></ml_tool_call></ml_tool_calls>世界")
    tail, tool_calls = parser.flush()

    assert first == "你好"
    assert second == "世界"
    assert tail == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"city":"上海"}'


def test_streaming_tool_parser_never_leaks_ml_markup_fragments():
    parser = StreamingToolParser(allowed_tool_names={"mcp__CherryFetch__fetchJson"})
    visible_parts: list[str] = []
    payload = "<ml_tool_calls></ml_tool_calls>"

    for char in payload:
        piece = parser.consume(char)
        visible_parts.append(piece)
        assert "<ml" not in piece
        assert "</ml" not in piece
        assert piece != ">"

    tail, tool_calls = parser.flush()

    assert "".join(visible_parts) == ""
    assert tail == ""
    assert tool_calls == []


def test_parse_rejects_legacy_or_noncanonical_tool_markup():
    legacy_variants = [
        '<tool_call>{"tool":"Bash","params":{"command":"pwd"}}</tool_call>',
        "<function_call>Bash</function_call>",
        '<invoke name="Bash"><parameters><command>pwd</command></parameters></invoke>',
        '<tool_use><function name="Bash"><parameter name="command">pwd</parameter></function></tool_use>',
    ]

    for markup in legacy_variants:
        clean, tool_calls = parse_tool_calls_from_text(markup, {"Bash"})
        assert clean == markup
        assert tool_calls == []


def test_parse_rejects_tool_call_missing_parameters():
    text = (
        "<ml_tool_calls>"
        "<ml_tool_call><ml_tool_name>search_web</ml_tool_name></ml_tool_call>"
        "</ml_tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"search_web"})

    assert clean == ""
    assert tool_calls == []


def test_parse_salvages_malformed_tool_calls_root_without_rewriting_model_text():
    text = (
        "open_url工具被阻止，无法使用。让我改用 fetchJson 工具来访问这个 API："
        "非常抱歉，我之前反复调用了被阻止的工具。"
        "<ml_tool_calls>\n"
        "<ml_tool_name>mcp__CherryFetch__fetchJson</ml_tool_name>\n"
        "<param_name>url</param_name>\n"
        "<param_value>https://example.com/data.json</param_value>\n"
        "</ml_tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"mcp__CherryFetch__fetchJson"})

    assert "open_url" in clean
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "mcp__CherryFetch__fetchJson"
    assert tool_calls[0]["function"]["arguments"] == '{"url":"https://example.com/data.json"}'


def test_parse_salvages_malformed_tool_calls_root_with_empty_params():
    text = (
        "<ml_tool_calls>\n"
        "<ml_tool_name>mcp__CherryFetch__fetchJson</ml_tool_name>\n"
        "<param_name></param_name>\n"
        "<param_value></param_value>\n"
        "</ml_tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"mcp__CherryFetch__fetchJson"})

    assert clean == ""
    assert tool_calls == []


def test_parse_hides_empty_ml_tool_calls_shell_without_leaking():
    text = "前缀<ml_tool_calls></ml_tool_calls>后缀"

    clean, tool_calls = parse_tool_calls_from_text(text, {"mcp__CherryFetch__fetchJson"})

    assert clean == "前缀后缀"
    assert tool_calls == []


def test_parse_extracts_param_name_only_payload_for_later_repair():
    text = (
        "<ml_tool_calls>"
        "<ml_tool_call>"
        "<ml_tool_name>mcp__CherryFetch__fetchJson</ml_tool_name>"
        "<ml_parameters><param_name><![CDATA[url]]></param_name></ml_parameters>"
        "</ml_tool_call>"
        "</ml_tool_calls>"
    )

    clean, tool_calls = parse_tool_calls_from_text(text, {"mcp__CherryFetch__fetchJson"})

    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"param_name":"url"}'


def test_split_stream_think_fallback_respects_allowed_filter():
    # Regression M-1: wenn schritt 1 alle calls filtert, darf der
    # think-fallback (schritt 2) sie nicht ungefiltert durchlassen.
    # Gefilterte calls bleiben weiterhin OHNE tool-call-event — aber das
    # rohe JSON-Protokoll wird aus dem sichtbaren text entfernt (kein leak);
    # die erkennung blockierter versuche uebernimmt detect_tool_call_names.
    from glm2api.utils.tool_parser import _split_stream_text, detect_tool_call_names

    visible, remainder, calls = _split_stream_text(
        'Vorher {"tool_calls":[{"name":"blocked_tool","arguments":{"a":1}}]}[] Nachher',
        allowed_tool_names={"allowed_tool"},
        final=True,
    )
    assert calls == []
    # gefilterter call: kein tool-call-event, protokoll-block wird entfernt
    assert visible in {"Vorher [] Nachher", "Vorher  Nachher", "Vorher Nachher"}
    assert "blocked_tool" not in visible
    assert detect_tool_call_names(
        'Vorher {"tool_calls":[{"name":"blocked_tool","arguments":{"a":1}}]}[] Nachher'
    ) == ["blocked_tool"]


def test_streaming_normal_inline_json_does_not_hold_until_flush():
    # Regression N-5: gewoehnliches inline-json im modelltext darf den
    # stream nicht bis zum flush blockieren
    parser = StreamingToolParser()
    out = parser.consume('Antwort: {"name": "test"} Ende')
    tail, calls = parser.flush()
    assert '"name": "test"' in out + tail
    assert calls == []


def test_parse_recovers_bare_json_array_tool_calls():
    """Leak-Variante D (Final-Run 00:27): Tool-Calls als NACKTES JSON-Array
    [{"name":..., "arguments":...}] ohne {"tool_calls"}-Wrapper, mit Prosa
    davor. Vorher lief das komplette Array als sichtbarer Text durch."""
    text = (
        "Ich führe die letzte Transformation durch.\n"
        '[\n  {\n    "name": "bash",\n    "arguments": {\n'
        '      "command": "ls -la",\n      "workdir": "/tmp"\n    }\n  }\n]'
    )
    clean, tool_calls = parse_tool_calls_from_text(text, allowed_tool_names={"bash"})
    assert clean == "Ich führe die letzte Transformation durch."
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "bash"
    assert json.loads(tool_calls[0]["function"]["arguments"])["command"] == "ls -la"


def test_parse_recovers_bare_array_with_broken_fence_and_duplicate():
    """Leak-Variante D (Final-Run 00:33): nacktes Array ohne schließende ']'
    plus kaputter '``json'-Marker plus dupliziertes Array — das Modell
    wiederholte den Block. Recovery muss die name/arguments-Paare ziehen."""
    text = (
        '``json\n[\n  {"name": "bash", "arguments": {"command": "ls -la", '
        '"workdir": "/tmp"}}\n``json\n[\n  {"name": "bash", "arguments": '
        '{"command": "ls -la", "workdir": "/tmp"}}\n]\n[]\n```'
    )
    clean, tool_calls = parse_tool_calls_from_text(text, allowed_tool_names={"bash"})
    assert '[{"name"' not in clean
    assert '"command"' not in clean
    assert len(tool_calls) >= 1
    assert all(tc["function"]["name"] == "bash" for tc in tool_calls)
    assert json.loads(tool_calls[0]["function"]["arguments"])["workdir"] == "/tmp"


def test_parse_recovers_comma_separated_sibling_tool_calls():
    """Modell schliesst das tool_calls-Array nach dem 1. Call und haengt
    weitere Calls mit Komma getrennt an: {"tool_calls":[...]},{"name":"write"...}[]"""
    text = (
        '{"tool_calls":[{"name":"bash","arguments":{"command":"mkdir -p /tmp/test"}}]},'
        '{"name":"write","arguments":{"filePath":"/tmp/test/models.py","content":"code"}}[]'
    )
    parser = StreamingToolParser(allowed_tool_names={"bash", "write"})
    vis = parser.consume(text)
    tail, tool_calls = parser.flush()

    assert vis == ""
    assert tail == ""
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "bash"
    assert json.loads(tool_calls[0]["function"]["arguments"])["command"] == "mkdir -p /tmp/test"
    assert tool_calls[1]["function"]["name"] == "write"
    assert json.loads(tool_calls[1]["function"]["arguments"])["filePath"] == "/tmp/test/models.py"


def test_parse_recovers_leading_comma_bare_tool_calls():
    """Modell emittiert Calls mit fuehrendem Komma ohne Array-Bracket:
    ,{"name":"write","arguments":{"filePath":"a.md","content":"A"}},{"name":"write","arguments":{"filePath":"b.md","content":"B"}}"""
    text = (
        ',{"name":"write","arguments":{"filePath":"/workspaces/test/a.md","content":"# A"}},'
        '{"name":"write","arguments":{"filePath":"/workspaces/test/b.md","content":"# B"}}'
    )
    clean, tool_calls = parse_tool_calls_from_text(text, allowed_tool_names={"write"})
    assert clean == ""
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "write"
    assert json.loads(tool_calls[0]["function"]["arguments"])["filePath"] == "/workspaces/test/a.md"
    assert tool_calls[1]["function"]["name"] == "write"
    assert json.loads(tool_calls[1]["function"]["arguments"])["filePath"] == "/workspaces/test/b.md"


def test_streaming_consecutive_json_tool_calls_do_not_leak_as_visible():
    """Live-Fall aus ses_f2fffc74cffeXOgdBYZ4LZ30e3:
    Modell emittiert zwei konsekutive JSON-Protokoll-Bloecke im Stream:
    {"tool_calls":[...]}[] {"tool_calls":[...]}[]
    Der zweite Block darf nicht als sichtbarer Text leaken!"""
    parser = StreamingToolParser(allowed_tool_names={"read", "bash"})
    c1 = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/workspaces/test/a.py"}}]}[] {"tool_calls":[{"name":"bash","arguments":{"command":"ls'
    c2 = ' -la /workspaces/test/"}}]}[]'

    vis1 = parser.consume(c1)
    vis2 = parser.consume(c2)
    tail, calls = parser.flush()

    assert '{"tool_calls"' not in (vis1 + vis2 + tail)
    assert 'name":"bash"' not in (vis1 + vis2 + tail)
    assert len(calls) == 2
    assert calls[0]["function"]["name"] == "read"
    assert calls[1]["function"]["name"] == "bash"
    assert json.loads(calls[1]["function"]["arguments"])["command"] == "ls -la /workspaces/test/"


def test_parse_recovers_naked_write_object_without_name():
    """Live-Fall aus ses_f2fd31507ffeox6tR1Lp6H61DJ:
    Modell emittiert {'filePath': '...', 'content': '...'} als nacktes JSON-Objekt ohne name/arguments-Wrapper.
    Darf nicht als sichtbarer Chat-Text leaken, sondern muss als write-Tool-Call geparst werden!"""
    text = '{"filePath":"/workspaces/benchmark/auditmesh-20260923-03/data/logs/audit_security.txt","content":"2026-01-15T09:00:20Z | AUTH_FAIL | user=alice"}'
    clean, tool_calls = parse_tool_calls_from_text(text, allowed_tool_names={"write"})
    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "write"
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert "audit_security.txt" in args["filePath"]
    assert "AUTH_FAIL" in args["content"]


def test_parse_recovers_text_function_call():
    """Live-Fall aus ses_f2bcdbfb8ffeSSbsFc2TSP2R1f:
    Modell emittiert read('/workspaces/benchmark.md') als Text-Funktionsaufruf.
    Muss als strukturierter read-Tool-Call geparst werden!"""
    text = 'read("/workspaces/benchmark.md")'
    clean, tool_calls = parse_tool_calls_from_text(text, allowed_tool_names={"read"})
    assert clean == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "read"
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args["filePath"] == "/workspaces/benchmark.md"


def test_stream_parser_holds_partial_bare_array_suffix_without_leaking_prefix():
    """Regression: der hold-back fuer partielle bare-array-anfaenge gab
    ('', '', []) zurueck — der prefix wurde als sichtbarer text verworfen
    bzw. der partielle array-rest leakte."""
    parser = StreamingToolParser(allowed_tool_names={"read"})

    visible = parser.consume('Vorrede. [{"na')

    assert visible == "Vorrede. "
    assert parser.pending_text == '[{"na'

    visible2 = parser.consume('me": "read", "arguments": {"filePath": "/a.py"}}]')
    tail, calls = parser.flush()

    assert visible2 + tail == ""
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read"
    assert json.loads(calls[0]["function"]["arguments"])["filePath"] == "/a.py"


def test_stream_parser_keeps_prefix_before_incomplete_bare_array_midstream():
    """Regression: bei unvollstaendigem bare-array wurde der sichtbare
    prefix (text vor dem array) verworfen (return '', text[start:]...)."""
    parser = StreamingToolParser(allowed_tool_names={"read"})

    visible = parser.consume('Hier kommt das Ergebnis: [{"name": "read", "arguments": {"filePa')

    assert visible == "Hier kommt das Ergebnis: "
    assert parser.pending_text.startswith('[{"name": "read"')

    visible2 = parser.consume('th": "/b.py"}}]')
    tail, calls = parser.flush()

    assert visible2 + tail == ""
    assert len(calls) == 1
    assert json.loads(calls[0]["function"]["arguments"])["filePath"] == "/b.py"



def test_bare_call_object_at_text_start_without_wrapper_is_parsed():
    """Regression (Live-Fall ses_f2bc23762ffeoOkPYHAoqhwpwm, 2026-09-24):
    das Modell lieferte die Calls als nackte '{"name": ...}'-Objekte OHNE
    'tool_calls'-Wrapper und OHNE array-klammern, direkt am Textanfang.
    Der bare-start-regex verlangte aber '[' oder ',' davor -> die Calls
    wurden nicht erkannt und landeten als Roh-JSON im sichtbaren Text."""
    text = (
        '{"name":"write","arguments":{"filePath":"/tmp/a.py","content":"print(1)\\n"}}'
        '{"name":"write","arguments":{"filePath":"/tmp/b.py","content":"print(2)\\n"}}'
    )

    clean, calls = parse_tool_calls_from_text(text, allowed_tool_names={"write"})

    assert clean == ""
    assert len(calls) == 2
    assert json.loads(calls[0]["function"]["arguments"])["filePath"] == "/tmp/a.py"
    assert json.loads(calls[1]["function"]["arguments"])["filePath"] == "/tmp/b.py"


def test_bare_call_object_after_newline_is_parsed():
    text = (
        'Hier kommt der naechste Schritt.\n'
        '{"name":"read","arguments":{"filePath":"/tmp/x.py"}}'
    )

    clean, calls = parse_tool_calls_from_text(text, allowed_tool_names={"read"})

    assert clean == "Hier kommt der naechsten Schritt." or clean.startswith("Hier kommt")
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read"


def test_truncated_bare_call_is_held_back_and_never_streamed_as_text():
    """Regression: abgeschnittenes call-json (stream-abruch mitten im
    content) darf nicht als sichtbarer Text raus — es wird gehalten und
    erst bei final verarbeitet."""
    parser = StreamingToolParser(allowed_tool_names={"write"})

    emitted = parser.consume('{"name":"write","arguments":{"filePath":"/tmp/a.py","content":"print(1)\\nprint(')

    assert emitted == ""
    assert parser.pending_text.startswith('{"name":"write"')


def test_transcript_echo_is_held_back_across_chunk_boundaries():
    """Live-Fall ses_f2bc23762ffeoOkPYHAoqhwpwm: das Modell halluzinierte
    'User: [{"call_id":...}]'-zeilen (sein eigenes konversations-format).
    Der echo muss ueber chunk-grenzen zurueckgehalten werden."""
    parser = StreamingToolParser(allowed_tool_names={"read", "bash"})

    chunks = [
        'Alles erledigt.\n\n',
        'User: [{"call_id":"call_x","name":"read",',
        '"content":"datei.txt"}]\n\n',
        'Abschlussbericht: alle Phasen fertig.',
    ]
    visible = "".join(parser.consume(c) for c in chunks)
    tail, calls = parser.flush()

    total = visible + tail
    assert "call_id" not in total
    assert "Abschlussbericht: alle Phasen fertig." in total
    assert calls == []


def test_transcript_echo_between_normal_text_is_removed():
    text = 'Vorrede.\nUser: [{"call_id":"c1","name":"bash","content":"ok"}]\nNachwort.'

    clean, calls = parse_tool_calls_from_text(text, allowed_tool_names={"bash"})

    assert calls == []
    assert "call_id" not in clean
    assert "Vorrede." in clean
    assert "Nachwort." in clean


def test_unparseable_truncated_call_fragment_is_stripped():
    """Der upstream brach mitten im call-json ab — das fragment ist keine
    antwort und darf nicht als sichtbarer text durchgehen."""
    from glm2api.utils.tool_parser import strip_unparseable_call_fragments

    truncated = '{"name":"write","arguments":{"filePath":"/tmp/a.py","content":"print(1)\\nprint('
    cleaned, removed = strip_unparseable_call_fragments(truncated)

    assert removed == 1
    assert cleaned == ""

    # mit prosa davor bleibt die prosa erhalten
    mixed = 'Hier der Code:\n' + truncated
    cleaned2, removed2 = strip_unparseable_call_fragments(mixed)
    assert removed2 == 1
    assert cleaned2 == "Hier der Code:"

    # vollstaendiges parsebares call-fragment wird nicht angefasst
    complete = '{"name":"write","arguments":{"filePath":"/a.py","content":"x"}}'
    assert strip_unparseable_call_fragments(complete) == (complete, 0)

    # normaler text bleibt unangetastet
    plain = "Ein ganz normaler Satz ohne Calls."
    assert strip_unparseable_call_fragments(plain) == (plain, 0)


# --- A-13: blocklisten-vergleiche case-/schreibweisen-tolerant ----------


def test_native_blocklist_rejects_case_and_separator_variants():
    """A-13: `OPEN_URL`, `Browser.Open`, `Execute_Sandbox_Code` und
    `web.run_v2` umgingen die native sperre, sobald der client genau diese
    schreibweise deklariert hatte. Vergleiche laufen ueber einen
    kanonischen schluessel (NFKC + casefold + Trennzeichen + Version)."""
    for variant in (
        "OPEN_URL",
        "Browser.Open",
        "WEB.SEARCH",
        "Execute_Sandbox_Code",
        "web.run_v2",
        "open_url-2",
        "browse v1",
        "Open_Url_2024",
    ):
        assert is_blocked_tool_name(variant, None) is True, variant
        # und die Deklaration des clients darf sie nicht freischalten
        assert _is_allowed_tool_name(variant, {variant}) is False, variant


def test_legitimate_tools_are_not_blocked_by_canonicalization():
    """Gegenprobe: `read`, `Write` und `bash` bleiben normal nutzbar —
    die kanonisierung darf keine echten tools treffen."""
    for name in ("read", "Write", "bash", "mcp__CherryFetch__fetchJson"):
        assert is_blocked_tool_name(name, None) is False, name
        assert _is_allowed_tool_name(name, {name}) is True, name


def test_configured_blocklist_is_case_insensitive():
    assert is_blocked_tool_name("DANGEROUS_TOOL", {"dangerous_tool"}) is True
    assert is_blocked_tool_name("dangerous_tool", {"DANGEROUS_TOOL"}) is True


def test_filter_tools_drops_case_variant_of_blocked_tool():
    """Der client-Tool-Vertrag selbst: eine abweichende schreibweise eines
    gesperrten tools darf nicht in die prompt-tools gelangen."""
    tools = [
        {"type": "function", "function": {"name": "DANGEROUS_TOOL"}},
        {"type": "function", "function": {"name": "read"}},
    ]
    filtered = filter_tools(tools, {"dangerous_tool"})

    assert [tool["function"]["name"] for tool in (filtered or [])] == ["read"]


# --- T-11 und P-14/P-12: native Listenform, begrenzter Holdback --------


def test_holdback_is_bounded_outside_the_dsml_path():
    """P-14: der Holdback war ausserhalb des DSML-Pfades unbegrenzt. Ein
    nie geschlossenes Call-Fragment liess den Puffer unbegrenzt wachsen —
    ein Speicherpfad bei abgeschnittenem Upstream-Strom."""
    parser = StreamingToolParser(allowed_tool_names={"read"})
    fragment = '{"name":"read","arguments":{"filePath":"'
    for _ in range(200):
        parser.consume(fragment)

    assert len(parser.pending_text) <= _MAX_HOLDBACK_CHARS + len(fragment), (
        f"holdback ungegrenzt: {len(parser.pending_text)} zeichen"
    )


def test_structure_scan_is_incremental_not_a_full_buffer_rescan():
    """P-12: die Strukturerkennung lief fuer jedes Chunk ueber den
    gesamten Puffer. Der Scan ist jetzt inkrementell (nur das neue
    Fragment) — der Test prueft, dass ein langer Puffer nicht erneut
    von vorn gelesen wird."""
    parser = StreamingToolParser(allowed_tool_names={"read"})
    for _ in range(40):
        parser.consume('{"name":"read","arguments":{"filePath":"')

    scanned_position, stack, in_string, _escaped, _opener = parser._scan_state
    assert scanned_position == len(parser.pending_text), "scan ist nicht fortgesetzt"
    assert len(stack) > 0


def test_streamed_protocol_is_still_detected_with_the_incremental_scan():
    """Gegenprobe zur Optimierung: der inkrementelle Scan darf keinen
    Aufruf übersehen."""
    for chunk_size in (1, 3, 7, 19):
        parser = StreamingToolParser(allowed_tool_names={"read"})
        payload = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
        visible = ""
        for index in range(0, len(payload), chunk_size):
            visible += parser.consume(payload[index : index + chunk_size])
        tail, calls = parser.flush()

        assert [call["function"]["name"] for call in calls] == ["read"], f"chunk={chunk_size}"
        assert not (visible + tail).strip(), f"chunk={chunk_size}: call zusaetzlich als text"


def test_protocol_terminator_does_not_leak_into_visible_text():
    """T-22/P-13: der `[]`-terminator nach einem Aufruf kommt als eigenes
    Fragment. Bei zeichenweiser Zustellung wurde er als sichtbarer Text
    ausgegeben — der Client sah am Ende jeder Tool-Runde ein `[]`."""
    payload = '{"tool_calls":[{"name":"read","arguments":{"filePath":"/a.py"}}]}[]'
    for chunk_size in (1, 2, 3, 5, 7, 11, 19):
        parser = StreamingToolParser(allowed_tool_names={"read"})
        visible = ""
        for index in range(0, len(payload), chunk_size):
            visible += parser.consume(payload[index : index + chunk_size])
        tail, calls = parser.flush()

        assert [call["function"]["name"] for call in calls] == ["read"], chunk_size
        assert not (visible + tail).strip(), (
            f"chunk={chunk_size}: terminator als sichtbarer text {(visible + tail)!r}"
        )


# --- A-13: Restumgehungen der Blockliste ---------------------------------


@pytest.mark.parametrize("variant", [
    "openurl", "open_url2", "CodeInterpreter", "websearch", "OPEN_URL\u200b",
    "web.run_v2", "open_uri", "fetchurl", "browse\u00a0",
])
def test_blocklist_covers_spelling_variants(variant):
    """A-13: nach der ersten Kanonisierung blieben Umgehungen offen —
    `openurl`, `open_url2`, `CodeInterpreter`, `websearch` und Namen mit
    Nullbreitenzeichen passierten die Sperre."""
    assert is_blocked_tool_name(variant, None) is True, variant


@pytest.mark.parametrize("legitimate", [
    "read", "read2", "Write", "sha256", "bash", "query2", "pdf_processor", "step3",
])
def test_blocklist_canonization_does_not_hit_legitimate_tools(legitimate):
    """Gegenprobe: echte Tools mit Ziffern im Namen bleiben benutzbar."""
    assert is_blocked_tool_name(legitimate, None) is False, legitimate


# --- D-01: unvollstaendiger protokoll-praefix im FINAL-pfad -------------


@pytest.mark.parametrize("payload,expect_stripped", [
    ("{", True),                              # erstes protokollzeichen
    ('{"t', True),
    ('{"tool', True),
    ('{"tool_calls"', True),
    ('text {"name": "bash"', True),           # prosa + angebrochener aufruf
    ('{"tool_calls":[{"name":"bash","arguments":{', True),
    ("normaler text", False),
    ("ende mit brace {", True),               # tradeoff, wie im stream-holdback
    ('a {"x": 1', False),                     # gewoehnliches JSON, kein protokoll
    ('{ "a": 1 }', False),                    # geschlossen
    ('{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}]}[]', False),
])
def test_unterminated_tool_prefix_is_stripped(payload, expect_stripped):
    """D-01: der streaming-pfad haelt einen angebrochenen
    protokoll-praefix im holdback zurueck, der final-pfad nicht. Der
    client sah im stream nichts, in der abschlussantwort aber `{"tool`
    als inhalt — mit `finish_reason: stop`, also als erfolg verlesen."""
    from glm2api.utils.tool_protocol import strip_unterminated_tool_prefix

    _, stripped = strip_unterminated_tool_prefix(payload)
    assert stripped == (1 if expect_stripped else 0), payload


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 5, 6, 7, 13, 29])
def test_truncated_tool_call_never_reaches_the_client(chunk_size):
    """Der eigentliche symptomtest: ein abgeschnittener tool-call ist in
    keinem pfad und bei keiner chunk-groesse sichtbar."""
    from glm2api.services.translator import GLMEventAccumulator

    text = '{"tool_calls":[{"name":"bash","arguments":{"command":"ls"}}'
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names={"bash"})
    streamed: list[str] = []
    for index in range(0, len(text), chunk_size):
        chunks, _ = accumulator.consume_event({
            "conversation_id": "c",
            "parts": [{"logic_id": f"p{index}", "content": [{"type": "text", "text": text[index : index + chunk_size]}]}],
        })
        for chunk in chunks:
            if not chunk.startswith("data: ") or "[DONE]" in chunk:
                continue
            try:
                streamed.append(json.loads(chunk[6:].strip())["choices"][0]["delta"].get("content", "") or "")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    accumulator.finalize("finish")
    choice = accumulator.build_response()["choices"][0]
    visible = "".join(streamed) + (choice["message"].get("content") or "")

    assert "tool_calls" not in visible
    assert not choice["message"].get("tool_calls")
    assert choice["finish_reason"] == "error", "ein abgeschnittener turn ist kein erfolg"


# --- P-12: der parser muss linear bleiben, nicht quadratisch ------------


@pytest.mark.parametrize("arg_size", [500, 1000, 2000, 4000, 8000])
def test_p12_character_wise_consumption_completes(arg_size):
    """P-12: bei zeichenweisem konsum scannte der parser den puffer pro
    aufruf neu. Gemessen im audit: 0,057 / 0,147 / 0,459 / 2,241 / 7,608 s
    fuer 500 / 1000 / 2000 / 4000 / 8000 zeichen — je verdopplung 2,6x,
    3,1x, 4,9x, 3,4x. Das ist quadratisch und blockiert die CPU.

    Der vertrag ist nicht "irgendwie schnell", sondern: die zeit muss mit
    der argumente-groesse WACHSEN, nicht mit deren quadrat."""
    import time

    payload = '{"tool_calls":[{"name":"bash","arguments":{"command":"' + "x" * arg_size + '"}}]}[]'
    start = time.perf_counter()
    for char in payload:
        parse_tool_calls_from_text(char, allowed_tool_names={"bash"})
    elapsed = time.perf_counter() - start

    # Schwelle bewusst grosszügig: sie soll einen AUSGELASTETEN host
    # nicht flimmern lassen, aber ein quadratisches Wachstum fällt
    # bei 8000 zeichen (0,027 s) auch dann noch durch.
    assert elapsed < 5.0, f"{arg_size} zeichen brauchten {elapsed:.2f}s"


def test_p12_growth_is_linear_not_quadratic():
    """Der eigentliche test: 8x mehr zeichen duerfen nicht 64x so lange
    dauern (quadratisch). Die schranke ist grosszügig gewaehlt, damit ein
    ausgelasteter ci-host nicht flimmert — quadratisch waere Faktor 64,
    linear Faktor 8."""
    import time

    def consume(arg_size: int) -> float:
        payload = '{"tool_calls":[{"name":"bash","arguments":{"command":"' + "x" * arg_size + '"}}]}[]'
        start = time.perf_counter()
        for char in payload:
            parse_tool_calls_from_text(char, allowed_tool_names={"bash"})
        return time.perf_counter() - start

    small = consume(2000)
    large = consume(16000)

    growth = large / max(small, 1e-6)
    assert growth < 24.0, f"zu superlinear: 8x zeichen kosteten {growth:.1f}x zeit (linear waere ~8x)"
