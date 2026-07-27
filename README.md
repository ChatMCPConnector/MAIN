# Neon Rift: Arena Breakers — Unity Edition

Neon Rift is an original 2.5D local arena brawler rebuilt for **Unity 6.3 LTS**. The Unity edition replaces the former procedural Godot presentation with a lit 3D arena, animated CC0 characters, dynamic camera framing, URP post-processing, neon materials, particles, fog and three distinct visual themes.

## Highlights

- Five modes: Stage Run, Local Versus, Team Battle, Training and Survival.
- Four fighters: Kira Volt, Brakk Forge, Mira Bloom and Nyx Shade.
- KayKit CC0 adventurer models for the player roster.
- KayKit CC0 skeleton models for enemies, elites and bosses.
- Kenney CC0 Mini Arena and City Kit Industrial environment props.
- Globally configured Poly Haven and ambientCG source pipeline for additional CC0 models, materials and HDRIs.
- Five curated 1K CC0 assets provide arena-specific PBR floors, walls, tower facades and panoramic environment lighting.
- Three arenas: Skyline Foundry, Verdant Metro and Null Observatory.
- Four-direction arena movement, jumping, dash/guard, light/heavy attacks and energy specials.
- Local keyboard and two-gamepad support through Unity's Input System.
- URP lighting, bloom, ACES tonemapping, fog, emissive surfaces, impact particles and camera shake.
- Procedural fallback characters and props when a community download is unavailable.
- Portable Windows build with a real executable smoke test in GitHub Actions.

## Unity version

The project is pinned to **Unity 6000.3.17f1** and URP 17.3. Install the same editor version and the Windows Build Support module through Unity Hub.

## First launch

1. Open this repository as a Unity project.
2. Unity automatically creates the main scene and URP assets.
3. Run **Neon Rift → Download or repair CC0 assets** for the existing KayKit and Kenney packages.
4. Run **Neon Rift → Download or repair Poly Haven and ambientCG assets** when `AssetSources/open-assets.json` contains requested open assets.
5. Open `Assets/NeonRift/Scenes/Main.unity` and press Play.

The game remains runnable with generated fallback art if an asset host is temporarily unavailable.

## Browser-managed assets

The repository is configured so ChatGPT can act as the asset worker while GitHub remains the project platform:

1. Repository-wide source rules live in `AssetSources/providers.json`.
2. Agent behavior is defined in root `AGENTS.md` and `.github/copilot-instructions.md`.
3. ChatGPT adds selected provider IDs to `AssetSources/open-assets.json`.
4. GitHub Actions resolves those IDs through the configured APIs and updates `AssetSources/open-assets.lock.json`.
5. Unity downloads the resolved assets into an ignored project directory during installation or build.

No Poly Haven or ambientCG API key is required. Downloaded binary files and caches are intentionally not committed to Git. See [AssetSources/README.md](AssetSources/README.md) for the complete workflow.

## Build Windows

Use **Neon Rift → Build portable Windows game**. The build is written to:

```text
build/StandaloneWindows64/NeonRift/
```

The build command downloads missing CC0 source assets, prepares the Unity scene, creates the URP configuration, builds `NeonRift.exe` and copies documentation and license notices beside the executable.

## GitHub Actions and Unity licensing

Static project and license checks always run. Unity Editor tests and the Windows build run when the repository has a usable Unity license configuration in GitHub Secrets:

- `UNITY_LICENSE`, or
- `UNITY_EMAIL`, `UNITY_PASSWORD` and `UNITY_SERIAL`.

Without those secrets, Unity-dependent jobs are deliberately skipped rather than reporting a false successful build. See [BUILDING.md](BUILDING.md).

## Asset policy

No proprietary Unity Asset Store package is copied into this public repository. Selected community content is downloaded from pinned public sources with redistribution-friendly licenses. Exact files, commits, URLs and licenses are listed in [ASSET_SOURCES.md](ASSET_SOURCES.md).

## License

Original source code is MIT licensed. Third-party engine packages and CC0 assets retain their own licenses as described in `ThirdPartyNotices` and `ASSET_SOURCES.md`.
