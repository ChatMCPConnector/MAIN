"""S-14-Messung: was vom ersten Fragment einer zerschnittenen Narration
beim Client ankommt.

Szenario: ein Narration-Part (live repro M) + ein nativer Aufruf. Im
Aufruf-Turn darf die Narration den Client nicht erreichen — sie steht fuer
"ich tue X"-Gebraeuch, nicht fuer die Antwort.

Gemessen wird ueber ALLE chunk-groessen 1..len(narration) (nicht nur
stichproben), weil genau die fragmentgrenze den Fehler ausloest.

    python3 leak_probe.py            # protokoll
    python3 leak_probe.py --short    # nur zeilen mit leak
"""

from __future__ import annotations

import sys

from common import ALLOWED, NARRATION, native_event, stream

CONTROL_ANSWER = (
    "Die Datei hat 3 Zeilen. Nutze `read` mit dem Pfad, dann `bash` fuer "
    "den Rest.\n```bash\nls -la\n```\nFertig."
)


def probe_narration(chunk_size: int) -> tuple[str, str, list[str]]:
    visible, _body, acc = stream([NARRATION, native_event("c1")], chunk_size)
    return visible, "", [c["function"]["name"] for c in acc.build_response()["choices"][0]["message"].get("tool_calls") or []]


def probe_control(chunk_size: int) -> str:
    """Gegenprobe: echter Antworttext MIT werkzeug-nennung muss durch."""
    visible, _body, _acc = stream([CONTROL_ANSWER, native_event("c1")], chunk_size)
    return visible


def main() -> int:
    short = "--short" in sys.argv
    total = len(NARRATION)
    leaks = 0
    control_broken = 0
    calls_lost = 0
    print(f"narration = {total} zeichen, {len(NARRATION.splitlines())} zeilen")
    print(f"{'chunk':>5} | {'sichtbar':<52} | call")
    print("-" * 90)
    for chunk_size in range(1, total + 1):
        visible, _body, names = probe_narration(chunk_size)
        if not names:
            calls_lost += 1
        leak = visible.strip()
        if leak:
            leaks += 1
        if not short or leak or not names:
            print(f"{chunk_size:>5} | {leak[:52]!r:<52} | {','.join(names) or '—'}")
    print("-" * 90)
    print(f"LEAK: {leaks}/{total} chunk-groessen mit sichtbarem narration-rest")
    print(f"Aufruf verloren: {calls_lost}/{total}")

    print()
    print("Gegenprobe (echter antworttext mit `read`/`bash`/fence):")
    broken = 0
    for chunk_size in range(1, len(CONTROL_ANSWER) + 1):
        visible = probe_control(chunk_size)
        if visible.strip() != CONTROL_ANSWER.strip():
            broken += 1
            if not short or broken <= 5:
                print(f"  chunk={chunk_size:>3} -> {visible[:70]!r}")
    print(f"  veraendert: {broken}/{len(CONTROL_ANSWER)}")
    control_broken = broken
    return 1 if (leaks or control_broken or calls_lost) else 0


if __name__ == "__main__":
    raise SystemExit(main())
