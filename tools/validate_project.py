#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def read(path: str) -> str:
    target = ROOT / path
    require(target.is_file(), f"Missing required file: {path}")
    return target.read_text(encoding="utf-8") if target.is_file() else ""


project_version = read("ProjectSettings/ProjectVersion.txt")
require("6000.3.17f1" in project_version, "Unity editor must be pinned to 6000.3.17f1")

manifest_text = read("Packages/manifest.json")
try:
    manifest = json.loads(manifest_text)
except json.JSONDecodeError as exc:
    ERRORS.append(f"Packages/manifest.json is invalid JSON: {exc}")
    manifest = {"dependencies": {}}

dependencies = manifest.get("dependencies", {})
required_packages = {
    "com.unity.inputsystem": "1.17.0",
    "com.unity.render-pipelines.universal": "17.3.0",
    "com.unity.test-framework": "1.6.0",
    "com.unity.ugui": "2.0.0",
}
for package, version in required_packages.items():
    require(dependencies.get(package) == version, f"Package {package} must be pinned to {version}")

gltfast = dependencies.get("com.atteneder.gltfast", "")
require("66aa58252bafe6f7f48031f4906f807f95a3f396" in gltfast, "glTFast must use the audited release commit")

required_files = [
    "Assets/NeonRift/Foundation/GameTypes.cs",
    "Assets/NeonRift/Scripts/Core/NeonRiftBootstrap.cs",
    "Assets/NeonRift/Scripts/Core/NeonRiftGame.cs",
    "Assets/NeonRift/Scripts/Gameplay/FighterController.cs",
    "Assets/NeonRift/Scripts/Gameplay/EnergyProjectile.cs",
    "Assets/NeonRift/Scripts/Rendering/ArenaVisualFactory.cs",
    "Assets/NeonRift/Scripts/Rendering/ArenaCameraRig.cs",
    "Assets/NeonRift/Scripts/Rendering/CommunityModel.cs",
    "Assets/NeonRift/Scripts/Rendering/CombatEffects.cs",
    "Assets/NeonRift/Editor/CommunityAssetInstaller.cs",
    "Assets/NeonRift/Editor/ProjectSetup.cs",
    "Assets/NeonRift/Editor/BuildAutomation.cs",
    "Assets/Tests/EditMode/NeonRiftCoreTests.cs",
    ".github/workflows/unity-windows.yml",
    "README.md",
    "ASSET_SOURCES.md",
    "CONTROLS.md",
    "BUILDING.md",
    "TESTING.md",
    "SECURITY.md",
    "LICENSE",
]
for path in required_files:
    require((ROOT / path).is_file(), f"Missing required file: {path}")

installer = read("Assets/NeonRift/Editor/CommunityAssetInstaller.cs")
for pin in [
    "672074b73ba276876a19e8816ecdc5241817ab47",
    "15b62b9bad122f72926c10fb14d622c73819fa54",
    "88f977a0cb-1709220730",
    "5fcb837741-1750838303",
]:
    require(pin in installer, f"Community source pin is missing: {pin}")

for model in [
    "Knight.glb",
    "Barbarian.glb",
    "Mage.glb",
    "Rogue.glb",
    "Skeleton_Warrior.glb",
    "Skeleton_Rogue.glb",
    "Skeleton_Mage.glb",
    "Skeleton_Minion.glb",
]:
    require(model in installer, f"Selected CC0 character file is not installed: {model}")

runtime_source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "Assets/NeonRift").rglob("*.cs"))
for symbol in [
    "class NeonRiftGame",
    "class FighterController",
    "class ArenaVisualFactory",
    "class CommunityModel",
    "class CombatEffects",
    "class EnergyProjectile",
    "GameMode.StageRun",
    "GameMode.LocalVersus",
    "GameMode.TeamBattle",
    "GameMode.Training",
    "GameMode.Survival",
    "UniversalRenderPipelineAsset",
    "Resources.Load<GameObject>",
    "Gamepad.all",
    "--smoke-test",
]:
    require(symbol in runtime_source, f"Required Unity implementation symbol is missing: {symbol}")

# Lightweight delimiter check after stripping comments and quoted strings.
def strip_csharp(text: str) -> str:
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r'@?"(?:""|\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])'", "''", text)
    return text

for source_path in (ROOT / "Assets").rglob("*.cs"):
    clean = strip_csharp(source_path.read_text(encoding="utf-8"))
    require(clean.count("{") == clean.count("}"), f"Unbalanced braces: {source_path.relative_to(ROOT)}")
    require(clean.count("(") == clean.count(")"), f"Unbalanced parentheses: {source_path.relative_to(ROOT)}")

for forbidden in ["project.godot", "export_presets.cfg", "default_bus_layout.tres"]:
    require(not (ROOT / forbidden).exists(), f"Former Godot file must be removed: {forbidden}")
require(not any(ROOT.rglob("*.gd")), "Former GDScript files must be removed")
require(not any(ROOT.rglob("*.tscn")), "Former Godot scene files must be removed")

asset_sources = read("ASSET_SOURCES.md")
for license_name in ["CC0 1.0 Universal", "Apache-2.0", "Unity Package Manager"]:
    require(license_name in asset_sources, f"Asset documentation is missing license/source detail: {license_name}")

workflow = read(".github/workflows/unity-windows.yml")
for token in [
    "6000.3.17f1",
    "game-ci/unity-test-runner@v4",
    "game-ci/unity-builder@v5",
    "NeonRift.Editor.BuildAutomation.BuildWindows",
    "UNITY_LICENSE",
    "StandaloneWindows64",
    "smoke-test.log",
    "SHA256SUMS.txt",
]:
    require(token in workflow, f"Unity workflow is missing: {token}")

if ERRORS:
    print("Unity project validation FAILED:")
    for error in ERRORS:
        print(f" - {error}")
    sys.exit(1)

cs_count = len(list((ROOT / "Assets").rglob("*.cs")))
print("Unity project validation PASSED")
print(f"C# files: {cs_count}")
print(f"Unity version: {project_version.split(':', 1)[-1].strip()}")
print("Modes: 5 | Fighters: 4 | Arenas: 3 | CC0 character models: 8")
