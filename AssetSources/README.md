# Browser-managed open asset pipeline

This folder is the repository-wide control surface for Poly Haven and ambientCG assets used by the Unity project. The workflow is designed for ChatGPT in the browser plus the GitHub connector; no local MCP server, API key or desktop asset manager is required.

## Global configuration

`providers.json` is the canonical source registry. It defines:

- which asset platforms are enabled;
- provider priority;
- official API endpoints;
- authentication requirements;
- licenses and credits;
- supported asset kinds and preferred formats;
- global resolution and download-size limits.

Agents should read the root `AGENTS.md` before changing assets. GitHub Copilot receives the matching instructions from `.github/copilot-instructions.md`.

`open-assets.json` contains only the concrete assets requested by the game. It does not repeat API addresses, licenses or global limits.

## How it works

1. Ask ChatGPT to find a CC0 model, material or HDRI.
2. ChatGPT reads `providers.json`, searches enabled providers in the configured order and adds the selected provider ID to `open-assets.json`.
3. `.github/workflows/resolve-open-assets.yml` runs `tools/asset_pipeline.py resolve`.
4. The resolver writes direct HTTPS download URLs, sizes, available hashes, source pages and licenses to `open-assets.lock.json`.
5. Unity's `OpenAssetInstaller` downloads the resolved files into the ignored directory `Assets/Resources/Community/OpenAssets/`.
6. Unity verifies declared sizes and MD5 hashes when available, safely extracts ZIP files and imports the results.
7. The normal Neon Rift build continues. Procedural fallback art remains available if a host is temporarily unavailable.

Binary files and caches stay out of Git. The provider registry, asset requests, lock file and license/source documentation remain reviewable.

## Request manifest

```json
{
  "schemaVersion": 1,
  "assets": [
    {
      "provider": "polyhaven",
      "id": "asset_slug",
      "kind": "model",
      "resolution": "2k",
      "format": "gltf",
      "target": "PolyHaven/Props/AssetName"
    },
    {
      "provider": "ambientcg",
      "id": "MaterialId001",
      "kind": "material",
      "resolution": "2k",
      "format": "jpg",
      "target": "AmbientCG/Materials/MaterialName"
    }
  ]
}
```

`resolution`, `format`, `target` and `maxDownloadBytes` may be omitted when the global provider defaults are suitable. `target` is always relative to `Assets/Resources/Community/OpenAssets/`.

## Repository commands

Validate the global source registry and request manifest without downloading assets:

```bash
python tools/asset_pipeline.py validate
```

Search in global provider order:

```bash
python tools/asset_pipeline.py search --provider auto --kind model --query "industrial barrel"
```

Search a specific provider:

```bash
python tools/asset_pipeline.py search --provider polyhaven --kind model --query "industrial barrel"
python tools/asset_pipeline.py search --provider ambientcg --kind material --query "wet concrete"
```

Resolve all enabled requests:

```bash
python tools/asset_pipeline.py resolve
```

`tools/open_asset_catalog.py` is the provider-specific resolver engine. Normal repository work should use the global `asset_pipeline.py` front end.

## Prompt for ChatGPT

```text
@GitHub

Read AGENTS.md and AssetSources/providers.json first.
Find a suitable CC0 asset for Neon Rift using the globally configured source priority.
Reuse an existing asset when practical and stay within the configured resolution and size limits.

Add only the selected provider ID and game target to AssetSources/open-assets.json.
Do not add downloaded binary files to Git.
Run python tools/asset_pipeline.py validate after the change.
```

Poly Haven live-API access is credited as **Powered by Poly Haven**. Both enabled providers' downloaded assets are CC0, but source records are retained for auditing and reproducibility.
