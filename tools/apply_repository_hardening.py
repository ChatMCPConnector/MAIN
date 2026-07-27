#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text and old not in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one occurrence in {relative}, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_game_navigation_and_lifecycle() -> None:
    path = "Assets/NeonRift/Scripts/Core/NeonRiftGame.cs"
    replace_once(
        path,
        """            int optionCount = OptionCountForCurrentScreen();
            if (keyboard.upArrowKey.wasPressedThisFrame) _menuIndex = Wrap(_menuIndex - 1, optionCount);
            if (keyboard.downArrowKey.wasPressedThisFrame) _menuIndex = Wrap(_menuIndex + 1, optionCount);
            if (keyboard.leftArrowKey.wasPressedThisFrame) MoveHorizontal(-1);
            if (keyboard.rightArrowKey.wasPressedThisFrame) MoveHorizontal(1);
""",
        """            if (keyboard.upArrowKey.wasPressedThisFrame) MoveVertical(-1);
            if (keyboard.downArrowKey.wasPressedThisFrame) MoveVertical(1);
            if (keyboard.leftArrowKey.wasPressedThisFrame) MoveHorizontal(-1);
            if (keyboard.rightArrowKey.wasPressedThisFrame) MoveHorizontal(1);
""",
    )
    replace_once(
        path,
        """        private void MoveHorizontal(int direction)
        {
            if (Screen == GameScreen.CharacterSelect)
            {
                _selectedCharacter = Wrap(_selectedCharacter + direction, NeonRiftCatalog.Fighters.Count);
                _menuIndex = _selectedCharacter;
            }
            else if (Screen == GameScreen.ArenaSelect)
            {
                _selectedArena = Wrap(_selectedArena + direction, NeonRiftCatalog.Arenas.Count);
                _menuIndex = _selectedArena;
                _arenaFactory.Build(NeonRiftCatalog.Arenas[_selectedArena], _selectedArena);
                CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();
            }
            else if (Screen == GameScreen.ModeSelect)
            {
                _menuIndex = Wrap(_menuIndex + direction, NeonRiftCatalog.Modes.Count);
            }
        }
""",
        """        private void MoveVertical(int direction)
        {
            _menuIndex = Wrap(_menuIndex + direction, OptionCountForCurrentScreen());
            SynchronizeSelectionPreview();
        }

        private void MoveHorizontal(int direction)
        {
            if (Screen != GameScreen.CharacterSelect &&
                Screen != GameScreen.ArenaSelect &&
                Screen != GameScreen.ModeSelect)
            {
                return;
            }

            _menuIndex = Wrap(_menuIndex + direction, OptionCountForCurrentScreen());
            SynchronizeSelectionPreview();
        }

        private void SynchronizeSelectionPreview()
        {
            if (Screen == GameScreen.CharacterSelect)
            {
                _selectedCharacter = _menuIndex;
            }
            else if (Screen == GameScreen.ArenaSelect)
            {
                _selectedArena = _menuIndex;
                RebuildArenaPreview();
            }
        }

        private void RebuildArenaPreview()
        {
            _arenaFactory.Build(NeonRiftCatalog.Arenas[_selectedArena], _selectedArena);
            CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();
        }
""",
    )
    replace_once(
        path,
        """                    Screen = GameScreen.ArenaSelect;
                    _menuIndex = _selectedArena;
                    break;
""",
        """                    Screen = GameScreen.ArenaSelect;
                    _menuIndex = _selectedArena;
                    RebuildArenaPreview();
                    break;
""",
    )
    replace_once(
        path,
        """        private void FinishMatch(string message)
        {
            _resultText = message;
            _resultTimer = 0f;
            Screen = GameScreen.Result;
        }
""",
        """        private void FinishMatch(string message)
        {
            if (Screen == GameScreen.Result) return;
            EnergyProjectile.DestroyAll();
            _resultText = message;
            _resultTimer = 0f;
            Screen = GameScreen.Result;
        }
""",
    )
    replace_once(
        path,
        """        private void ClearMatch()
        {
            foreach (FighterController fighter in _fighters)
""",
        """        private void ClearMatch()
        {
            EnergyProjectile.DestroyAll();
            foreach (FighterController fighter in _fighters)
""",
    )


