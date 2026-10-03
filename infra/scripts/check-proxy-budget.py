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

# ZeroKey-Port -> providers/<name>. Gilt fuer ZeroKey-getriebene opencode-
# Provider; andere Ports (8001 glm2api, 9878 antigravity, 4096 Server) haben
# kein promptLimit und werden uebersprungen.
ZK_PORT_PROVIDER = {"7250": "chatgpt", "7300": "deepseek"}

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lade(root, cfg_p=None, zk_p=None):
    """Liest context/reserved aus opencode.json und promptLimit aus der
    ZeroKey-Config. Gibt (ctx, out, reserved, prompt_limit) oder None.

    Die Pfade sind Parameter statt sys.argv-Leser (2026-10-01, PLAN Stufe 3):
    dadurch ist die Funktion ohne Subprozess aufrufbar — der Test laedt sie
    direkt. Der CLI-Aufruf verhaelt sich unveraendert (main() reicht argv
    durch), die beiden Dateipfade sind optional.
    """
    cfg_p = cfg_p or os.path.join(root, ".opencode/opencode.json")
    zk_p = zk_p or os.path.join(root, "llm-proxies/zerokey/providers/chatgpt/config.js")
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


def pruefe(ctx, out, reserved, limit):
    """Die Kopplungslogik, ohne I/O und ohne Ausgabe — die eigentliche Regel.

    Gibt (fenster, schwelle, chars, fehler, hinweise) zurueck. Bewusst frei von
    `print`: das Skript liest sich sonst schlecht, und nur so ist die Logik
    direkt testbar (infra/tests/test_check_proxy_budget.py, PLAN Stufe 3).
    """
    fenster = ctx - reserved
    chars = fenster * CHARS_PER_TOKEN
    schwelle = ctx - out
    fehler = []
    hinweise = []

    # DER BUG VOM 2026-09-30: output > context macht die Schwelle negativ und die
    # Kompaktierung damit bedingungslos. Steht an erster Stelle, weil es die
    # einzige Regel ist, die den echten Fehler gefunden hat.
    if out >= ctx:
        fehler.append(
            f"output ({out}) >= context ({ctx}): die Kompaktierungsschwelle "
            f"context-output waere {schwelle} Tokens, also nicht positiv — opencode "
            "kompaktiert dann nach JEDER Runde. Das erzeugt den Resume-Loop."
        )
    elif schwelle * CHARS_PER_TOKEN <= limit:
        # Kompaktierung VOR der Kuerzung ist falsch: opencodes Summarizer
        # verbietet Tool-Calls, ZeroKeys instructions.md schreibt sie aber vor,
        # der Lauf bricht ab mit "Tool call not allowed while generating
        # summary". Nutzerentscheidung 2026-09-30: die Kompaktierung soll gar
        # nicht einsetzen. Also muss ZeroKeys eigene Middle-out-Kuerzung immer
        # zuerst greifen — die behaelt Kopf (Auftrag) und Tail (letzte
        # User-Nachricht, neueste Tool-Ergebnisse), der Absturz tut es nicht.
        fehler.append(
            f"Kompaktierung waere VOR der Kuerzung erreichbar: Schwelle {schwelle} "
            f"Tokens (~{schwelle * CHARS_PER_TOKEN} Zeichen) <= promptLimit {limit}. "
            f"output muss < {ctx - limit // CHARS_PER_TOKEN} sein."
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
        hinweise.append(
            f"Fenster ~{chars} Zeichen > promptLimit ({limit}) — middle-out-Kuerzung, "
            "nur der Mittelteil faellt weg. Kopfbereich und Tail bleiben erhalten."
        )
    elif chars < limit * 0.25:
        hinweise.append(f"Fenster nutzt nur {100 * chars // limit}% des Budgets — Limit koennte hoeher.")

    return fenster, schwelle, chars, fehler, hinweise


def paare(root):
    """Alle ZeroKey-getriebenen opencode-Provider finden und mit promptLimit paaren.

    MAIN (2026-10-03): `lade()` war auf das ChatGPT-Paar festverdrahtet
    (`provider.downloaddoctor` + `providers/chatgpt/config.js`). Deshalb blieb
    dieser Check gruen, als `deepseek-web` mit `limit.context: 1000000` drin
    stand — die Regel, die das gefangen haette, wurde nie auf dieses Paar
    angewandt. Ermittelt wird die Zuordnung jetzt aus der baseURL
    (`http://127.0.0.1:<port>/v1` -> `providers/<port-label>/config.js`), nicht
    aus einer Liste im Skript: eine Liste waere die zweite Wahrheit und genau
    die Art Kopplung, die dieser Check verhindern soll.

    Liefert (paare, reserved) mit paare = [(provider_id, model_id, ctx, out,
    prompt_limit, providers_verzeichnis)]. reserved ist opencodes globale
    `compaction.reserved` — dieselbe Zahl, die `lade()` fuer das ChatGPT-Paar
    liest, denn sie gilt pro Model, nicht pro Provider.
    """
    erg = []
    try:
        cfg = json.load(open(os.path.join(root, ".opencode/opencode.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return erg, 0
    zk_root = os.path.join(root, "llm-proxies/zerokey/providers")
    for pid, prov in (cfg.get("provider") or {}).items():
        base = str((prov.get("options") or {}).get("baseURL") or "")
        m = re.search(r"127\.0\.0\.1:(\d+)", base)
        if not m:
            continue
        name = ZK_PORT_PROVIDER.get(m.group(1))
        if not name:
            continue
        datei = os.path.join(zk_root, name, "config.js")
        if not os.path.exists(datei):
            continue
        treffer = re.search(r"const promptLimit = ([\d_]+)", open(datei, encoding="utf-8").read())
        if treffer is None:
            continue
        limit = int(treffer.group(1).replace("_", ""))
        for mid, mod in (prov.get("models") or {}).items():
            lim = (mod or {}).get("limit") or {}
            if "context" not in lim:
                continue
            erg.append((pid, mid, int(lim["context"]), int(lim.get("output") or 0), limit, name))
    return erg, int((cfg.get("compaction") or {}).get("reserved") or 0)


def main():
    root = DEFAULT_ROOT
    # CLI bleibt wie vorher: zwei optionale Positionsargumente.
    werte = lade(
        root,
        sys.argv[1] if len(sys.argv) > 1 else None,
        sys.argv[2] if len(sys.argv) > 2 else None,
    )
    if werte is None:
        return 2
    ctx, out, reserved, limit = werte

    fenster, schwelle, chars, fehler, hinweise = pruefe(ctx, out, reserved, limit)

    print(f"Client: context={ctx}, output={out} -> Kompaktierung ab {schwelle} Tokens")
    print(f"        reserved={reserved} -> Fenster {fenster} Tokens (~{chars} Zeichen)")
    print(f"Proxy:  promptLimit={limit} Zeichen")

    for h in hinweise:
        print(f"HINWEIS: {h}")
    for f in fehler:
        print(f"FEHLER: {f}")
    if fehler:
        return 1
    print(f"ok: Kopplung stimmt (Fenster {fenster} von {ctx} Tokens)")

    # MAIN (2026-10-03): zweite, paarweise Pruefung ueber ALLE ZeroKey-Provider
    print()
    gefaelle = []
    ps, reserved = paare(root)
    if not ps:
        print("kein ZeroKey-Provider in opencode.json gefunden — Paar-Pruefung entfaellt")
        return 0
    for pid, mid, pctx, pout, plimit, name in ps:
        f2, schw2, chars2, ef, hn = pruefe(pctx, pout, reserved, plimit)
        marke = "FEHLER" if ef else "ok    "
        print(
            f"{marke} {pid}/{mid} (zerokey/providers/{name}): context={pctx}, "
            f"output={pout}, promptLimit={plimit} Zeichen -> Kompaktierung ab "
            f"{schw2} Tokens, Fenster {f2} (~{chars2} Zeichen)"
        )
        for h in hn:
            print(f"         HINWEIS: {h}")
        gefaelle.extend(f"{pid}/{mid}: {x}" for x in ef)
    if gefaelle:
        print()
        for f in gefaelle:
            print(f"FEHLER: {f}")
        return 1
    print()
    print(f"ok: alle {len(ps)} ZeroKey-Paare geprueft")
    return 0


if __name__ == "__main__":
    sys.exit(main())
