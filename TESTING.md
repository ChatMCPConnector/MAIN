# Testing

## Static validator

```text
python tools/validate_project.py
```

This checks the Unity version, package pins, required C# components, CC0 source pins, documentation, workflow configuration and removal of the former Godot project files.

## Unity EditMode tests

The `NeonRift.EditModeTests` assembly checks:

- four fighter definitions,
- three arena definitions,
- five mode definitions,
- damage scaling,
- minimum damage and knockback invariants.


## Visual Windows gallery

The packaged Windows player is also launched with `--capture-ci`. It renders eight real 1280×720 states: main menu, mode selection, character selection, arena selection, combat, boss combat, pause and result. CI rejects fewer than eight PNG files and uploads the complete gallery with player logs for human review.

## Windows player smoke test

The built Windows player is launched with:

```text
NeonRift.exe -batchmode -nographics --smoke-test
```

The runtime starts Training mode, creates two fighters, applies verified damage, writes `smoke-test.log` beside the executable and returns a non-zero process code if the contract fails.

## Manual acceptance checklist

- Confirm all eight KayKit GLB models were imported through glTFast, load from Resources and animate.
- Confirm Kenney props appear around each arena.
- Play all five modes to a result or progression state.
- Test both keyboard layouts simultaneously.
- Test two physical gamepads and mixed keyboard/gamepad play.
- Inspect the three arena themes at 1280×720 and a larger resolution.
- Check bloom, fog and emission on a DirectX 11 Windows system.
- Confirm the procedural fallback remains playable after temporarily moving the downloaded asset directories.
