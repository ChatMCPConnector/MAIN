#!/usr/bin/env bash
# secret-perms.sh: Secrets 600/700 halten — und die Default-ACL entschärfen.
#
# Warum (2026-10-01): Der Codespace-FS /workspaces (ext4) trägt eine geerbte
# POSIX-Default-ACL `USER_OBJ/GROUP_OBJ/OTHER = rwx`. Die hebelt `umask`
# vollständig aus: neue Dateien werden 666, Verzeichnisse 777 — egal was ein
# Skript zuvor `umask 077` setzt (live belegt). `setfacl`/`getfacl` sind im
# Image nicht installiert, deshalb macht dieses Skript zwei Dinge:
#   (a) explizites chmod auf die bekannten Secret-Pfade,
#   (b) die zu weite Default-ACL der empfindlichen Verzeichnisse (inkl.
#       Repo-Root) per python3 `os.removexattr` entfernen — danach greift dort
#       wieder `umask`, sodass auch zur Laufzeit neu geschriebene Dateien 600
#       werden (z.B. `temp/users.json`, das die ZeroKey-App atomar neu anlegt).
#
# Idempotent; Inhalte werden nie angefasst. Aufruf: setup.sh (vor dem Unlock).
# `verify-codespace.sh` prüft das Ergebnis.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Bekannte Secret-Dateien: 600. Fehlende werden übersprungen (werden später von
# `secrets.sh unlock` mit eigenem chmod angelegt).
SECRET_FILES=(
  config/passphrase
  config/secrets.enc
  config/secrets.manifest
  llm-proxies/glm2api/.env
)
# Empfindliche Verzeichnisse, deren geerbte Default-ACL entfernt wird.
SECRET_DIRS=(
  .runtime
  config
  llm-proxies/glm2api
)

for f in "${SECRET_FILES[@]}"; do
  [ -e "$f" ] && chmod 600 "$f" 2>/dev/null || true
done
[ -d .runtime ] && chmod 700 .runtime 2>/dev/null || true

# Default-ACL entfernen — inkl. Repo-Root, damit neu angelegte Verzeichnisse
# nicht wieder `rwx rwx rwx` erben. Ohne setfacl, deshalb python3 (im Image da).
python3 - "$REPO_ROOT" "${SECRET_DIRS[@]}" <<'PYEOF' 2>/dev/null || true
import os, sys
for d in sys.argv[1:]:
    try:
        os.removexattr(d, "system.posix_acl_default")
    except OSError:
        pass
PYEOF

echo "secret-perms: 600/700 gesetzt, Default-ACL entfernt (${#SECRET_FILES[@]} Dateien, ${#SECRET_DIRS[@]} Verzeichnisse + Root)."
