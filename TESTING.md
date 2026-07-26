# Testing

## Automated logic tests

Run with Godot 4.7.1:

```text
godot --headless --path . --script tests/test_runner.gd
```

The test runner checks project loading, main menu startup, character/stage/mode counts, stage spawning, movement/combat primitives, damage, specials, second local player, team assignment, training dummy, and required export/documentation files.

## Visual smoke gallery

CI starts the project under a virtual display and captures:

1. Main menu
2. Character select
3. Stage select
4. Stage combat
5. Special attack
6. Boss fight
7. Pause menu
8. Result screen

The screenshots are uploaded as `NeonRift-Visual-Smoke-Gallery` for human inspection.

## Windows start test

The Windows job exports the game, starts the exact packaged `NeonRift.exe` with `--headless --smoke-test`, waits for its exit, verifies exit code zero, and checks `smoke-test.log` for `PASS`. This detects immediate engine startup failures, missing PCK/DLL problems, and core initialization errors.

## Manual acceptance checklist

- Test both keyboard layouts simultaneously.
- Test two physical controllers and keyboard/controller combinations.
- Play each mode through to its result screen.
- Check all three arenas at 1280×720 and a larger resolution.
- Toggle fullscreen and restart to confirm portable settings persistence.
- Inspect audio levels and rapid-combo responsiveness.
- Scan the final ZIP manually with the user's preferred antivirus/VirusTotal policy.
