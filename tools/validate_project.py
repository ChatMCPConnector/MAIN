from __future__ import annotations
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
required = [
    "project.godot", "game/main.tscn", "game/main.gd", "export_presets.cfg",
    "README.md", "LICENSE", "CONTROLS.md", "BUILDING.md", "TESTING.md",
    "SECURITY.md", "CHANGELOG.md", "ASSET_LICENSES.md",
]
errors: list[str] = []
for rel in required:
    if not (ROOT / rel).is_file():
        errors.append(f"Missing required file: {rel}")

text = (ROOT / "game/main.gd").read_text(encoding="utf-8")
for token, minimum in [("Kira Volt", 1), ("Brakk Forge", 1), ("Mira Bloom", 1), ("Nyx Shade", 1)]:
    if text.count(token) < minimum:
        errors.append(f"Missing character: {token}")
for mode in ["stage", "versus", "team", "training"]:
    if f'"{mode}"' not in text:
        errors.append(f"Missing mode: {mode}")
for enemy in ["brawler", "runner", "ranger", "elite", "boss"]:
    if f'"{enemy}"' not in text:
        errors.append(f"Missing enemy type: {enemy}")

for path in ROOT.rglob("*"):
    if path.is_file() and path.stat().st_size > 2_000_000:
        errors.append(f"Unexpected large source file: {path.relative_to(ROOT)}")
    if path.is_file() and path.suffix.lower() in {".exe", ".dll", ".msi", ".bat", ".ps1"}:
        errors.append(f"Binary or executable script committed unexpectedly: {path.relative_to(ROOT)}")

suspicious = [r"process[_ ]?inject", r"dll[_ ]?inject", r"reg add", r"schtasks", r"powershell.*-enc", r"miner"]
for pattern in suspicious:
    if re.search(pattern, text, re.IGNORECASE):
        errors.append(f"Suspicious source pattern: {pattern}")

if errors:
    print("Validation failed:")
    print("\n".join(f"- {e}" for e in errors))
    sys.exit(1)
print("Project validation passed.")
