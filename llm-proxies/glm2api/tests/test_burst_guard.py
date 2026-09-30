"""B-01: BURST-GUARD — blindes Feuern im selben Turn wird gekappt.

Live-Befund 2026-10-01 00:11 (`glm2api.log`, ein Audit-Langlauf): das Modell
feuerte **29 identische `bash`-Calls in einer Sekunde**:

    思考结束
    {"tool_calls":[{"name":"bash","arguments":{"command":"du -sh …"}}]}[]
    思考结束
    {identisch}[]
    … ~29x

Der Denkblock war jedesmal LEER (`思考结束` = "denken beendet" ohne Text). Es
war also kein "erst lange denken, dann explodieren", sondern null Denken →
Call → null Denken → derselbe Call. Ohne Ergebnis dazwischen, also ohne
Möglichkeit zu lernen.

Der Loop-Guard (`_MAX_IDENTICAL_NATIVE_CALLS = 2`) hat alle Kopien still
verworfen, aber zwei davon gingen an den Client und liefen doppelt. Und das
Modell sah nie eine Rückmeldung, weil es nie ein Ergebnis bekam — es feuerte
weiter.

Diese Tests halten fest:
  - ein Burst wird auf GENAU EINE Client-Ausführung reduziert,
  - das Modell bekommt eine Notice mit der Burst-Zahl und der Anweisung zu
    warten (T-30-Kanal),
  - zwei bis vier gleiche Calls bleiben unangetastet (kein Fehlalarm — der
    Guard soll nicht das legitime parallele Prüfen zerstören),
  - verschiedene Calls werden nie kollabiert.
"""

import json
import logging

from glm2api.services.glm_client import _turn_notice_texts
from glm2api.services.translator import GLMEventAccumulator, _canonical_signature

TARGET = "/workspaces/MAIN/README.md"
COMMAND = "du -sh /workspaces/MAIN/.runtime/* | sort -rh | head -15"


def _acc():
    return GLMEventAccumulator(model="glm-5.3", allowed_tool_names={"bash", "read", "webfetch"})


