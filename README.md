# Neon Rift: Arena Breakers

Neon Rift is a compact, original 2.5D side-view arena brawler inspired by the pace and local multiplayer atmosphere of classic arcade fighting games. It uses no Little Fighter 2 names, characters, graphics, audio, code, or other copyrighted assets.

## Features

- Five modes: Stage Run, Local Versus, Team Battle, Training, and Survival.
- Four distinct fighters: Kira Volt, Brakk Forge, Mira Bloom, and Nyx Shade.
- Five enemy roles: brawler, runner, ranger, elite, and boss.
- Three arenas: Skyline Foundry, Verdant Metro, and Null Observatory.
- Horizontal and depth movement, jump, dash/guard, light/heavy attacks, specials, combos, knockback, projectiles, pickups, destructible props, health and energy.
- Keyboard and basic two-controller input.
- Procedural vector graphics and synthesized sound effects; no downloaded game assets.
- Portable Windows export with an external PCK, no installer, telemetry, advertising, network calls, registry persistence, or administrator requirement.

## Start the portable Windows build

1. Download the `NeonRift-Windows-Portable` workflow artifact.
2. Extract `NeonRift-Windows-Portable.zip` to a writable folder.
3. Run `NeonRift.exe`.
4. Settings are saved as `settings.cfg` beside the executable.

Windows 10/11 x86_64 and a GPU supporting Godot's GL Compatibility renderer are recommended.

## Build locally

The project targets **Godot Engine 4.7.1 stable**. Open `project.godot` in Godot, install matching export templates, and export the `Windows Desktop` preset. See [BUILDING.md](BUILDING.md).

## Controls

See [CONTROLS.md](CONTROLS.md). The same overview is available in the game.

## Testing

GitHub Actions validates source structure, runs Godot headless tests, renders eight visual smoke screenshots, exports Windows, launches the exported EXE in headless smoke mode, packages the portable ZIP, and produces SHA-256 checksums. See [TESTING.md](TESTING.md).

## Known limitations

- Art is intentionally procedural and stylized rather than sprite-sheet based.
- Controller remapping is not yet exposed in the UI.
- Automated CI confirms startup and logic but cannot replace hands-on latency and controller testing on a real Windows PC.
- The unsigned executable may still trigger a reputation-based antivirus warning despite the transparent build process.

## License

Source code is MIT licensed. Godot Engine is distributed under the MIT license by its contributors. Asset and audio details are separated in [ASSET_LICENSES.md](ASSET_LICENSES.md).