def patch_projectiles() -> None:
    path = "Assets/NeonRift/Scripts/Gameplay/EnergyProjectile.cs"
    replace_once(path, "        private bool _spent;\n", "        private bool _spent;\n        private Material _material;\n")
    replace_once(
        path,
        """            projectile.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit("Special projectile", color, 0f, 1f, color * 4.5f);
            var script = projectile.AddComponent<EnergyProjectile>();
""",
        """            var script = projectile.AddComponent<EnergyProjectile>();
            script._material = MaterialFactory.CreateLit("Special projectile", color, 0f, 1f, color * 4.5f);
            projectile.GetComponent<Renderer>().sharedMaterial = script._material;
""",
    )
    replace_once(
        path,
        """        private void Update()
        {
            if (_spent) return;
""",
        """        private void Update()
        {
            if (_spent) return;
            if (NeonRiftGame.Instance == null || NeonRiftGame.Instance.Screen != GameScreen.Playing)
            {
                Destroy(gameObject);
                return;
            }
""",
    )
    replace_once(
        path,
        """        private void OnTriggerEnter(Collider other)
        {
            if (_spent || _owner == null) return;
""",
        """        private void OnTriggerEnter(Collider other)
        {
            if (_spent || _owner == null) return;
            if (NeonRiftGame.Instance == null || NeonRiftGame.Instance.Screen != GameScreen.Playing) return;
""",
    )
    replace_once(
        path,
        """            Destroy(gameObject);
        }
    }
}
""",
        """            Destroy(gameObject);
        }

        public static void DestroyAll()
        {
            foreach (EnergyProjectile projectile in UnityEngine.Object.FindObjectsByType<EnergyProjectile>(FindObjectsSortMode.None))
            {
                if (projectile != null) Destroy(projectile.gameObject);
            }
        }

        private void OnDestroy()
        {
            if (_material != null) Destroy(_material);
            _material = null;
        }
    }
}
""",
    )


def patch_fallback_material_ownership() -> None:
    path = "Assets/NeonRift/Scripts/Rendering/CommunityModel.cs"
    replace_once(path, "using UnityEngine;\n", "using System.Collections.Generic;\nusing UnityEngine;\n")
    replace_once(path, "        private GameObject _visual;\n", "        private GameObject _visual;\n        private readonly List<Material> _ownedMaterials = new();\n")
    replace_once(path, "        private static GameObject CreateFallback(Color primary, Color accent)\n", "        private GameObject CreateFallback(Color primary, Color accent)\n")
    replace_once(
        path,
        "            body.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit(\"Fallback Body\", primary, 0.15f, 0.5f);\n",
        "            body.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit(\"Fallback Body\", primary, 0.15f, 0.5f));\n",
    )
    replace_once(
        path,
        "            head.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit(\"Fallback Head\", accent, 0.05f, 0.55f);\n",
        "            head.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit(\"Fallback Head\", accent, 0.05f, 0.55f));\n",
    )
    replace_once(
        path,
        "            weapon.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit(\"Fallback Weapon\", accent, 0.35f, 0.9f, accent * 2.6f);\n",
        "            weapon.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit(\"Fallback Weapon\", accent, 0.35f, 0.9f, accent * 2.6f));\n",
    )
    replace_once(
        path,
        """            return root;
        }
    }
}
""",
        """            return root;
        }

        private Material Own(Material material)
        {
            _ownedMaterials.Add(material);
            return material;
        }

        private void OnDestroy()
        {
            foreach (Material material in _ownedMaterials)
            {
                if (material != null) Destroy(material);
            }
            _ownedMaterials.Clear();
        }
    }
}
""",
    )


