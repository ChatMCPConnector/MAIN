"""Breadth-Varianz-Studie: wie breit liest ein `opencode run`-Lauf wirklich?

Hintergrund: Ein einzelner Live-Lauf beweist nicht, dass eine Analyseaufgabe
zuverlässig das gesamte Repo inspiziert. GLM `glm-5.3` ist nicht
deterministisch, und `git ls-files`-Ausgaben lassen "Breite" größer aussehen,
als sie ist — sie zeigen nur, welche Dateien EXISTIEREN, nicht welche das
Modell GELESEN hat.

Dieses Harness trennt beides strikt:

  * ``inventory_bash``  — bash-Aufrufe ohne Lese-Verb (`git ls-files`, `find`,
                          `ls`, `du`, `wc -l`): reines Strukturwissen
  * ``content_files``   — DISTINKTE Dateien, deren Inhalt nachweislich gelesen
                          wurde: `read`-Ziel (existierende Datei) ODER Pfad in
                          einem bash-Kommando mit Lese-Verb
  * ``areas``           — Top-Level-Bereiche dieser ``content_files``
  * ``src_files``       — davon echte Quell-/Konfigdateien (.py/.go/.js/.sh/.ts)

Eingabe sind die ``--format json``-Ereignislogs von ``opencode run``
(gitignoriert unter ``.runtime/glm2api-*.jsonl``), daneben die ``.status``
Datei mit ``exit=``/``elapsed=``.

Aufruf::

    uv run python harness/breadth_variance.py ../../.runtime/glm2api-*.jsonl

Das Harness fasst nur zusammen; es bewertet keine Berichtsinhalte. Ein
niedriger ``src_files``-Wert bei hohem ``content_files`` heißt: viel Config
und Doku, wenig Quellcode — nicht zwingend ein Fehlschlag, aber auch keine
Quellcode-Abdeckung.
"""

from __future__ import annotations

import json
import os
import sys

# bash-Kommandos, die DateiINHALTE lesen (vs. reines Auflisten).
CONTENT_VERB = r"\b(cat|head|tail|less|more|sed|awk|grep|python3?|open\()"
# bash-Kommandos, die nur den Baum auflisten.
INVENTORY = r"\b(git ls-files|find |ls |du |wc -l|tree )"

FILE_EXT = r"(?:py|go|js|sh|ts|toml|json|md|yaml|yml|txt|rc|cfg|ini|example|dist|conf)"
PATH_RE = r"[\w./~-]+\.{ext}\b|(?<![\w./-])(?:Makefile|Dockerfile)\b".format(ext=FILE_EXT)
SRC_RE = r"[\w./-]+\.(?:py|go|js|sh|ts)\b"

# Zuordnung einer Datei zu einem Top-Level-Bereich des MAIN-Repos.
AREAS: list[tuple[str, str]] = [
    ("root", r"(?:^|[\s(])/?(?:Makefile|pyproject\.toml|AGENTS\.md|README\.md|"
             r"infrastructure\.md|PRIVACY\.md|\.env\.example)\b"),
    (".devcontainer", r"\.devcontainer/"),
    (".opencode", r"\.opencode/"),
    ("config", r"(?<![\w./])config/"),
    ("infra", r"(?<![\w./])infra/"),
    ("glm2api", r"llm-proxies/glm2api/"),
    ("zerokey", r"llm-proxies/zerokey/"),
    ("antigravity", r"llm-proxies/antigravity-proxy/"),
    ("llm-proxies-other", r"llm-proxies/(?!glm2api/|zerokey/|antigravity-proxy/)"),
]

ABORT = r"neue Nachricht|new message|neue Session|restart the session|schick(e)? (mir )?(einfach|bitte)"


def _compile():
    import re
    return {
        "content_verb": re.compile(CONTENT_VERB),
        "inventory": re.compile(INVENTORY),
        "path": re.compile(PATH_RE),
        "src": re.compile(SRC_RE),
        "abort": re.compile(ABORT, re.I),
        "areas": [(name, re.compile(rx)) for name, rx in AREAS],
    }


