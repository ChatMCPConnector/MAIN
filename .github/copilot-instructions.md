# GitHub Copilot repository instructions

Follow the root `AGENTS.md` for all work in this repository.

For third-party art and environment content, use the global provider registry in
`AssetSources/providers.json` and the request manifest in `AssetSources/open-assets.json`.
Do not commit downloaded binary assets. Prefer Poly Haven, then ambientCG, stay within the
configured 1K/2K and size limits, and retain CC0 source/license metadata.

Validate manifest changes with:

```bash
python tools/open_asset_catalog.py validate
```
