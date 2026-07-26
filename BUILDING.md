# Building Neon Rift

## Pinned toolchain

- Godot Engine **4.7.1 stable**, standard build (not Mono)
- Matching official Godot 4.7.1 export templates
- Windows Desktop x86_64 export

Download the editor and templates only from the official Godot website or the `godotengine/godot-builds` GitHub organization.

## Local Windows build

1. Install or unpack Godot 4.7.1 stable.
2. Install the matching export templates in Godot's Export Template Manager.
3. Open `project.godot`.
4. Run the project for a functional check.
5. Export the preset named `Windows Desktop` to `dist/NeonRift-Windows-Portable/NeonRift.exe`.
6. Keep `NeonRift.exe` and `NeonRift.pck` together.

The PCK is deliberately not embedded. Godot documentation notes that embedded PCKs can increase antivirus false positives on Windows and interfere with signing workflows.

## CI build

`.github/workflows/build-windows.yml` downloads pinned official binaries, runs validation and tests, exports on `windows-latest`, performs a headless launch check of the actual EXE, creates a normal ZIP, and generates SHA-256 checksums.

No installer, executable packer, obfuscator, self-extractor, or dynamic code downloader is used.
