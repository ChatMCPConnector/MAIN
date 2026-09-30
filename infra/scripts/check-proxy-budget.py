#!/usr/bin/env python3
"""Prueft die Kopplung zwischen opencodes Kontextbudget und ZeroKeys PromptLimit.

Vier Zahlen MUESSEN zusammenpassen, werden aber an zwei verschiedenen Stellen
von Hand gepflegt: `limit.context`, `limit.output` und `compaction.reserved`
in `.opencode/opencode.json` (alle Tokens), `promptLimit` in
`llm-proxies/zerokey/providers/chatgpt/config.js` (Zeichen).

DER ECHTE BUG war `output > context`. Am 2026-09-30 stand output=16384 neben
context=16000. opencode rechnet die Schwelle fuer die Kompaktierung als
`context - output`, das Ergebnis ist negativ — die Kompaktierung lief also
**bedingungslos**, nach jedem Turn, unabhaengig vom Fuellstand. Das Modell las
opencodes synthetischen Satz "Continue if you have next steps" als
Resume-Marker und schrieb statt zu arbeiten einen Task-Uebergabebericht
("## Objective / ## Work State"), 1712 -> 2533 -> 3635 Zeichen. Eine
Live-Session verbrannte 20 Requests damit und lief danach in
"Tool call not allowed while generating summary": opencode verbietet Tool-Calls
waehrend der Summary, und ZeroKeys instructions.md schreibt sie dem Modell
ausdruecklich vor.

Isoliert belegt am 2026-09-30, eine Variable zur Zeit:

    context=16000 output=4000  reserved=2000  -> agent=build, KEINE Kompaktierung
    context=16000 output=16384 reserved=2000  -> agent=compaction nach step 1
    context=16000 output=16384 reserved=15000 -> Kompaktierung nach jedem Turn

Die erste Fassion dieses Checks hatte `compaction.reserved` im Verdacht und
lag falsch; sie pruefte nur reserved gegen context und verfehlte output
voellig.

Die uebrigen Regeln:

  reserved >= context
      Kompaktierung nach jedem Turn, derselbe Effekt.

  Arbeitsfenster < 50 % des Kontexts
      reserved=15000 bei context=1600 liess 1000 Token. Die Menge lag UNTER dem
      Proxy-Budget, die Zeichen-Pruefung greift also nicht — gebrochen war,
      dass die Kompaktierung bei 6 % Fuellstand ausloeste.

  Arbeitsfenster > doppeltes Proxy-Budget
      mehr als die Haelfte des Gespraechs waere abgeschnitten. Ein leichtes
      Ueberschreiten ist beabsichtigt: limitPrompt schneidet dann middle-out und
      rettet dabei Kopf (Auftrag) und Tail (letzte User-Nachricht, neueste
      Tool-Ergebnisse).

Aufruf: check-proxy-budget.py [opencode.json] [chatgpt/config.js]
Exit 0 = Kopplung stimmt, 1 = Fehler, 2 = Datei nicht lesbar.
"""

import json
import os
import re
import sys

# Zeichen pro Token. 4 ist die uebliche Naeherung fuer Fliesstext; Code und
# JSON sind dichter (~3). Es geht hier um Groessenordnungen, nicht um Genauigkeit.
CHARS_PER_TOKEN = 4

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lade(root):
    """Liest context/reserved aus opencode.json und promptLimit aus der
    ZeroKey-Config. Gibt (ctx, reserved, prompt_limit) oder None bei Fehlern."""
    cfg_p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, ".opencode/opencode.json")
    zk_p = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(root, "llm-proxies/zerokey/providers/chatgpt/config.js")
    )
    try:
        cfg = json.load(open(cfg_p, encoding="utf-8"))
        treffer = re.search(r"const promptLimit = ([\d_]+)", open(zk_p, encoding="utf-8").read())
        if treffer is None:
            raise ValueError(f"kein promptLimit in {zk_p}")
        prompt_limit = int(treffer.group(1).replace("_", ""))
        lim = cfg["provider"]["downloaddoctor"]["models"]["zerokey"]["limit"]
        ctx = int(lim["context"])
        out = int(lim["output"])
        reserved = int(cfg["compaction"]["reserved"])
    except (OSError, ValueError, KeyError, TypeError) as err:
        print(f"FEHLER: Dateien nicht lesbar ({err})")
        return None
    return ctx, out, reserved, prompt_limit


def main():
    root = DEFAULT_ROOT
    werte = lade(root)
    if werte is None:
        return 2
    ctx, out, reserved, limit = werte

    fenster = ctx - reserved
    chars = fenster * CHARS_PER_TOKEN
    schwelle = ctx - out
    fehler = []

    print(f"Client: context={ctx}, output={out} -> Kompaktierung ab {schwelle} Tokens")
    print(f"        reserved={reserved} -> Fenster {fenster} Tokens (~{chars} Zeichen)")
    print(f"Proxy:  promptLimit={limit} Zeichen")

    # DER BUG VOM 2026-09-30: output > context macht die Schwelle negativ und die
    # Kompaktierung damit bedingungslos. Steht an erster Stelle, weil es die
    # einzige Regel ist, die den echten Fehler gefunden hat.
    if out >= ctx:
        fehler.append(
            f"output ({out}) >= context ({ctx}): die Kompaktierungsschwelle "
            f"context-output waere {schwelle} Tokens, also nicht positiv — opencode "
            "kompaktiert dann nach JEDER Runde. Das erzeugt den Resume-Loop."
        )

    if reserved >= ctx:
        fehler.append(
            f"reserved ({reserved}) >= context ({ctx}): opencode kompactiert nach JEDER Runde "
            "und haengt Continue-if-you-have-next-steps an — der Resume-Loop."
        )
    elif fenster * 2 < ctx:
        fehler.append(
            f"Arbeitsfenster nur {fenster} von {ctx} Tokens ({100 * fenster // ctx}%): "
            f"reserved belegt {100 * reserved // ctx}% des Kontexts fuer die Compaction. "
            "Laeuft die Kompaktierung ständig, ist der Loop wieder da."
        )

    if chars > limit * 2:
        fehler.append(
            f"Arbeitsfenster ~{chars} Zeichen > 2x promptLimit ({limit * 2}): "
            "mehr als die Haelfte des Gespraechs waere abgeschnitten."
        )
    elif chars > limit:
        print(f"HINWEIS: Fenster ~{chars} Zeichen > promptLimit ({limit}) — middle-out-Kuerzung,")
        print("         nur der Mittelteil faellt weg. Kopfbereich und Tail bleiben erhalten.")
    elif chars < limit * 0.25:
        print(f"HINWEIS: Fenster nutzt nur {100 * chars // limit}% des Budgets — Limit koennte hoeher.")

    for f in fehler:
        print(f"FEHLER: {f}")
    if fehler:
        return 1
    print(f"ok: Kopplung stimmt (Fenster {fenster} von {ctx} Tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
