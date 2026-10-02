#!/usr/bin/env python3
"""gate-claims-check.py — Falschaussagen ueber die Gate-Konfiguration finden.

Warum: der Coverage-Floor ist GLOBAL (`fail_under` auf TOTAL), aber die
Kommentare in `infra/coverage-floor.rc`, `pyproject.toml`, `Makefile` und
`.github/workflows/checks.yml` behaupteten das Gegenteil ("pro Datei"). Das fiel
erst auf, als ein neues Skript mit 0 % die Summe von 95 % auf 77 % zog. Ein
Kommentar, der die Konfiguration falsch beschreibt, ist schlimmer als kein
Kommentar — er verhindert, dass man den Fehler ueberhaupt sucht.

Der Check haelt die WIRKLICHE Scope aus `infra/coverage-floor.rc` (wo steht
`fail_under`?) gegen die Behauptungen in den Gate-Dateien. Er ist bewusst
schmal: geprueft werden nur Zeilen mit Coverage-Kontext, und nur Aussagen, die
sich aus der Config ableiten lassen. Kein NLP-Pruefer.

Aufruf:
  gate-claims-check.py           # Bericht, Exit 1 bei Drift
  gate-claims-check.py --quiet   # nur Exit-Code
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

FLOOR_CONFIG = "infra/coverage-floor.rc"
# Gate-Dateien, die ueber den Floor reden. Bewusst eine feste Liste: eine
# Volltextsuche im ganzen Repo wuerde Fliesstext/Changelog mitpruefen.
GUARD_FILES = [
    FLOOR_CONFIG,
    "pyproject.toml",
    "Makefile",
    ".github/workflows/checks.yml",
]

# "pro Datei"/"je Datei"/"per-file" — nur wenn NICHT "nicht"/"kein" davor steht,
# sonst schluege die korrekte Formulierung ("nicht pro Datei") selbst an.
PER_FILE_RE = re.compile(r"(?<!nicht )(?<!kein )(?:pro|je|per)[ -]?(?:Datei|file)", re.I)
# "Floor gilt fuer <datei>.py" — eine Einzeldatei-Behauptung.
ONE_FILE_RE = re.compile(r"floor[^\n]*\b(?:fuer|für)\b[^\n]*\.py", re.I)
# Eine Global-Behauptung. Bewusst an `fail_under`/`TOTAL` gebunden, nicht an das
# Wort "global" allein (das kommt auch in anderen Kontexten vor).
GLOBAL_CLAIM_RE = re.compile(r"global[^\n]*\bTOTAL\b|\bfail_under\b[^\n]*\bTOTAL\b", re.I)
CONTEXT_RE = re.compile(r"floor|coverage|fail_under|\bcov\b", re.I)


def floor_scope(config_text: str) -> str:
    """'global', wenn `fail_under` in `[report]` steht, sonst 'per-file'.

    coverage.py kennt pro-Datei-Grenzen ueber eigene Report-Sektionen; die
    Scope ergibt sich daraus, in welcher Sektion `fail_under` steht.
    """
    section = ""
    scope = "global"
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].lower()
            continue
        if re.match(r"^fail_under\s*=", line):
            scope = "per-file" if ":" in section else "global"
    return scope


def line_problem(scope: str, line: str) -> str | None:
    """Gibt den Grund zurueck, wenn die Zeile der echten Scope widerspricht."""
    if not CONTEXT_RE.search(line):
        return None
    if scope == "per-file":
        if GLOBAL_CLAIM_RE.search(line) and not PER_FILE_RE.search(line):
            return "behauptet global, der Floor ist aber pro Datei"
        return None
    # scope == "global"
    if PER_FILE_RE.search(line):
        return "behauptet pro-Datei, der Floor ist aber global (fail_under auf TOTAL)"
    if ONE_FILE_RE.search(line):
        return "nennt eine Einzeldatei fuer den Floor, der Floor ist aber global"
    return None


def check(root: Path | None = None) -> list[str]:
    root = root or REPO
    config = root / FLOOR_CONFIG
    if not config.is_file():
        return [f"{FLOOR_CONFIG}: fehlt — Scope nicht bestimmbar"]
    scope = floor_scope(config.read_text(encoding="utf-8"))
    problems: list[str] = []
    for rel in GUARD_FILES:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: fehlt (Gate-Datei)")
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            why = line_problem(scope, line)
            if why:
                problems.append(f"{rel}:{number}: {why}\n    {line.strip()}")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    quiet = "--quiet" in argv
    problems = check()
    if problems:
        if not quiet:
            print("gate-claims-check: Widerspruch zwischen Kommentar und Config:")
            for problem in problems:
                print(f"  {problem}")
            print("")
            print("Entweder den Kommentar korrigieren oder die Config aendern —")
            print("beides muss dieselbe Aussage treffen.")
        return 1
    if not quiet:
        scope = floor_scope((REPO / FLOOR_CONFIG).read_text(encoding="utf-8"))
        print(f"gate-claims-check: Gate-Kommentare stimmen mit der Config ueberein (Floor-Scope: {scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
