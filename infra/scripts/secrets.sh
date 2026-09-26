#!/usr/bin/env bash
# secrets.sh: deine Secrets (API-Keys, opencode-Login, .env) verschlüsselt im Git mitschleppen.
# Sinn: beide Accounts sind deine -> ein Bundle, eine Passphrase, null Aufwand pro Codespace.
# Sicherheit: Repo ist PUBLIC -> die Datei config/secrets.enc kann jeder sehen, aber ohne
# deine Passphrase ist sie nutzlos. Starke, einmalige Passphrase wählen. Bei Verdacht: PAT
# auf GitHub revoken, .env-Keys rotieren, neu locken.
#
# WICHTIG (2026-09-06): Die Passphrase ist NUR ein Entschlüsselungswort — nie ein GitHub-PAT
# oder ein anderer Secret benutzen (der alte PAT wurde dadurch geleakt+revoked). Die
# Passphrase liegt als Klartext in config/passphrase (bewusst, Komfort>Auto-Unlock), ein
# Leak allein dieser Datei ist damit wertlos. Der PAT selbst gehört nur verschlüsselt ins
# Bundle bzw. als Codespaces-Secret LANDSCAPE_PAT.
#
#   ./infra/scripts/secrets.sh lock     # packt ein (Passphrase-Abfrage, unsichtbar). DANACH sagst du dem Agent "save".
#   ./infra/scripts/secrets.sh unlock   # packt aus (automatisch wenn LANDSCAPE_PASSPHRASE gesetzt, sonst Abfrage)
#   ./infra/scripts/secrets.sh status   # zeigt was drin ist (ohne Passphrase, ohne Inhalte)
#
# Vollautomatisch: LANDSCAPE_PASSPHRASE als Codespaces-Secret pro Account hinterlegen ->
# jeder neue Codespace entsperrt sich beim Start von selbst (siehe setup.sh).
# WICHTIG: Die Passphrase tippst DU im Terminal ein. Nie in den Chat schreiben.
#
# ROBUSTHEIT (2026-09-26): Der Unlock probiert ALLE verfügbaren Passphrase-Kandidaten
# durch, bis einer das Bundle entschlüsselt. Grund: In einem Account war
# LANDSCAPE_PASSPHRASE versehentlich mit dem PAT befüllt. Das Bundle ließ sich damit
# nicht öffnen, die Key-Dateien blieben aus -> opencode startete nicht mehr
# ("bad file reference: {file:~/.config/landscape/nvidia-nim.key}"). Jetzt gewinnt
# der Kandidat, der tatsächlich entschlüsselt, und config/passphrase ist der
# zuverlässige Fallback. Kandidaten, die nach einem PAT aussehen, werden verworfen.
set -euo pipefail
cd "$(dirname "$0")/../.."
BUNDLE="config/secrets.enc"
MANIFEST="config/secrets.manifest"

# Ein PAT ist KEINE Passphrase. Typische Prefixe: ghp_, gho_, ghu_, ghs_, ghr_,
# github_pat_, glpat-. Solche Werte werden als Kandidat ignoriert (mit Warnung).
looks_like_pat() {
  case "$1" in
    ghp_*|gho_*|ghu_*|ghs_*|ghr_*|github_pat_*|glpat-*) return 0 ;;
    *) return 1 ;;
  esac
}