def _read_status(jsonl_path: str) -> tuple[str, str]:
    status = jsonl_path[:-len(".jsonl")] + ".status" if jsonl_path.endswith(".jsonl") else jsonl_path + ".status"
    code = elapsed = "?"
    if os.path.exists(status):
        with open(status, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("exit="):
                    code = line.strip().split("=", 1)[1]
                elif line.startswith("elapsed="):
                    elapsed = line.strip().split("=", 1)[1]
    return code, elapsed


def analyse(jsonl_path: str) -> dict:
    rx = _compile()
    counts = {"read": 0, "bash": 0, "todowrite": 0, "other": 0}
    inventory = 0
    content_files: set[str] = set()
    text_chars = 0
    texts: list[str] = []

    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "tool_use":
                part = ev.get("part", {}) or {}
                tool = part.get("tool")
                state = part.get("state", {}) or {}
                inp = state.get("input", {}) or {}
                if tool == "read":
                    counts["read"] += 1
                    fp = str(inp.get("filePath") or inp.get("path") or "")
                    # Nur echte Dateien zählen; ein Verzeichnis ist kein Inhalt.
                    if fp and not fp.endswith("/") and (os.path.isfile(fp) or "." in os.path.basename(fp)):
                        content_files.add(fp)
                elif tool == "bash":
                    counts["bash"] += 1
                    cmd = str(inp.get("command", ""))
                    if rx["inventory"].search(cmd) and not rx["content_verb"].search(cmd):
                        inventory += 1
                    content_files.update(rx["path"].findall(cmd))
                elif tool == "todowrite":
                    counts["todowrite"] += 1
                else:
                    counts["other"] += 1
            elif kind == "text":
                tx = (ev.get("part", {}) or {}).get("text", "")
                text_chars += len(tx)
                if tx.strip():
                    texts.append(tx)

    areas = sorted({
        name
        for f in content_files
        for name, area_rx in rx["areas"]
        if area_rx.search(f)
    })
    src_files = sorted({f for f in content_files if rx["src"].search(f)})
    code, elapsed = _read_status(jsonl_path)
    return {
        "exit": code,
        "elapsed": elapsed,
        **counts,
        "toolcalls": sum(counts.values()),
        "inventory_bash": inventory,
        "content_files": sorted(content_files),
        "n_content": len(content_files),
        "areas": areas,
        "src_files": src_files,
        "n_src": len(src_files),
        "report_chars": text_chars,
        "abort": bool(rx["abort"].search("\n".join(texts))),
    }


def selftest(tmpdir: str) -> int:
    """Positivkontrolle: reines Auflisten darf keine Inhalts-Breite vortäuschen.

    Genau dieser Fehler ist beim Bau des Harness aufgetreten: ein
    ``git ls-files``-Lauf meldete alle Bereiche als "inspiziert". Der Test
    hält die Trennung fest — Auflisten zählt als ``inventory``, nicht als
    ``content``.
    """
    listing = os.path.join(tmpdir, "selftest_listing.jsonl")
    reading = os.path.join(tmpdir, "selftest_reading.jsonl")
    with open(listing, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "tool_use", "part": {
            "tool": "bash", "state": {"input": {"command": "git ls-files"}}}}) + "\n")
    with open(reading, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "tool_use", "part": {
            "tool": "bash", "state": {"input": {"command": "cat Makefile"}}}}) + "\n")
    listed = analyse(listing)
    read = analyse(reading)
    ok = (
        listed["n_content"] == 0
        and listed["inventory_bash"] == 1
        and read["n_content"] == 1
        and read["n_src"] == 0
        and read["areas"] == ["root"]
    )
    print("selftest:", "OK" if ok else "FEHLGESCHLAGEN",
          f"(listing={listed['n_content']}/{listed['inventory_bash']} "
          f"reading={read['n_content']}/{read['areas']})")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            return selftest(tmp)
    if not argv:
        print(__doc__)
        return 2
    print(f"{'Lauf':<26} {'exit':>4} {'s':>5} {'tools':>5} {'read':>4} {'bash':>4} "
          f"{'inv':>3} {'content':>7} {'areas':>5} {'src':>3} {'chars':>6} abort")
    for path in argv:
        if not os.path.exists(path):
            print(f"{os.path.basename(path):<26} FEHLT")
            continue
        r = analyse(path)
        name = os.path.basename(path).replace(".jsonl", "")
        print(f"{name:<26} {r['exit']:>4} {r['elapsed']:>5} {r['toolcalls']:>5} "
              f"{r['read']:>4} {r['bash']:>4} {r['inventory_bash']:>3} {r['n_content']:>7} "
              f"{len(r['areas']):>5} {r['n_src']:>3} {r['report_chars']:>6} "
              f"{'JA' if r['abort'] else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
