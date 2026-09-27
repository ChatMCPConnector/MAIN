"""Gemeinsame Mess-Bausteine fuer die glm2api-Translator-Harnesses.

Wichtig (aus drei Harness-Bugs dieser Session): ein Harness-Bug sieht aus
wie ein Proxy-Bug. Deshalb gilt fuer jede Messung die POSITIVKONTROLLE:
dieselbe Messung muss gegen `GLM_SRC=<worktree>/.../src` mit einem
historischen Stand laufen und dort das erwartete (falsche) Ergebnis zeigen.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

DEFAULT_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "src"
)
GLM_SRC = os.environ.get("GLM_SRC", os.path.abspath(DEFAULT_SRC))
sys.path.insert(0, GLM_SRC)

from glm2api.services.translator import GLMEventAccumulator  # noqa: E402

# Live repro M (2026-09-26 19:29, 20 tool-calls im turn): ein text-part
# enthielt drei varianten desselben selbstgespraechs, aneinandergeklebt.
NARRATION = (
    "Der `open`-Tool-Aufruf funktioniert in dieser Umgebung nicht zuverlässig für "
    "lokale Pfade – ich nutze stattdessen `read`/`bash`:\n"
    "The `open` tool only works for web URLs — for local files I need to use "
    "`read`/`bash`:"
)

ALLOWED = {"read", "bash"}


def native_event(logic_id: str, name: str = "read", **arguments: Any) -> dict:
    args: dict[str, Any] = {"filePath": "/a.py", "command": "ls"}
    args.update(arguments)
    return {
        "conversation_id": "c",
        "parts": [
            {
                "logic_id": logic_id,
                "content": [
                    {
                        "type": "tool_calls",
                        "tool_calls": {
                            "id": f"{logic_id}-id",
                            "name": name,
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }
        ],
    }


def text_event(logic_id: str, text: str) -> dict:
    return {
        "conversation_id": "c",
        "parts": [{"logic_id": logic_id, "content": [{"type": "text", "text": text}]}],
    }


def content_of(chunks) -> str:
    out: list[str] = []
    for chunk in chunks or ():
        if not chunk.startswith("data: ") or "[DONE]" in chunk:
            continue
        try:
            delta = json.loads(chunk[6:].strip())["choices"][0]["delta"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            continue
        if delta.get("content"):
            out.append(delta["content"])
    return "".join(out)


def stream(parts, chunk_size: int = 4, allowed=ALLOWED):
    """Sichtbarer Stream inkl. finalize.

    `parts`: str -> in `chunk_size`-stuecke zerlegte text-deltas,
             dict -> natives call-event.

    Rueckgabe: (sichtbarer stream, body-content, accumulator)
    """
    accumulator = GLMEventAccumulator(
        model="m", allowed_tool_names=set(allowed or ALLOWED)
    )
    streamed: list[str] = []
    for index, part in enumerate(parts):
        if isinstance(part, dict):
            chunks, _ = accumulator.consume_event(part)
            streamed.append(content_of(chunks))
            continue
        for offset in range(0, len(part), chunk_size):
            chunks, _ = accumulator.consume_event(
                text_event(f"p{index}-{offset}", part[offset : offset + chunk_size])
            )
            streamed.append(content_of(chunks))
    streamed.append(content_of(accumulator.finalize("finish")))
    body = accumulator.build_response()["choices"][0]["message"].get("content") or ""
    return "".join(streamed), body, accumulator


def call_names(accumulator) -> list[str]:
    message = accumulator.build_response()["choices"][0]["message"]
    return [call["function"]["name"] for call in (message.get("tool_calls") or [])]