# Gibt alle nutzbaren Passphrase-Kandidaten aus, eine pro Zeile, in
# absteigender Verlässlichkeit. Achtung: KEIN "[ -n ] && cmd"-Statement —
# unter `set -e` würde dessen Fehlstatus das Skript abbrechen.
passphrase_candidates() {
  if [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && ! looks_like_pat "$LANDSCAPE_PASSPHRASE"; then
    printf '%s\n' "$LANDSCAPE_PASSPHRASE"
  fi
  if [ -f "config/passphrase" ]; then
    # printf statt cat: die Datei hat oft KEIN abschliessendes Newline, und
    # `read` verwirft eine solche letzte Zeile (EOF -> Status 1).
    printf '%s\n' "$(cat "config/passphrase")"
  fi
  return 0
}

# Interaktive Passphrase als weiterer Kandidat (nur wenn ein TTY da ist).
prompt_passphrase() {
  local p
  [ -t 0 ] || return 1
  read -rsp "Secrets-Passphrase: " p </dev/tty || return 1
  echo ""
  [ -n "$p" ] || return 1
  printf '%s\n' "$p"
}

# Sucht den ersten Kandidaten, der das Bundle entschlüsselt. Setzt
# LANDSCAPE_PASSPHRASE auf den Gewinner. Gibt 0 zurück, wenn einer passt.
try_passphrase() {
  local p="$1" stage="$2"
  [ -n "$p" ] || return 1
  LANDSCAPE_PASSPHRASE="$p" openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass env:LANDSCAPE_PASSPHRASE -in "$BUNDLE" -out "$stage/bundle.tgz" 2>/dev/null || return 1
  tar -tzf "$stage/bundle.tgz" >/dev/null 2>&1 || return 1
  LANDSCAPE_PASSPHRASE="$p"
  export LANDSCAPE_PASSPHRASE
  return 0
}

# Uebernimmt das entschluesselte Tarball aus dem Stage-Verzeichnis und
# raeumt das Stage auf. Der Aufrufer ist fuer das Entfernen zustaendig.
keep_decrypted() {
  DECRYPTED_TARBALL="$1/bundle.tgz"
}

# Beim Erfolg bleibt das entschluesselte Tarball in DECRYPTED_TARBALL liegen,
# damit cmd_unlock nicht ein zweites Mal entschluesseln muss.
DECRYPTED_TARBALL=""

find_working_passphrase() {
  local stage p
  stage="$(mktemp -d)"
  # "|| [ -n \"$p\"]": letzte Zeile ohne Newline (config/passphrase) mitnehmen
  while IFS= read -r p || [ -n "$p" ]; do
    if try_passphrase "$p" "$stage"; then keep_decrypted "$stage"; return 0; fi
  done < <(passphrase_candidates)
  # Interaktive Nachfrage NUR wenn wirklich ein Terminal da ist und der Aufrufer
  # sie nicht abgewählt hat. Sonst wartet der Codespace-Build (postCreateCommand)
  # auf eine Eingabe, die niemand tippt — live am 2026-09-26 im Testblock
  # reproduziert: leeres LANDSCAPE_PASSPHRASE -> Haenger an /dev/tty.
  if [ "${SECRETS_NO_PROMPT:-0}" != "1" ] && [ -t 0 ] && [ -r /dev/tty ]; then
    if p="$(prompt_passphrase 2>/dev/null)"; then
      if try_passphrase "$p" "$stage"; then keep_decrypted "$stage"; return 0; fi
    fi
  fi
  rm -rf "$stage"
  if [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && looks_like_pat "$LANDSCAPE_PASSPHRASE"; then
    echo "WARN: LANDSCAPE_PASSPHRASE sieht aus wie ein PAT — als Passphrase verworfen." >&2
    echo "      Richtig ist der Inhalt von config/passphrase (auch als Codespaces-Secret)." >&2
  fi
  return 1
}

# "fehlt" aus Sicht des Unlock: Datei existiert nicht ODER ist 0 Byte
# (Platzhalter aus keys.sh ensure). Belegte lokale Secrets bleiben unangetastet.
missing_or_empty() {
  [ ! -f "$1" ] || [ ! -s "$1" ]
}

# Für `lock`: genau eine Passphrase, kein Durchprobieren nötig.
get_passphrase() {
  if [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && ! looks_like_pat "$LANDSCAPE_PASSPHRASE"; then return 0; fi
  if [ -f "config/passphrase" ]; then
    LANDSCAPE_PASSPHRASE="$(cat "config/passphrase")"
    export LANDSCAPE_PASSPHRASE
    return 0
  fi
  # Wie beim Unlock: keine TTY / Aufrufer will keine Nachfrage -> abbrechen statt
  # auf eine Eingabe warten, die im Codespace-Build nie kommt.
  if [ "${SECRETS_NO_PROMPT:-0}" = "1" ] || [ ! -t 0 ] || [ ! -r /dev/tty ]; then
    echo "Abgebrochen: keine Passphrase (kein TTY bzw. SECRETS_NO_PROMPT=1)." >&2
    exit 1
  fi
  read -rsp "Secrets-Passphrase: " LANDSCAPE_PASSPHRASE
  echo ""
  [ -n "${LANDSCAPE_PASSPHRASE:-}" ] || { echo "Abgebrochen: keine Passphrase."; exit 1; }
  export LANDSCAPE_PASSPHRASE
}

cmd_lock() {
  local stage; stage="$(mktemp -d)"
  trap "rm -rf '$stage'" EXIT
  local found=0
  mkdir -p "$stage/files"
  # "-s" statt "-f": 0-Byte-Platzhalter aus keys.sh ensure dürfen NICHT ins
  # Bundle — sonst überschreiben sie beim nächsten Unlock den echten Key.
  [ -s "$HOME/.config/landscape/pat" ] && { cp "$HOME/.config/landscape/pat" "$stage/files/pat"; found=1; }
  [ -s "$HOME/.config/landscape/nvidia-nim.key" ] && { cp "$HOME/.config/landscape/nvidia-nim.key" "$stage/files/nvidia-nim-key"; found=1; }
  [ -s "$HOME/.config/landscape/xinjianya.key" ] && { cp "$HOME/.config/landscape/xinjianya.key" "$stage/files/xinjianya-key"; found=1; }
  [ -s "$HOME/.config/landscape/cline.key" ] && { cp "$HOME/.config/landscape/cline.key" "$stage/files/cline-key"; found=1; }
  [ -s "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json" ] && { cp "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json" "$stage/files/antigravity-oauth_creds.json"; found=1; }
  [ -s "$HOME/.config/landscape/chatglm-refresh-token" ] && { cp "$HOME/.config/landscape/chatglm-refresh-token" "$stage/files/chatglm-refresh-token"; found=1; }
  missing_or_empty "$HOME/.config/landscape/chatglm-refresh-token" && [ -f ".secrets/chatglm-refresh-token" ] && { cp ".secrets/chatglm-refresh-token" "$stage/files/chatglm-refresh-token"; found=1; }
  [ -s "$HOME/.local/share/opencode/auth.json" ] && { cp "$HOME/.local/share/opencode/auth.json" "$stage/files/opencode-auth.json"; found=1; }
  [ -s "$HOME/.config/rclone/rclone.conf" ] && { cp "$HOME/.config/rclone/rclone.conf" "$stage/files/rclone.conf"; found=1; }
  [ -s ".env" ] && { cp ".env" "$stage/files/env"; found=1; }
  [ "$found" -eq 1 ] || { echo "Nichts zu sichern (kein PAT, kein opencode-Login, kein .env)."; exit 1; }
  get_passphrase
  tar -czf "$stage/bundle.tgz" -C "$stage/files" .
  openssl enc -aes-256-cbc -pbkdf2 -pass env:LANDSCAPE_PASSPHRASE -in "$stage/bundle.tgz" -out "$BUNDLE"
  tar -tzf "$stage/bundle.tgz" | sort > "$MANIFEST"
  unset LANDSCAPE_PASSPHRASE
  echo "Verschlüsselt -> $BUNDLE"
  cat "$MANIFEST"
  echo "Fertig. Sag dem Agent 'save', damit es ins Git kommt."
}

cmd_unlock() {
  [ -f "$BUNDLE" ] || { echo "Kein Bundle ($BUNDLE fehlt)."; exit 1; }
  local noninteractive=0
  [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && noninteractive=1
  # Durchprobieren statt erster Versuch gewinnt: ein falsch gesetztes
  # Codespaces-Secret darf den Auto-Unlock nicht mehr totlegen.
  if ! find_working_passphrase; then
    echo "FEHLER: Bundle nicht entschlüsselbar (alle Passphrase-Kandidaten falsch)."
    echo "       Erwartet: Inhalt von config/passphrase — als LANDSCAPE_PASSPHRASE-Setzen"
    echo "       ODER im Repo hinterlegt lassen (dann tut der Fallback automatisch das Richtige)."
    exit 1
  fi
  # Das Tarball liegt bereits entschluesselt vor (siehe find_working_passphrase)
  local stage; stage="$(dirname "$DECRYPTED_TARBALL")"
  trap "rm -rf '$stage'" EXIT
  if [ ! -s "$DECRYPTED_TARBALL" ]; then
    unset LANDSCAPE_PASSPHRASE
    echo "FEHLER: falsche Passphrase oder Bundle kaputt."
    exit 1
  fi
  mkdir -p "$stage/files" && tar -xzf "$stage/bundle.tgz" -C "$stage/files"
  # Bestehendes nie überschreiben (lokale Secrets behalten Vorrang) — ABER eine
  # 0-Byte-Datei ist kein Secret, sondern der Platzhalter aus keys.sh ensure.
  # Sonst blockiert der Platzhalter den echten Key und der Provider bleibt
  # dauerhaft auf 401. Leere Datei zählt deshalb als "fehlt".
  if [ -f "$stage/files/pat" ] && missing_or_empty "$HOME/.config/landscape/pat"; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/pat" "$HOME/.config/landscape/pat" && chmod 600 "$HOME/.config/landscape/pat"
    ./infra/scripts/auth.sh setup "$(cat "$HOME/.config/landscape/pat")" >/dev/null 2>&1 || true
    echo "    PAT wiederhergestellt + Git/gh verdrahtet."
  fi
  if [ -f "$stage/files/opencode-auth.json" ] && missing_or_empty "$HOME/.local/share/opencode/auth.json"; then
    mkdir -p "$HOME/.local/share/opencode" && cp "$stage/files/opencode-auth.json" "$HOME/.local/share/opencode/auth.json" && chmod 600 "$HOME/.local/share/opencode/auth.json"
    echo "    opencode-Login wiederhergestellt."
  fi
  if [ -f "$stage/files/nvidia-nim-key" ] && missing_or_empty "$HOME/.config/landscape/nvidia-nim.key"; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/nvidia-nim-key" "$HOME/.config/landscape/nvidia-nim.key" && chmod 600 "$HOME/.config/landscape/nvidia-nim.key"
    echo "    NVIDIA-NIM-Key wiederhergestellt."
  fi
  if [ -f "$stage/files/xinjianya-key" ] && missing_or_empty "$HOME/.config/landscape/xinjianya.key"; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/xinjianya-key" "$HOME/.config/landscape/xinjianya.key" && chmod 600 "$HOME/.config/landscape/xinjianya.key"
    echo "    XinJianYa-Key wiederhergestellt."
  fi
  if [ -f "$stage/files/cline-key" ] && missing_or_empty "$HOME/.config/landscape/cline.key"; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/cline-key" "$HOME/.config/landscape/cline.key" && chmod 600 "$HOME/.config/landscape/cline.key"
    echo "    Cline-Key wiederhergestellt."
  fi
  if [ -f "$stage/files/chatglm-refresh-token" ] && missing_or_empty "$HOME/.config/landscape/chatglm-refresh-token"; then
    mkdir -p "$HOME/.config/landscape" && cp "$stage/files/chatglm-refresh-token" "$HOME/.config/landscape/chatglm-refresh-token" && chmod 600 "$HOME/.config/landscape/chatglm-refresh-token"
    echo "    ChatGLM-Refresh-Token wiederhergestellt."
  fi
  if [ -f "$stage/files/antigravity-oauth_creds.json" ] && missing_or_empty "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json"; then
    mkdir -p "$HOME/.config/antigravity-oauth-proxy" && cp "$stage/files/antigravity-oauth_creds.json" "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json" && chmod 600 "$HOME/.config/antigravity-oauth-proxy/oauth_creds.json"
    echo "    Antigravity-OAuth-Creds wiederhergestellt."
  fi
  if [ -f "$stage/files/rclone.conf" ] && missing_or_empty "$HOME/.config/rclone/rclone.conf"; then
    mkdir -p "$HOME/.config/rclone" && cp "$stage/files/rclone.conf" "$HOME/.config/rclone/rclone.conf" && chmod 600 "$HOME/.config/rclone/rclone.conf"
    echo "    rclone.conf (Google-Drive) wiederhergestellt."
  fi
  if [ -f "$stage/files/env" ] && missing_or_empty ".env"; then
    cp "$stage/files/env" ".env" && chmod 600 ".env"
    echo "    .env wiederhergestellt."
  fi
  [ "$noninteractive" -eq 0 ] && unset LANDSCAPE_PASSPHRASE
  # Key-Dateien garantiert vorhanden halten, damit opencode immer startet
  bash ./infra/scripts/keys.sh ensure || true
  echo "Unlock fertig."
}

cmd_status() {
  if [ -f "$BUNDLE" ]; then
    echo "Bundle: $BUNDLE ($(wc -c < "$BUNDLE" | tr -d ' ') Bytes, verschlüsselt)"
    [ -f "$MANIFEST" ] && { echo "Inhalt:"; sed 's/^/  /' "$MANIFEST"; }
    # Entschlüsselbar? Der häufigste Fehler ist ein falsch gesetztes Secret.
    if find_working_passphrase >/dev/null 2>&1; then
      echo "Passphrase: OK (ein Kandidat entschlüsselt das Bundle)"
    else
      echo "Passphrase: FEHLT/FALSCH — Unlock würde scheitern."
      if [ -n "${LANDSCAPE_PASSPHRASE:-}" ] && looks_like_pat "$LANDSCAPE_PASSPHRASE"; then
        echo "  Grund: LANDSCAPE_PASSPHRASE enthält einen PAT, nicht die Passphrase."
        echo "  Fix:   Inhalt von config/passphrase als Secret setzen (siehe infrastructure.md)."
      fi
    fi
    # find_working_passphrase legt das entschlüsselte Tarball bewusst zur
    # Wiederverwendung ab; hier wird es nur geprüft, also wieder aufräumen.
    [ -n "$DECRYPTED_TARBALL" ] && rm -rf "$(dirname "$DECRYPTED_TARBALL")"
    DECRYPTED_TARBALL=""
  else
    echo "Kein Bundle vorhanden. Mit './infra/scripts/secrets.sh lock' erstellen."
  fi
  echo ""
  bash ./infra/scripts/keys.sh status
}

case "${1:-status}" in
  lock) cmd_lock ;;
  unlock) cmd_unlock ;;
  status) cmd_status ;;
  *) echo "Usage: $0 {lock|unlock|status}"; exit 1 ;;
esac
