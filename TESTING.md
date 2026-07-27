# Testing

## Static validator

```text
python -m compileall -q tools
python tools/asset_pipeline.py validate
python tools/validate_project.py
```

This checks the Unity version, package pins, required C# components, CC0 source pins, documentation, workflow configuration and removal of the former Godot project files. It also verifies the open-asset repair and ZIP safety guards, runtime cleanup hooks, canonical build version, Unity verification gate and the pruned Poly Haven lock policy.

## Unity EditMode tests

The `NeonRift.EditModeTests` assembly checks:

- four unique and usable fighter definitions,
- three unique and usable arena definitions,
- complete coverage of all five game modes,
- heavy and special damage scaling,
- monotonic power scaling,
- minimum damage and knockback invariants.

## Visual Windows gallery

The packaged Windows player is also launched with `--capture-ci`. It renders eight real 1280×720 states: main menu, mode selection, character selection, arena selection, combat, boss combat, pause and result. CI rejects fewer than eight PNG files and uploads the complete gallery with player logs for human review.

## Windows player smoke test

The built Windows player is launched with:

```text
NeonRift.exe -batchmode -nographics --smoke-test
```

The runtime starts Training mode, creates two fighters, applies verified damage, writes `smoke-test.log` beside the executable and returns a non-zero process code if the contract fails.

## CI verification policy

Pull requests always run the static validators. Unity-dependent jobs run when a valid Unity activation route is configured. A push to `main` is not considered successfully verified when Unity tests, the Windows build, the visual gallery or the smoke test are skipped.

## Manual acceptance checklist

- Confirm all eight KayKit GLB models were imported through glTFast, load from Resources and animate.
- Confirm Kenney props appear around each arena.
- Play all five modes to a result or progression state.
- Test character and arena selection with all four arrow keys.
- Confirm projectiles disappear immediately when the result screen opens.
- Test both keyboard layouts simultaneously.
- Test two physical gamepads and mixed keyboard/gamepad play.
- Inspect the three arena themes at 1280×720 and a larger resolution.
- Check bloom, fog and emission on a DirectX 11 Windows system.
- Change arenas repeatedly and inspect memory usage for stable runtime material and VolumeProfile counts.
- Check that deleting one installed open-asset file triggers repair on the next installer run.
- Confirm the procedural fallback remains playable after temporarily moving the downloaded asset directories.
