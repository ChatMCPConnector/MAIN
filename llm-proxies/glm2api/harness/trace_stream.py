"""Delta-fuer-delta-trace fuer einen beliebigen text (text-part, dann
nativer aufruf). Aufruf:

    python3 trace_stream.py <preset> <chunk>
    presets: preamble | fence | s09 | s14 | eigen:<text>
"""

import sys

from common import GLM_SRC, content_of, native_event, text_event
from glm2api.services.translator import GLMEventAccumulator

PRESETS = {
    "preamble": "Ich lese die Datei jetzt.",
    "fence": "Vorher\n```\nalpha\nbeta\n```\nNachher",
    "s09": (
        "Der `open`-Tool-Aufruf funktioniert in dieser Umgebung nicht "
        "zuverlässig für lokale Pfade – ich nutze stattdessen `read`/`bash`:\n"
        "The `open` tool only works for web URLs — for local files I need to "
        "use `read`/`bash`:"
    ),
    "s14": "The `open` tool only works for web URLs — for local files I need to use `read`:`",
}
ALLOWED = {"read", "bash"}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "s09"
    chunk = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    if name.startswith("eigen:"):
        text = name[len("eigen:") :].replace("\\n", "\n")
    else:
        text = PRESETS[name]
    print(f"GLM_SRC = {GLM_SRC}")
    print(f"text    = {text!r}  chunk={chunk}")
    accumulator = GLMEventAccumulator(model="m", allowed_tool_names=ALLOWED)
    published: list[str] = []

    def state(tag):
        parser = accumulator.tool_parser
        print(
            f"  {tag:<7} carry={accumulator._narration_carry!r:<14}"
            f" deferred={accumulator._deferred_visible_text!r:<26}"
            f" parser={getattr(parser, 'pending_text', '?')!r:<20}"
            f" pre={accumulator._preamble_pending}"
        )

    for offset in range(0, len(text), chunk):
        piece = text[offset : offset + chunk]
        print(f"\ndelta {offset:>3} {piece!r}")
        state("vorher")
        chunks, _ = accumulator.consume_event(text_event(f"p{offset}", piece))
        out = content_of(chunks)
        published.append(out)
        print(f"  RAUS   {out!r}")
        state("nachher")
    chunks, _ = accumulator.consume_event(native_event("c1"))
    out = content_of(chunks)
    published.append(out)
    print(f"\ncall     RAUS {out!r}")
    state("nachher")
    final = content_of(accumulator.finalize("finish"))
    published.append(final)
    print(f"finalize RAUS {final!r}")
    print(f"\nGESAMT {''.join(published)!r}")


if __name__ == "__main__":
    main()
