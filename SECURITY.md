# Security and privacy

Neon Rift is an offline game. The runtime contains no telemetry, advertisements, account system, analytics SDK, remote-control service or background updater.

Network access is used only by the Unity Editor asset installer to retrieve the exact public CC0 files listed in `ASSET_SOURCES.md`. The Unity Editor imports the downloaded files into project Resources before the build. Runtime builds perform no asset downloads and contain only local imported data.

The Windows build is unsigned. Reputation-based antivirus warnings are therefore possible. GitHub Actions produces a SHA-256 checksum and performs a real launch smoke test, but these checks do not replace a user's preferred antivirus or VirusTotal policy.

Do not commit Unity credentials or license files. Store them only as encrypted GitHub Secrets.
