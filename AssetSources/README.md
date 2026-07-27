# Browser-managed open asset pipeline

This folder is the control surface for Poly Haven and ambientCG assets used by the Unity project.
The workflow is designed for ChatGPT in the browser plus the GitHub connector; no local MCP server,
API key or desktop asset manager is required.

## How it works

1. Ask ChatGPT to find a CC0 model, material or HDRI on Poly Haven or ambientCG.
2. ChatGPT searches the provider API and adds the chosen provider ID to `open-assets.json`.
3. GitHub Actions runs `tools/open_asset_catalog.py resolve` before the Unity build.
4. The resolver writes temporary direct download URLs, sizes and hashes to `open-assets.lock.json`.
5. Unity's `OpenAssetInstaller` downloads the resolved files into the ignored directory
   `Assets/Resources/Community/OpenAssets/` and verifies the available integrity metadata.
6. Unity imports the files and the normal Neon Rift build continues.

Binary files stay out of Git. The manifest, resolver and license/source documentation remain reviewable.

## Manifest format

```json
{
  "schemaVersion": 1,
  "defaults": {
    "resolution": "2k",
    "maxDownloadBytes": 104857600
  },
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

Supported providers: `polyhaven`, `ambientcg`.

Supported kinds: `model`, `material`, `hdri`.

`target` is always relative to `Assets/Resources/Community/OpenAssets/`.
Use 1K or 2K unless a specific gameplay asset visibly needs more detail.

## Repository commands

Validate without network access:

```bash
python tools/open_asset_catalog.py validate
```

Search a provider:

```bash
python tools/open_asset_catalog.py search --provider polyhaven --kind model --query "industrial barrel"
python tools/open_asset_catalog.py search --provider ambientcg --kind material --query "wet concrete"
```

Resolve all enabled requests:

```bash
python tools/open_asset_catalog.py resolve
```

The GitHub Actions Windows build performs validation and resolution automatically.

## Prompt for ChatGPT

```text
@GitHub

Find a CC0 asset for Neon Rift using Poly Haven first and ambientCG second.
Use the provider API, choose at most 2K, keep the total download below 100 MB,
and prefer glTF/GLB for models or JPG/PNG for materials.

Add the selected provider ID to AssetSources/open-assets.json with a clear target path.
Do not add binary files to Git. Validate the manifest and update source documentation when needed.
```

Poly Haven live-API access is credited as **Powered by Poly Haven**. Both providers' downloaded assets
are CC0, but source records are retained for auditing and reproducibility.