def patch_arena_resource_ownership() -> None:
    path = "Assets/NeonRift/Scripts/Rendering/ArenaVisualFactory.cs"
    replace_once(path, "        private Material _skyboxMaterial;\n", "        private Material _skyboxMaterial;\n        private VolumeProfile _volumeProfile;\n")
    replace_once(
        path,
        """            if (ArenaRoot != null)
            {
                ArenaRoot.gameObject.SetActive(false);
                Destroy(ArenaRoot.gameObject);
            }

            foreach (Material material in _materials)
""",
        """            if (ArenaRoot != null)
            {
                ArenaRoot.gameObject.SetActive(false);
                Destroy(ArenaRoot.gameObject);
            }

            if (_volumeProfile != null)
            {
                Destroy(_volumeProfile);
                _volumeProfile = null;
            }

            foreach (Material material in _materials)
""",
    )
    replace_once(
        path,
        """            var profile = ScriptableObject.CreateInstance<VolumeProfile>();
            profile.name = "Neon Rift Runtime Grade";
            volume.profile = profile;

            var bloom = profile.Add<Bloom>(true);
""",
        """            _volumeProfile = ScriptableObject.CreateInstance<VolumeProfile>();
            _volumeProfile.name = "Neon Rift Runtime Grade";
            volume.profile = _volumeProfile;

            var bloom = _volumeProfile.Add<Bloom>(true);
""",
    )
    replace_once(path, "            var colorAdjustments = profile.Add<ColorAdjustments>(true);\n", "            var colorAdjustments = _volumeProfile.Add<ColorAdjustments>(true);\n")
    replace_once(path, "            var vignette = profile.Add<Vignette>(true);\n", "            var vignette = _volumeProfile.Add<Vignette>(true);\n")
    replace_once(path, "            var tonemapping = profile.Add<Tonemapping>(true);\n", "            var tonemapping = _volumeProfile.Add<Tonemapping>(true);\n")
    replace_once(
        path,
        """            foreach (Material material in _materials)
            {
                if (material != null) Destroy(material);
            }
            _materials.Clear();
        }
""",
        """            if (_volumeProfile != null)
            {
                Destroy(_volumeProfile);
                _volumeProfile = null;
            }

            foreach (Material material in _materials)
            {
                if (material != null) Destroy(material);
            }
            _materials.Clear();
        }
""",
    )


def patch_open_asset_installer() -> None:
    path = "Assets/NeonRift/Editor/OpenAssetInstaller.cs"
    replace_once(
        path,
        "        private const string UserAgent = \"NeonRift-Unity-Open-Asset-Installer/1.0\";\n",
        """        private const string UserAgent = "NeonRift-Unity-Open-Asset-Installer/1.0";
        private const int MaximumArchiveEntries = 4096;
        private const long MaximumSingleExtractedBytes = 134_217_728;
        private const long MaximumTotalExtractedBytes = 536_870_912;
        private const double MaximumCompressionRatio = 200d;
""",
    )
    replace_once(
        path,
        """                    else if (File.Exists(markerPath))
                    {
                        fileIndex += asset.files?.Length ?? 0;
                        continue;
                    }

                    Directory.CreateDirectory(targetDirectory);
""",
        """                    else if (File.Exists(markerPath) && VerifyInstalledAsset(asset, targetDirectory))
                    {
                        fileIndex += asset.files?.Length ?? 0;
                        continue;
                    }
                    else if (File.Exists(markerPath))
                    {
                        File.Delete(markerPath);
                        Debug.LogWarning($"Repairing incomplete or corrupted open asset {asset.provider}/{asset.id}.");
                    }

                    Directory.CreateDirectory(targetDirectory);
""",
    )
    replace_once(
        path,
        """        private static bool TryInstallFile(
            AssetEntry asset,
""",
        """        private static bool VerifyInstalledAsset(AssetEntry asset, string targetDirectory)
        {
            try
            {
                DownloadEntry[] files = asset.files ?? Array.Empty<DownloadEntry>();
                if (files.Length == 0) return false;

                foreach (DownloadEntry file in files)
                {
                    if (file == null) return false;
                    if (file.extract)
                    {
                        bool hasPayload = false;
                        if (Directory.Exists(targetDirectory))
                        {
                            foreach (string installedFile in Directory.EnumerateFiles(targetDirectory, "*", SearchOption.AllDirectories))
                            {
                                if (!string.Equals(Path.GetFileName(installedFile), ".open-asset.json", StringComparison.OrdinalIgnoreCase))
                                {
                                    hasPayload = true;
                                    break;
                                }
                            }
                        }
                        if (!hasPayload) return false;
                        continue;
                    }

                    string destination = SafeChildPath(targetDirectory, file.path, false);
                    if (!VerifyExisting(destination, file)) return false;
                }
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Open asset verification failed ({asset.provider}/{asset.id}): {exception.Message}");
                return false;
            }
        }

        private static bool TryInstallFile(
            AssetEntry asset,
""",
    )
    replace_once(
        path,
        """        private static void ExtractZipSafely(string archivePath, string targetDirectory)
        {
            string fullTarget = Path.GetFullPath(targetDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                                + Path.DirectorySeparatorChar;
            using ZipArchive archive = ZipFile.OpenRead(archivePath);
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string destination = Path.GetFullPath(Path.Combine(targetDirectory, entry.FullName));
                if (!destination.StartsWith(fullTarget, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Archive entry attempted to leave the target directory.");
                }
                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? targetDirectory);
                entry.ExtractToFile(destination, true);
            }
        }
""",
        """        private static void ExtractZipSafely(string archivePath, string targetDirectory)
        {
            string fullTarget = Path.GetFullPath(targetDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                                + Path.DirectorySeparatorChar;
            using ZipArchive archive = ZipFile.OpenRead(archivePath);
            if (archive.Entries.Count > MaximumArchiveEntries)
            {
                throw new InvalidDataException($"Archive contains {archive.Entries.Count} entries; limit is {MaximumArchiveEntries}.");
            }

            long totalExtractedBytes = 0;
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                int unixType = (entry.ExternalAttributes >> 16) & 0xF000;
                if (unixType == 0xA000)
                {
                    throw new InvalidDataException("Archive contains a symbolic link, which is not permitted.");
                }
                if (entry.Length > MaximumSingleExtractedBytes)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} is too large ({entry.Length} bytes).");
                }
                if (entry.Length > 0 && entry.CompressedLength == 0)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} has an invalid compression size.");
                }
                if (entry.CompressedLength > 0 && entry.Length / (double)entry.CompressedLength > MaximumCompressionRatio)
                {
                    throw new InvalidDataException($"Archive entry {entry.FullName} exceeds the compression-ratio limit.");
                }
                if (entry.Length > MaximumTotalExtractedBytes - totalExtractedBytes)
                {
                    throw new InvalidDataException($"Archive expands beyond {MaximumTotalExtractedBytes} bytes.");
                }
                totalExtractedBytes += entry.Length;

                string destination = Path.GetFullPath(Path.Combine(targetDirectory, entry.FullName));
                if (!destination.StartsWith(fullTarget, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Archive entry attempted to leave the target directory.");
                }
                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? targetDirectory);
                entry.ExtractToFile(destination, true);
            }
        }
""",
    )


