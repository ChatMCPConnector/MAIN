#!/usr/bin/env python3
"""port-drift-check.py — Ports gegen ihre einzige Quelle halten.

Warum überhaupt: die Ports 8001/9878/7250/4096 stehen in `ports.sh`, in
`.devcontainer/devcontainer.json`, in `infrastructure.md` und in den
Start-Skripten. Das ist keine Dokumentationsfrage, sondern ein Check-Problem
(PLAN §11) — Umschreiben der Doku hält nichts dauerhaft, ein Gate schon.

Was geprüft wird — genau drei Stellen, die Ports *aufzählen*, nicht die 40
Stellen, die sie nur *erwähnen* (Changelog, Fehlerberichte, Prose). Erwähnen
ist frei, Aufzählen muss stimmen:

  1. `ports.sh`            — die Labels. Fehlt ein Label, sieht `ports.sh`
                              „sonstiger Prozess" statt des Dienstnamens.
  2. `devcontainer.json`   — was GitHub weiterleitet. Ein Port hier ohne
                              Label ist sichtbar, aber unbeschriftet.
  3. Die Start-Skripten    — was wirklich gebunden wird. Ein gebundener Port
                              ohne Label ist der schlimmste Fall: er läuft
                              und niemand erkennt ihn.

Bewusst NICHT geprüft: Ports in Fließtext, Changelog-Einträgen, Fehlermeldungen.
Die zu verbiegen wäre die Umschreibung, die der Plan gerade vermeiden will.

Aufruf:
  port-drift-check.py            # Textbericht, Exit 1 bei Drift
  port-drift-check.py --quiet    # nur Exit-Code (fuer Hook/CI)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PORTS_SH = REPO / "infra" / "scripts" / "ports.sh"
DEVCONTAINER = REPO / ".devcontainer" / "devcontainer.json"

# Skripte, die Ports *deklarieren* (also eine Konstante setzen, nicht nur
# einen Port in einer Health-URL benutzen). Nicht "alle .sh im Repo": die
# Maintenance-Seiten (gdrive, quota) binden nichts, und ihre Ports sind
# Upstream-Dienste, keine Dienste dieses Codespaces.
#
# `verify-codespace.sh` und `proxy-watchdog.sh` fehlen absichtlich: sie
# *benutzen* Ports in curl-URLs, um sie zu prüfen. Würde man sie mitlesen,
# wäre das dieselbe Erkenntnis in zwei Dateien statt einer.
BINDING_SCRIPTS = [
    "infra/scripts/glm2api.sh",
    "infra/scripts/opencode-server.sh",
    "llm-proxies/scripts/start-glm2api.sh",
    "llm-proxies/scripts/start-zerokey.sh",
    "llm-proxies/antigravity-proxy/scripts/start.sh",
    "llm-proxies/zerokey/config/constants.js",
]

# Wo ein Port in einem Skript *deklariert* wird. Bewusst eng: ein Port, der in
# einem Kommentar oder in einer Health-URL auftaucht, ist kein gebundener Port.
#
# Die Anführungszeichen sind nicht optional — genau das war der Fehler in der
# ersten Fassung: `PORT="7250"` wurde nicht gematcht, also fiel der Negativtest
# (Label entfernen) nicht durch. `PORT=8001` und `PORT="7250"` kommen beide vor.
PORT_PATTERNS = [
    re.compile(r"""^\s*(?:export\s+)?PORT\s*=\s*["']?(\d{4,5})["']?\s*$"""),
    re.compile(r"--port[=\s]+(\d{4,5})\b"),
    re.compile(r"^\s*(?:export\s+)?(?:\w+_)?PORT\s*:\s*[^,]*?\b(\d{4,5})\b"),  # JS-Objekt
    re.compile(r"\bport\s*=\s*(\d{4,5})\b"),
]


def labelled_ports() -> dict[int, str]:
    """Lese die case-Arme aus ports.sh. Single Source of Truth."""
    text = PORTS_SH.read_text(encoding="utf-8")
    out: dict[int, str] = {}
    # 8001) echo "glm2api-Proxy";;
    for m in re.finditer(r"(\d{4,5})\)\s*echo\s+\"([^\"]+)\"", text):
        out[int(m.group(1))] = m.group(2)
    return out


def devcontainer_ports() -> set[int]:
    try:
        data = json.loads(DEVCONTAINER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    ports: set[int] = set()
    for entry in data.get("forwardPorts", []) or []:
        if isinstance(entry, int):
            ports.add(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("containerPort"), int):
            ports.add(entry["containerPort"])
    return ports


def bound_ports() -> dict[int, list[str]]:
    """Welche Ports werden von welchem Skript gebunden."""
    out: dict[int, list[str]] = {}
    for rel in BINDING_SCRIPTS:
        path = REPO / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            # Kommentarzeilen und Kommentarhälften auslassen.
            if stripped.startswith("#") or stripped.startswith("*") or stripped.startswith("//"):
                continue
            # Nur Deklarationszeilen: `echo "... Port ${PORT} ..."` zählt nicht.
            code = stripped.split("  #")[0].split(" #")[0]
            if not code or code.startswith(("echo", "printf", "print")):
                continue
            for pat in PORT_PATTERNS:
                for m in pat.finditer(code):
                    out.setdefault(int(m.group(1)), []).append(rel)
    return out


def main() -> int:
    quiet = "--quiet" in sys.argv
    labels = labelled_ports()
    if not labels:
        print("FEHLER: keine Port-Labels in ports.sh gefunden — Parser oder Datei kaputt.")
        return 2

    problems: list[str] = []

    # 1. Gebundene Ports ohne Label.
    bound = bound_ports()
    for port, where in sorted(bound.items()):
        if port not in labels:
            problems.append(
                f"Port {port} wird gebunden ({', '.join(sorted(set(where)))}) "
                f"hat aber kein Label in ports.sh"
            )

    # 2. Devcontainer-Ports ohne Label. Ausgenommen: die, die VS-Code selbst
    #    braucht (6082 noVNC, 5920 x11vnc — beide haben Labels, aber die
    #    Absicht ist: jedes weitergeleitete Port soll benennbar sein).
    for port in sorted(devcontainer_ports() - set(labels)):
        problems.append(f"Port {port} wird in devcontainer.json weitergeleitet, hat aber kein Label in ports.sh")

    if quiet:
        return 1 if problems else 0

    print(f"port-drift-check: {len(labels)} Labels in ports.sh")
    print(f"  gebunden:  {', '.join(str(p) for p in sorted(bound)) or '(keine)'}")
    print(f"  Devcontainer: {', '.join(str(p) for p in sorted(devcontainer_ports())) or '(keine)'}")
    if problems:
        print("")
        for p in problems:
            print(f"  FEHL  {p}")
        return 1
    print("  OK    jeder gebundene/weitergeleitete Port hat ein Label")
    return 0


if __name__ == "__main__":
    sys.exit(main())