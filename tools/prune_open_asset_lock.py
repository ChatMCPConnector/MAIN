#!/usr/bin/env python3
"""Remove downloaded material maps that the current Unity runtime does not consume."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "AssetSources" / "open-assets.lock.json"
USED_POLYHAVEN_SUFFIXES = ("_diff", "_normal", "_ao")


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    removed = 0
    for asset in lock.get("assets", []):
        if asset.get("provider") != "polyhaven" or asset.get("kind") != "material":
            continue

        files = asset.get("files") or []
        kept = [
            entry
            for entry in files
            if any(suffix in str(entry.get("path", "")).lower() for suffix in USED_POLYHAVEN_SUFFIXES)
        ]
        if not kept:
            raise SystemExit(f"No runtime-consumed maps remain for {asset.get('provider')}/{asset.get('id')}")
        removed += len(files) - len(kept)
        asset["files"] = kept

    LOCK_PATH.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pruned {removed} unused Poly Haven material map(s).")


if __name__ == "__main__":
    main()