def patch_asset_selection_and_lock() -> None:
    path = "tools/open_asset_catalog.py"
    replace_once(
        path,
        """    map_aliases = {
        "diff": ("diff", "albedo", "basecolor", "base_color"),
        "normal": ("nor_gl", "normal_gl", "normal"),
        "rough": ("rough", "roughness"),
        "ao": (" ao ", "_ao", "/ao", "ambientocclusion", "ambient_occlusion"),
        "metal": ("metallic", "_metal_", "-metal-", "/metal/"),
        "disp": ("disp", "height", "displacement"),
        "arm": (" arm ", "_arm", "/arm"),
    }
""",
        """    # The current URP runtime consumes only base color, OpenGL normals and AO.
    # Avoid downloading unused roughness, metallic, displacement and ARM maps.
    map_aliases = {
        "diff": ("diff", "albedo", "basecolor", "base_color"),
        "normal": ("nor_gl", "normal_gl", "normal"),
        "ao": (" ao ", "_ao", "/ao", "ambientocclusion", "ambient_occlusion"),
    }
""",
    )

    lock_path = ROOT / "AssetSources/open-assets.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for asset in lock.get("assets", []):
        if asset.get("kind") != "material" or asset.get("provider") != "polyhaven":
            continue
        asset["files"] = [
            item
            for item in asset.get("files", [])
            if any(token in str(item.get("path", "")).lower() for token in ("_diff", "_normal", "_ao"))
        ]
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def patch_versioning() -> None:
    replace_once(
        "Assets/NeonRift/Editor/ProjectSetup.cs",
        '            PlayerSettings.bundleVersion = "2.0.0-unity";\n',
        '            PlayerSettings.bundleVersion = "2.1.0";\n',
    )
    replace_once(
        "Assets/NeonRift/Editor/BuildAutomation.cs",
        '                $"Neon Rift Arena Breakers Unity Edition\\nVersion 2.1.0\\nUnity {Application.unityVersion}\\nWindows x86_64 portable build\\n");\n',
        '                $"Neon Rift Arena Breakers Unity Edition\\nVersion {PlayerSettings.bundleVersion}\\nUnity {Application.unityVersion}\\nWindows x86_64 portable build\\n");\n',
    )


