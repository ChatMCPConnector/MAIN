# Security

Neon Rift is an offline game. It contains no networking, telemetry, advertising, updater, account system, background service, registry persistence, autostart, privilege escalation, code injection, obfuscation, executable packing, or dynamic code download.

## Build trust

- Engine/editor/templates are pinned to official Godot 4.7.1 stable downloads.
- The Windows PCK is external rather than embedded.
- CI produces a binary manifest and SHA-256 checksums.
- The portable package is a normal ZIP, never a self-extracting executable.
- No signing certificate or private key is stored in the repository.

## Antivirus and VirusTotal

No unsigned indie executable can be guaranteed to receive zero heuristic detections. A code-signing certificate can reduce reputation warnings, but none is assumed.

VirusTotal uploads may share files with security vendors. CI therefore does not upload builds automatically without an explicitly configured, authorized process. Use the checksum in `SHA256SUMS.txt`, confirm the file is non-confidential, then upload the portable ZIP manually if acceptable. Record the scan URL, date, SHA-256, detection count, and engines that report a finding.

Report security concerns through a private GitHub security advisory where available rather than a public issue.