def _bash_event(call_id: str, command: str = COMMAND):
    """Ein nativer Bash-Call in der Listenform, wie chatglm.cn ihn sendet."""
    return {
        "status": "finish",
        "parts": [
            {
                "id": f"p{call_id}",
                "logic_id": f"l{call_id}",
                "role": "assistant",
                "status": "finish",
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "name": "bash",
                                "arguments": {"command": command},
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _feed_burst(acc, count: int, command: str = COMMAND):
    for index in range(count):
        acc.consume_event(_bash_event(f"burst_{index}", command))


def _client_calls(acc):
    acc.finalize("finish")
    return acc.build_response()["choices"][0]["message"].get("tool_calls") or []


# --- Der Burst selbst -----------------------------------------------------


def test_burst_von_29_identischen_calls_wird_auf_einen_call_kollabiert():
    """Der Live-Fall: 29x derselbe Call, zwei gingen doppelt an den Client."""
    acc = _acc()
    _feed_burst(acc, 29)

    calls = _client_calls(acc)

    assert len(calls) == 1, (
        f"ein burst darf nur einmal ausgefuehrt werden, nicht {len(calls)}-mal"
    )
    assert acc.burst_guard_tripped is True


def test_burst_notice_nennt_anzahl_und_wartungsanweisung():
    acc = _acc()
    _feed_burst(acc, 29)
    _client_calls(acc)

    notices = _turn_notice_texts(acc, [])

    assert notices, "das modell muss eine burst-rueckmeldung bekommen"
    burst_text = " ".join(notices)
    assert "[burst_guard_notice]" in burst_text
    assert "bash" in burst_text, "die notice nennt den werkzeugnamen"
    # 29 gesendet, 27 davon vom loop-guard verworfen — die notice nennt die
    # WIEDERHOLUNGEN (27), nicht die Gesamtzahl. Sonst waere die Zahl falsch.
    assert "27 times" in burst_text, f"die notice nennt die anzahl, nicht '{burst_text}'"
    assert "repeated" in burst_text
    assert "wait" in burst_text.lower()


def test_burst_notice_erscheint_vor_der_loop_guard_meldung():
    """Die Burst-Meldung ist die Eskalation — sie muss zuerst kommen."""
    acc = _acc()
    _feed_burst(acc, 29)
    _client_calls(acc)

    notices = _turn_notice_texts(acc, ["open"])

    burst_index = next(
        index for index, text in enumerate(notices) if "[burst_guard_notice]" in text
    )
    loop_index = next(
        (
            index
            for index, text in enumerate(notices)
            if "[loop_guard_notice]" in text
        ),
        len(notices),
    )
    assert burst_index < loop_index


def test_burst_wird_im_proxy_log_als_eigener_zustand_gefuehrt():
    acc = _acc()
    acc.logger = logging.getLogger("glm2api.test.burst")
    _feed_burst(acc, 12)
    _client_calls(acc)

    assert acc.burst_guard_tripped is True
    assert acc.burst_notices, "die notice liegt als eigener zustand vor"


# --- Schwellwert-Grenzen (kein Fehlalarm) --------------------------------


def test_zwei_identische_calls_sind_kein_burst():
    """Legitimes doppeltes Pruefen bleibt erlaubt."""
    acc = _acc()
    _feed_burst(acc, 2)

    calls = _client_calls(acc)

    assert len(calls) == 2
    assert acc.burst_guard_tripped is False
    assert acc.burst_notices == []


def test_vier_identische_calls_sind_kein_burst():
    """Unterhalb der Schwelle (5 Drops) fasst der Guard nicht ein."""
    acc = _acc()
    _feed_burst(acc, 4)

    calls = _client_calls(acc)

    assert len(calls) == 2, "der loop-guard laesst zwei, der burst-guard fasst nicht an"
    assert acc.burst_guard_tripped is False


def test_fuenf_identische_calls_sind_der_schwellwert():
    """5 Calls = 3 Drops … und damit noch kein Burst (Schwelle ist 5 DROPS)."""
    acc = _acc()
    _feed_burst(acc, 5)

    assert acc.burst_guard_tripped is False


def test_sechs_identische_calls_ueberschreiten_die_schwelle():
    """6 Calls = 4 Drops; der 5. Drop fehlt noch. Ab 7 Calls greift er."""
    acc = _acc()
    _feed_burst(acc, 6)

    assert acc.burst_guard_tripped is False


def test_acht_identische_calls_ueberschreiten_die_schwelle():
    acc = _acc()
    _feed_burst(acc, 8)

    calls = _client_calls(acc)

    assert acc.burst_guard_tripped is True
    assert len(calls) == 1


# --- Verschiedene Calls bleiben unangetastet ------------------------------


def test_verschiedene_calls_werden_nie_kollabiert():
    acc = _acc()
    for index in range(8):
        acc.consume_event(_bash_event(f"diff_{index}", command=f"ls -la /tmp/{index}"))

    calls = _client_calls(acc)

    assert len(calls) == 8, "acht verschiedene calls sind kein burst"
    assert acc.burst_guard_tripped is False


def test_gemischte_calls_nur_die_burst_signatur_wird_kollabiert():
    acc = _acc()
    for index in range(7):
        acc.consume_event(_bash_event(f"dup_{index}"))
    for index in range(3):
        acc.consume_event(_bash_event(f"uniq_{index}", command=f"wc -l /workspaces/MAIN/f{index}"))

    calls = _client_calls(acc)
    commands = [
        call.get("function", {}).get("arguments", "") for call in calls
    ]

    assert acc.burst_guard_tripped is True
    assert sum(1 for arg in commands if COMMAND in str(arg)) == 1
    assert sum(1 for arg in commands if "wc -l" in str(arg)) == 3


# --- Signatur-Kanonisierung (B-01-Fallstrick) ----------------------------


def test_signaturen_sind_unabhaengig_von_der_schluesselreihenfolge():
    """Der native Pfad normalisiert mit `sort_keys`, `_tool_call_signature`
    ohne — ohne Kanonisierung findet der Burst-Guard seinen Call nicht."""
    forward = _canonical_signature('bash:{"command":"ls","workdir":"/tmp"}')
    backward = _canonical_signature('bash:{"workdir":"/tmp","command":"ls"}')

    assert forward == backward


def test_canonical_signature_laesst_nicht_json_zugriffen():
    assert _canonical_signature("bash:{kaputt") == "bash:{kaputt"
    assert _canonical_signature("ohne-doppelpunkt") == "ohne-doppelpunkt"


def test_canonical_signature_behaelt_doppelte_signaturen_unverwandelt():
    """Ein Argument, das selbst ein String ist, wird nicht umgepackt."""
    raw = json.dumps({"command": "ls"}, separators=(",", ":"))
    assert _canonical_signature(f"bash:{raw}") == f"bash:{raw}"