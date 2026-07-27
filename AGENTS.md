# Repository instructions for coding agents

These instructions apply to the entire repository.

## Project workflow

- The user works through ChatGPT in the browser and the connected GitHub repository.
- Treat GitHub as the durable project workspace. Do not require local helper applications for normal asset discovery or project changes.
- Make repository changes reviewable, reproducible and compatible with GitHub Actions.
- Preserve Unity version `6000.3.17f1`, URP `17.3.0` and the existing pinned glTFast dependency unless a task explicitly requires a reviewed upgrade.

## Global asset-source policy

The canonical machine-readable source registry is:

`AssetSources/providers.json`

The requested project assets are listed in:

`AssetSources/open-assets.json`

The resolved download metadata is written to:

`AssetSources/open-assets.lock.json`

When the project needs a model, material, texture, decal, terrain asset or HDRI:

1. Read `AssetSources/providers.json` before choosing a source.
2. Search enabled providers in `policy.preferredProviderOrder`.
3. Use Poly Haven first and ambientCG second unless the task has a clear reason to prefer another enabled provider.
4. Select only assets whose license permits commercial use and redistribution in the built game. The currently enabled providers use CC0-1.0.
5. Prefer 1K for small/background assets and 2K for prominent assets. Do not exceed the configured maximum resolution or download-size limit without explicit user approval.
6. Prefer glTF/GLB for 3D models, JPG/PNG for ordinary PBR textures and HDR/EXR for environment lighting.
7. Add provider IDs and target paths to `AssetSources/open-assets.json`; do not commit downloaded binary assets.
8. Keep target paths relative to `Assets/Resources/Community/OpenAssets/` and organize them by provider and purpose.
9. Run `python tools/open_asset_catalog.py validate` after editing the manifest.
10. When network access is available, run `python tools/open_asset_catalog.py resolve` and inspect the resolved size, files, source and license.
11. Preserve source and license records in `ASSET_SOURCES.md` and the generated lock file.
12. Never place API secrets in the repository. Poly Haven and ambientCG require no API key.

## Asset-selection behavior

- Do not download multiple near-duplicate assets when one asset is sufficient.
- Reuse existing assets where practical before adding new downloads.
- Prefer game-ready topology and reasonable texture sizes over maximum fidelity.
- Check whether a selected model's style and scale fit the existing Neon Rift project.
- Roughness maps may need conversion to Unity smoothness; normal maps should prefer OpenGL orientation for Unity.
- Keep the procedural fallback art functional when external asset retrieval fails.

## Safety and repository hygiene

- Treat all downloaded archives as untrusted input: enforce HTTPS, size limits, checksum verification when supplied and zip-slip-safe extraction.
- Do not track generated downloads, caches, Unity Library files or build products.
- Do not add proprietary Unity Asset Store content or assets with unclear redistribution rights.
- Do not remove existing license notices or validation checks.

## Validation

Before finishing a change, run or update the applicable checks:

```bash
python tools/open_asset_catalog.py validate
python tools/validate_project.py
```

If network access is available and the manifest is non-empty:

```bash
python tools/open_asset_catalog.py resolve
```