def patch_ci() -> None:
    path = ".github/workflows/unity-windows.yml"
    replace_once(
        path,
        """      - run: python tools/validate_project.py
""",
        """      - name: Validate Python tools, manifests and project structure
        run: |
          python -m compileall -q tools
          python tools/asset_pipeline.py validate
          python tools/validate_project.py
""",
    )
    replace_once(path, "    name: Unity build availability summary\n", "    name: Unity verification gate\n")
    replace_once(
        path,
        """          if [[ "${{ needs.unity-license.outputs.available }}" == "true" ]]; then
            echo "Unity activation route '${{ needs.unity-license.outputs.route }}' detected. Tests/build result: ${{ needs.unity-tests.result }}/${{ needs.unity-build.result }}/${{ needs.windows-visual.result }}/${{ needs.windows-smoke.result }}"
          else
            echo "Source validation passed, but Unity jobs were skipped. Activation route: ${{ needs.unity-license.outputs.route }}."
          fi
""",
        """          results="${{ needs.unity-tests.result }}/${{ needs.unity-build.result }}/${{ needs.windows-visual.result }}/${{ needs.windows-smoke.result }}"
          if [[ "${{ needs.unity-license.outputs.available }}" != "true" ]]; then
            echo "::error::Unity verification cannot be skipped. Configure a valid activation route; detected '${{ needs.unity-license.outputs.route }}'."
            exit 1
          fi
          if [[ "${{ needs.unity-tests.result }}" != "success" ||
                "${{ needs.unity-build.result }}" != "success" ||
                "${{ needs.windows-visual.result }}" != "success" ||
                "${{ needs.windows-smoke.result }}" != "success" ]]; then
            echo "::error::One or more required Unity jobs did not succeed: $results"
            exit 1
          fi
          echo "Unity activation route '${{ needs.unity-license.outputs.route }}' detected. All required Unity jobs succeeded: $results"
""",
    )

    path = ".github/workflows/resolve-open-assets.yml"
    replace_once(
        path,
        """      - name: Show resolved catalog
        run: cat AssetSources/open-assets.lock.json

      - name: Commit updated lock file
""",
        """      - name: Show resolved catalog
        run: cat AssetSources/open-assets.lock.json

      - name: Validate resolved repository state
        run: |
          python -m compileall -q tools
          python tools/asset_pipeline.py validate
          python tools/validate_project.py
          git diff --check

      - name: Commit updated lock file
""",
    )


def patch_validator() -> None:
    path = "tools/validate_project.py"
    replace_once(
        path,
        """    "ExtractZipSafely",
    "Path attempted to leave the open-asset directory",
""",
        """    "ExtractZipSafely",
    "VerifyInstalledAsset",
    "MaximumArchiveEntries",
    "MaximumTotalExtractedBytes",
    "MaximumCompressionRatio",
    "Path attempted to leave the open-asset directory",
""",
    )
    replace_once(
        path,
        """    "class EnergyProjectile",
    "class OpenAssetInstaller",
""",
        """    "class EnergyProjectile",
    "EnergyProjectile.DestroyAll()",
    "FindObjectsByType<EnergyProjectile>",
    "class OpenAssetInstaller",
""",
    )
    replace_once(
        path,
        """asset_pipeline = read("tools/asset_pipeline.py")
for token in [
""",
        """asset_catalog = read("tools/open_asset_catalog.py")
for unused_map in ['"rough":', '"metal":', '"disp":', '"arm":']:
    require(unused_map not in asset_catalog, f"Unused Poly Haven material map is still selected: {unused_map}")

asset_pipeline = read("tools/asset_pipeline.py")
for token in [
""",
    )
    replace_once(
        path,
        """workflow = read(".github/workflows/unity-windows.yml")
for token in [
""",
        """project_setup = read("Assets/NeonRift/Editor/ProjectSetup.cs")
build_automation = read("Assets/NeonRift/Editor/BuildAutomation.cs")
require('PlayerSettings.bundleVersion = "2.1.0"' in project_setup, "Unity bundle version must be 2.1.0")
require("Version {PlayerSettings.bundleVersion}" in build_automation, "Distribution version must use PlayerSettings.bundleVersion")

workflow = read(".github/workflows/unity-windows.yml")
for token in [
""",
    )
    replace_once(
        path,
        """    "SHA256SUMS.txt",
]:
""",
        """    "SHA256SUMS.txt",
    "Unity verification cannot be skipped",
    "python tools/asset_pipeline.py validate",
]:
""",
    )
    replace_once(
        path,
        """    "AssetSources/open-assets.lock.json",
]:
""",
        """    "AssetSources/open-assets.lock.json",
    "python tools/validate_project.py",
    "git diff --check",
]:
""",
    )


def main() -> None:
    patch_game_navigation_and_lifecycle()
    patch_projectiles()
    patch_fallback_material_ownership()
    patch_arena_resource_ownership()
    patch_open_asset_installer()
    patch_asset_selection_and_lock()
    patch_versioning()
    patch_ci()
    patch_validator()
    print("Repository hardening changes applied.")


if __name__ == "__main__":
    main()
