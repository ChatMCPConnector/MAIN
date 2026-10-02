#!/usr/bin/env python3
"""freebuff_patch.py: haelt die Byte-Patches des freebuff-Binaries am Leben.

Warum es diese Datei gibt
-------------------------
Das native freebuff-Binary (`~/.config/manicode/freebuff`, ~136 MB) enthaelt ein
Vue-Bundle. Vier Bedien-Eigenschaften sind dort hart verdrahtet und haben
weder Config, Flag noch Env:

  1. Scroll-Schrittweite: `Math.floor(X*VAR)` mit `VAR=0.8` neben
     `viewport.height` -> 0.5, also eine halbe Seite wie opencode.
  2. `history-up`/`history-down` rufen `onHistoryUp()`/`onHistoryDown()` ->
     umhaengt auf `onScrollUp()`/`onScrollDown()`. Ohne Mouse-Reporting
     schickt das Terminal das Mausrad als **dasselbe** Byte wie die Pfeiltaste
     (`ESC[A`/`ESC[B`); dieser Patch ist deshalb das, was das Rad ueberhaupt
     scrollen laesst, waehrend Menues (`/history`, Slash-Menue, Model-Picker) die
     Pfeiltaste vorher abfangen und nativ bedienbar bleiben.
  3. Wortgrenzen: `word-backward`/`word-forward` fressen Leerzeile UND Wort in
     einem Aufruf und springen ueber Zeilengrenzen -> stoppen an der ersten
     Klassengrenze (Whitespace / Wort).
  4. `/history` loescht eine Session nur per Mausklick `[x]`; die Maus ist
     bewusst aus -> Delete / Ctrl+D / Ctrl+X auf der fokussierten Session.

Die vier Punkte liegen als Bytes im Binary. Der npm-Launcher zieht aber selbst
das neueste Binary nach (`deferUpdatesUntilExit`, `binaryChecksums`) und legt
es unbemerkt ueber das gepatchte: **jedes Update loescht alle vier Patches**.
Live belegt 2026-10-02 (0.2.11, vom 1.10.): Mausrad tot, `Entf` in `/history`
tot, Pfeiltasten scrollten nur noch Menues.

Deshalb wird hier nicht mehr nur beim Codespace-Build gepatcht (das war
`freebuff-install.sh`), sondern **bei jedem Start von freebuff**, bevor die TUI
startet: `--ensure` vergleicht eine Stamp-Datei (Groesse + mtime + Format-
version) mit dem Binary und patcht nur, wenn sich etwas geaendert hat. Im
Normalfall kostet das ein `stat()`; nach einem Update einmalig ein Durchlauf
ueber 136 MB.

Update-Festigkeit ist zweiteilig, beides ist hier eingebaut:

  * **Muster statt Namen.** Der Minifier benennt um (0.0.204 `LGA`/`_GA` ->
     0.2.12 `iKA`/`yKA`); ein Patch auf feste Namen ist beim naechsten Update
     tot — das ist live passiert (`patch_word_boundary: 0 Treffer`). Alle Muster
     sind deshalb namenunabhaengig (Regex-Backreferences auf die selbst
     gefundenen Bezeichner) und zaehlen Treffer: != 1 heisst "Struktur nicht
     erkannt" -> unangetastet melden, nie raten. `infra/tests/
     test_freebuff_patch.py` pinnt das mit einem Fixture, dessen Bezeichner
     absichtlich anders heissen als im echten Bundle.
  * **Der eigene Zustand wird strukturell erkannt.** "Bereits gepatcht" heisst
     "Form des gepatchten Codes", nicht "steht da ein Nebentext". Genau daran
     ist der erste Wurf gescheitert: der Fusszeilentext `Del / Ctrl+D to
     remove` fehlt in 0.2.12, der Patch war drauf und wurde beim zweiten Lauf
     trotzdem als "unangetastet" gemeldet.

Sichtbarkeit: `--check` schreibt nichts (read-only, fuer
`verify-codespace.sh`), jeder schreibende Lauf hinterlaesst
`~/.config/manicode/freebuff-patch.status`. Exit 0 = alles gepatcht, 1 =
mindestens ein Patch passt nicht mehr (Struktur-Drift, muss ein Mensch ran),
2 = Binary fehlt/kaputt.

Nutzung:
    python3 infra/scripts/freebuff_patch.py --ensure   # beim Start (Wrapper)
    python3 infra/scripts/freebuff_patch.py --check    # read-only Diagnose
    python3 infra/scripts/freebuff_patch.py --force    # ohne Stamp-Vergleich

Wenn ein Patch nicht mehr passt (Struktur-Drift) — die Runbook-Zeilen, die ein
Agent braucht, stehen hier und nicht in vier anderen Dateien:
  1. `--check` laufen lassen. Die Zeile nennt Patch **und Grund**
     ("0 Treffer fuer word-backward", "2 Definitionsstellen (…)"): das ist die
     Fehlermeldung, an der sich die Diagnose aufhaengt, nicht der Exit-Code.
  2. **Nicht raten.** Erst belegen, was das neue Bundle wirklich schreibt: die
     Muster-Variable bzw. den Handler im Binary suchen und den Byte-Kontext
     ansehen (`grep -abo` auf `~/.config/manicode/freebuff` oder
     `strings | grep`), **vorher** die Muster zu aendern.
  3. Muster **namenunabhaengig** formulieren (Backreferences auf die selbst
     gefundenen Bezeichner) und die Zahl der erwarteten Treffer pruefen: != 1
     heisst "nicht eindeutig" -> unangetastet melden, nie raten. Neue
     Bezeichner im generierten Code ueber `fresh_name` holen, nie hart
     `k`/`s`/`s`.
  4. `STAMP_FORMAT` hochzaehlen (der wird in die Stamp-Datei geschrieben) und
     `infra/tests/test_freebuff_patch.py` erweitern: das Fixture traegt
     **absichtlich andere Bezeichner** als das echte Bundle, genau damit fängt
     der Test den nächsten Rename. Dann `make check` (ruff, mypy, pytest,
     Coverage-Floor 90 %, syntax-sh, shellcheck).
  5. `bash ./infra/scripts/freebuff-install.sh` — erzeugt den Wrapper neu und
     patcht mit `--force`. Danach `freebuff --version` **einmal starten**: der
     Starttest des Patchers ist der, der einen kaputten Bundle-Fang zurückholt.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Formatversion der Patch-Logik. Steht in der Stamp-Datei: wer die Muster hier
# aendert, invalidiert damit automatisch alle Stamps, statt still auf einem
# gecachten "gepatcht" sitzen zu bleiben.
STAMP_FORMAT = 1

DEFAULT_NATIVE_DIR = Path.home() / ".config" / "manicode"
BINARY_NAME = "freebuff"
BACKUP_NAME = "freebuff.orig"
STAMP_NAME = ".freebuff-patch-stamp"
STATUS_NAME = "freebuff-patch.status"

# Reste abgebrochener Auto-Update-Downloads. Nur aelter als `STALE_AFTER_S`
# anfassen: eine laufende Session darf ihren Download nicht verlieren.
STALE_AFTER_S = 1800

# Ergebnis-Name des Starttests nach dem Patchen (kein Patch, siehe `drifted`).
START_CHECK = "binary_start"


@dataclass
class PatchResult:
    """Ergebnis eines Einzel-Patches. `status`:

    * ``applied``     — Bytes wurden ersetzt
    * ``already``     — die gepatchte Form war schon da
    * ``unrecognized``— Muster passt nicht (Struktur-Drift); Datei unangetastet
    * ``error``       — Ersetzung waere laenger/kuerzer als das Original
    """

    name: str
    status: str
    detail: str = ""


# --------------------------------------------------------------------------------------
# Hilfsfunktionen fuer den Byte-Tausch
# --------------------------------------------------------------------------------------
_IDENT = rb"[A-Za-z0-9_$]{1,8}"


def fresh_name(taken: set[str], candidates: str = "suvwxyzAB") -> str:
    """Ersten Kandidaten liefern, der in `taken` noch nicht vorkommt.

    Die generierten Ersetzungen brauchen ein bis zwei *neue* Bezeichner (z. B.
    das `s` im Wortgrenzen-Patch, `k`/`s` im History-Patch). Der Minifier
    vergibt kurze Namen aus genau diesem Alphabet — ein harter Name wie `s`
    ist deshalb eine Lotterie und wuerde bei einem Update still falschen Code
    erzeugen (z. B. `let k=` kollidiert mit einem Parameter `k`).
    """
    for c in candidates:
        if c not in taken:
            return c
    raise ValueError("kein freier Bezeichner mehr")  # pragma: no cover


def fit_replacement(orig: bytes, repl: bytes) -> bytes | None:
    """`repl` auf exakt die Laenge von `orig` bringen (mit Leerzeichen auffuellen).

    Das Bundle ist an Fixed Offsets im ELF verlinkt, deshalb muss die Datei
    groessengleich bleiben. Ist der neue Text zu lang, gibt es kein Padding:
    dann lieber `unrecognized` melden als die Struktur zerlegen.
    """
    if len(repl) > len(orig):
        return None
    return repl + b" " * (len(orig) - len(repl))


# --------------------------------------------------------------------------------------
# Patch 1: Scroll-Schrittweite (0.8 -> 0.5)
# --------------------------------------------------------------------------------------
def patch_scroll_step(data: bytes, want: str = "0.5") -> tuple[bytes | None, PatchResult]:
    """`Math.floor(X*VAR)` neben `viewport.height`: die eine Definition von VAR ersetzen.

    Bewusst Mustersuche statt Namenssuche (`fOA` -> `$hA` -> `jzA` hat der
    Minifier in drei Versionen umbenannt). Gefordert ist genau eine
    Definitionsstelle, sonst bleibt die Datei unangetastet.
    """
    use = re.compile(rb"Math\.floor\(([A-Za-z0-9_$]{1,4})\*([A-Za-z0-9_$]{1,8})\)")
    cands = {
        m.group(2)
        for m in use.finditer(data)
        if b"viewport.height" in data[max(0, m.start() - 200) : m.start() + 200]
    }
    if not cands:
        return None, PatchResult(
            "scroll_step", "unrecognized", "kein Math.floor(X*VAR) neben viewport.height"
        )

    targets = [
        (m.start(1), m.group(1))
        for var in cands
        for m in re.finditer(re.escape(var) + rb"=(0\.[0-9]+)(?![0-9A-Za-z_$])", data)
    ]
    if len(targets) != 1:
        names = ", ".join(sorted(c.decode() for c in cands))
        return None, PatchResult(
            "scroll_step", "unrecognized", f"{len(targets)} Definitionsstellen ({names})"
        )

    off, old = targets[0]
    if old.decode() == want:
        return None, PatchResult("scroll_step", "already", f"Schrittweite bereits {want}")

    fitted = fit_replacement(data[off : off + len(old)], want.encode())
    if fitted is None:
        return None, PatchResult("scroll_step", "error", f"{old.decode()} -> {want}: Laengendifferenz")

    out = bytearray(data)
    out[off : off + len(old)] = fitted
    return bytes(out), PatchResult("scroll_step", "applied", f"{old.decode()} -> {want}")


# --------------------------------------------------------------------------------------
# Patch 2: history-up/down -> onScrollUp/Down (Mausrad)
# --------------------------------------------------------------------------------------
_ARROW_PATCHED = re.compile(
    rb'case"history-up":return\(' + _IDENT + rb"\.onScrollUp\(\),!0\);"
    rb'case"history-down":return\(' + _IDENT + rb"\.onScrollDown\(\),!0\);"
)
_ARROW_ORIG = re.compile(
    rb'case"history-up":return (' + _IDENT + rb")\.onHistoryUp\(\),!0;"
    rb'case"history-down":return \1\.onHistoryDown\(\),!0;'
)


def patch_arrow_scroll(data: bytes) -> tuple[bytes | None, PatchResult]:
    if _ARROW_PATCHED.search(data):
        return None, PatchResult("arrow_scroll", "already", "history-up/down -> onScrollUp/Down")
    matches = list(_ARROW_ORIG.finditer(data))
    if len(matches) != 1:
        return None, PatchResult(
            "arrow_scroll", "unrecognized", f"{len(matches)} Treffer fuer history-up/down"
        )
    m = matches[0]
    obj = m.group(1)
    repl = (
        b'case"history-up":return(' + obj + b".onScrollUp(),!0);"
        b'case"history-down":return(' + obj + b".onScrollDown(),!0);"
    )
    fitted = fit_replacement(m.group(), repl)
    if fitted is None:  # pragma: no cover - onScrollUp ist kuerzer als onHistoryUp
        return None, PatchResult("arrow_scroll", "error", "Ersetzung laenger als Original")
    out = bytearray(data)
    out[m.start() : m.end()] = fitted
    return bytes(out), PatchResult("arrow_scroll", "applied", "history-up/down -> onScrollUp/Down")


# --------------------------------------------------------------------------------------
# Patch 3: Wortgrenzen (Strg+Links/Rechts, Strg+Backspace)
# --------------------------------------------------------------------------------------
# Whitespace- und Wortschritt in EINER Schleife fressen Leerzeile und Wort
# zusammen. Die gepatchte Form merkt sich die Klasse des Zeichens VOR der
# Position (`s`) und laeuft nur, solange die Klasse gleich bleibt — damit
# stoppt `Strg+Links` am Zeilenende und frisst keine Folgezeile mit.
_WORD_BODY = (
    rb"function (?P<fn>" + _IDENT + rb")\((?P<str>" + _IDENT + rb"),(?P<pos>" + _IDENT + rb")\)\{"
    rb"let (?P<i>" + _IDENT + rb")=Math\.max\(0,Math\.min\((?P=pos),(?P=str)\.length\)\);"
    rb"while\((?P=i)>0&&/\\s/\.test\((?P=str)\[(?P=i)-1\]\)\)(?P=i)--;"
    rb"while\((?P=i)>0&&!/\\s/\.test\((?P=str)\[(?P=i)-1\]\)\)(?P=i)--;"
    rb"return (?P=i)\}"
)
_WORD_BODY_FWD = (
    rb"function (?P<fn>" + _IDENT + rb")\((?P<str>" + _IDENT + rb"),(?P<pos>" + _IDENT + rb")\)\{"
    rb"let (?P<i>" + _IDENT + rb")=Math\.max\(0,Math\.min\((?P=pos),(?P=str)\.length\)\);"
    rb"while\((?P=i)<(?P=str)\.length&&!/\\s/\.test\((?P=str)\[(?P=i)\]\)\)(?P=i)\+\+;"
    rb"while\((?P=i)<(?P=str)\.length&&/\\s/\.test\((?P=str)\[(?P=i)\]\)\)(?P=i)\+\+;"
    rb"return (?P=i)\}"
)
_WORD_PATCHED_BWD = re.compile(
    rb"let (?P<i>" + _IDENT + rb")=Math\.max\(0,Math\.min\((?P<pos>" + _IDENT
    + rb"),(?P<str>" + _IDENT + rb")\.length\)\),(?P<s>" + _IDENT + rb")=(?P=i)>0&&/\\s/\.test"
)
_WORD_PATCHED_FWD = re.compile(
    rb"let (?P<i>" + _IDENT + rb")=Math\.max\(0,Math\.min\((?P<pos>" + _IDENT
    + rb"),(?P<str>" + _IDENT + rb")\.length\)\),(?P<s>" + _IDENT + rb")=(?P=i)<(?P=str)\.length&&/\\s/\.test"
)


def _patch_word_function(data: bytes, pattern: re.Pattern[bytes], backward: bool) -> tuple[bytes, PatchResult]:
    matches = list(pattern.finditer(data))
    if len(matches) != 1:
        direction = "word-backward" if backward else "word-forward"
        return data, PatchResult(
            "word_boundary", "unrecognized", f"{len(matches)} Treffer fuer {direction}"
        )
    m = matches[0]
    g = {k: v.decode("latin1") for k, v in m.groupdict().items()}
    taken = set(g.values())
    flag = fresh_name(taken)
    if backward:
        body = (
            f"let {g['i']}=Math.max(0,Math.min({g['pos']},{g['str']}.length)),"
            f"{flag}={g['i']}>0&&/\\s/.test({g['str']}[{g['i']}-1]);"
            f"while({g['i']}>0&&{flag}===/\\s/.test({g['str']}[{g['i']}-1])){g['i']}--;"
            f"return {g['i']};"
        )
    else:
        body = (
            f"let {g['i']}=Math.max(0,Math.min({g['pos']},{g['str']}.length)),"
            f"{flag}={g['i']}<{g['str']}.length&&/\\s/.test({g['str']}[{g['i']}]);"
            f"while({g['i']}<{g['str']}.length&&{flag}===/\\s/.test({g['str']}[{g['i']}])){g['i']}++;"
            f"return {g['i']};"
        )
    repl = f"function {g['fn']}({g['str']},{g['pos']}){{{body}}}"
    fitted = fit_replacement(m.group(), repl.encode("latin1"))
    if fitted is None:  # pragma: no cover - Flag-Variable wiegt die zweite Schleife auf
        return data, PatchResult("word_boundary", "error", "Ersetzung laenger als Original")
    out = bytearray(data)
    out[m.start() : m.end()] = fitted
    return bytes(out), PatchResult("word_boundary", "applied", "saubere Wort-/Zeilengrenzen")


def patch_word_boundary(data: bytes) -> tuple[bytes | None, PatchResult]:
    if _WORD_PATCHED_BWD.search(data) and _WORD_PATCHED_FWD.search(data):
        return None, PatchResult("word_boundary", "already", "Wort-/Zeilengrenzen sauber")
    out, res_bwd = _patch_word_function(data, re.compile(_WORD_BODY, re.S), True)
    out, res_fwd = _patch_word_function(out, re.compile(_WORD_BODY_FWD, re.S), False)
    if res_bwd.status != "applied" and res_fwd.status != "applied":
        return None, PatchResult("word_boundary", res_bwd.status, f"{res_bwd.detail}; {res_fwd.detail}")
    detail = "; ".join(r.detail for r in (res_bwd, res_fwd) if r.status == "applied")
    return out, PatchResult("word_boundary", "applied", detail)


# --------------------------------------------------------------------------------------
# Patch 4: Session loeschen in /history (Entf / Ctrl+D / Ctrl+X)
# --------------------------------------------------------------------------------------
# Der OnKeyIntercept-Handler der History-Komponente, komplett ueber die
# benutzten Bezeichner beschrieben — schon 0.0.204-namensunabhaengig, deshalb
# hier unveraendert uebernommen.
_HISTORY_ORIG = re.compile(
    rb'(?P<fn>[a-zA-Z0-9_$]+)=(?P<react>[a-zA-Z0-9_$]+)\.useCallback\(\((?P<key>[a-zA-Z0-9_$]+)\)=>\{'
    rb'if\((?P=key)\.name==="escape"\)\{if\((?P<query>[a-zA-Z0-9_$]+)\.length>0\)(?P<setQuery>[a-zA-Z0-9_$]+)\(""\);else (?P<cancel>[a-zA-Z0-9_$]+)\(\);return!0\}'
    rb'if\((?P=key)\.name==="up"\)return (?P<setIndex>[a-zA-Z0-9_$]+)\(\(([a-zA-Z0-9_$]+)\)=>Math\.max\(0,[a-zA-Z0-9_$]+-1\)\),!0;'
    rb'if\((?P=key)\.name==="down"\)\{let [a-zA-Z0-9_$]+=Math\.min\((?P<items>[a-zA-Z0-9_$]+)\.length,(?P<consts>[a-zA-Z0-9_$]+)\.MAX_RENDERED_CHATS\)-1;return (?P=setIndex)\(\([a-zA-Z0-9_$]+\)=>Math\.min\([a-zA-Z0-9_$]+,[a-zA-Z0-9_$]+\+1\)\),!0\}'
    rb'let (?P<rightVar>[a-zA-Z0-9_$]+)=(?P=key)\.name==="right"&&!(?P=key)\.ctrl&&!(?P=key)\.meta&&!(?P=key)\.option&&!(?P=key)\.shift;'
    rb'if\((?P<isEnter>[a-zA-Z0-9_$]+)\((?P=key)\)\|\|(?P=rightVar)\)\{let [a-zA-Z0-9_$]+=(?P=items)\[(?P<index>[a-zA-Z0-9_$]+)\];if\([a-zA-Z0-9_$]+\)(?P<openChat>[a-zA-Z0-9_$]+)\([a-zA-Z0-9_$]+\.id\);return!0\}'
    rb'if\((?P=key)\.name==="c"&&(?P=key)\.ctrl\)return (?P=cancel)\(\),!0;'
    rb'return!1\},\[(?P=query),(?P=setQuery),(?P=setIndex),(?P=items),(?P=index),(?P=openChat),(?P=cancel)\]\)'
)
# Die Delete-Action (`fn(item.id)`) wird VOR dem Handler definiert; es gibt
# mindestens zwei solche Callbacks, die loeschende ist die zweite.
_HISTORY_DELETE_BEFORE = re.compile(
    rb'(?P<action>[a-zA-Z0-9_$]+)=(?P<react>[a-zA-Z0-9_$]+)\.useCallback\(\(([a-zA-Z0-9_$]+)\)=>\{(?P<fn>[a-zA-Z0-9_$]+)\([a-zA-Z0-9_$]+\.id\)\},\[(?P=fn)\]\),'
)
_HISTORY_PATCHED = re.compile(
    rb'==="delete"\|\|[a-zA-Z0-9_$]{1,8}\.ctrl&&\([a-zA-Z0-9_$]{1,8}==="d"'
    rb'\|\|[a-zA-Z0-9_$]{1,8}==="x"\)'
)
# Nebentext am Fuss der History-Liste. Nur ein Bonus (sichtbarer Hinweis auf
# Tastatur-LOESCHEN statt Mausklick) — und bewusst NICHT als Erkennung
# "bereits gepatcht" benutzt: der Text fehlt in 0.2.12, der Patch nicht.
_HISTORY_FOOTER_ORIG = b"Click [\\xD7] to remove"
_HISTORY_FOOTER_REPL = b"Del / Ctrl+D to remove"


def patch_history_delete(data: bytes) -> tuple[bytes | None, PatchResult]:
    detail = "Delete/Ctrl+D/Ctrl+X loescht Session"
    if _HISTORY_PATCHED.search(data):
        return None, PatchResult("history_delete", "already", detail)

    match = _HISTORY_ORIG.search(data)
    if not match:
        return None, PatchResult("history_delete", "unrecognized", "Handler-Muster nicht gefunden")
    before = list(_HISTORY_DELETE_BEFORE.finditer(data[max(0, match.start() - 150) : match.start()]))
    if len(before) < 2:
        return None, PatchResult(
            "history_delete", "unrecognized", f"{len(before)} Delete-Actions davor (2 noetig)"
        )

    g = {k: v.decode("latin1") for k, v in match.groupdict().items()}
    taken = set(g.values())
    kvar = fresh_name(taken, "ksuvwxyzAB")
    svar = fresh_name(taken | {kvar}, "suvwxyzAB")
    g["deleteAction"] = before[1].group("action").decode("latin1")

    base = (
        f"{g['fn']}={g['react']}.useCallback(({g['key']})=>"
        f"{{let {kvar}={g['key']}.name,{svar}={g['items']}[{g['index']}];"
        f"if({kvar}===\"escape\")return {g['query']}?{g['setQuery']}(\"\"):{g['cancel']}(),!0;"
        f"if({kvar}===\"up\")return {g['setIndex']}({svar}=>Math.max(0,{svar}-1)),!0;"
        f"if({kvar}===\"down\")return {g['setIndex']}({svar}=>Math.min(Math.min({g['items']}.length,"
        f"{g['consts']}.MAX_RENDERED_CHATS)-1,{svar}+1)),!0;"
        f"if({svar}&&({kvar}===\"delete\"||{g['key']}.ctrl&&({kvar}===\"d\"||{kvar}===\"x\")))"
        f"return {g['deleteAction']}({svar}),!0;"
        f"if({g['isEnter']}({g['key']})||{kvar}===\"right\"&&!{g['key']}.meta&&!{g['key']}.option&&!{g['key']}.shift)"
        f"return {svar}&&{g['openChat']}({svar}.id),!0;"
        f"if({g['key']}.ctrl&&{kvar}===\"c\")return {g['cancel']}(),!0;"
        f"return!1"
    )
    suffix = (
        f"}}}},[{g['query']},{g['setQuery']},{g['setIndex']},{g['items']},"
        f"{g['index']},{g['openChat']},{g['cancel']}])"
    )
    fitted = fit_replacement(match.group(), (base + suffix).encode("latin1"))
    if fitted is None:
        return None, PatchResult("history_delete", "error", "Code laenger als Original")

    out = bytearray(data)
    out[match.start() : match.end()] = fitted
    if bytes(out).count(_HISTORY_FOOTER_ORIG) == 1:
        idx = bytes(out).find(_HISTORY_FOOTER_ORIG)
        footer = fit_replacement(_HISTORY_FOOTER_ORIG, _HISTORY_FOOTER_REPL)
        if footer is not None:
            out[idx : idx + len(_HISTORY_FOOTER_ORIG)] = footer
            detail += " (Fusszeile angepasst)"
    return bytes(out), PatchResult("history_delete", "applied", detail)


PatchFn = Callable[[bytes, str], "tuple[bytes | None, PatchResult]"]


def _without_step(fn: Callable[[bytes], "tuple[bytes | None, PatchResult]"]) -> PatchFn:
    """Ein Patcher ohne Schrittweiten-Argument auf die gemeinsame Signatur heben."""

    def run(data: bytes, _step: str) -> "tuple[bytes | None, PatchResult]":
        return fn(data)

    return run


PATCHERS: tuple[PatchFn, ...] = (
    patch_scroll_step,
    _without_step(patch_arrow_scroll),
    _without_step(patch_word_boundary),
    _without_step(patch_history_delete),
)


def apply_patches(data: bytes, scroll_step: str = "0.5") -> tuple[bytes, list[PatchResult]]:
    """Alle vier Patches nacheinander anwenden. Ergebnis muss gROSSENGLEICH sein."""
    out = data
    results: list[PatchResult] = []
    for patcher in PATCHERS:
        new, res = patcher(out, scroll_step)
        results.append(res)
        if new is not None:
            out = new
    if len(out) != len(data):
        raise AssertionError("Patch hat die Dateigroesse veraendert")
    return out, results


# --------------------------------------------------------------------------------------
# Datei-Ebene
# --------------------------------------------------------------------------------------
def stamp_text(path: Path) -> str:
    st = path.stat()
    return f"{STAMP_FORMAT} {st.st_size} {st.st_mtime_ns}"


def stamp_matches(path: Path, stamp: Path) -> bool:
    """Schneller Weg (< 1 ms): passt die Stamp-Datei zum Binary?

    Nach einem Auto-Update ist das Binary eine neue Datei: andere Groesse und
    andere mtime. Genau daran erkennt der Wrapper, dass er patchen muss.
    """
    try:
        return stamp.read_text(encoding="utf-8").strip() == stamp_text(path)
    except OSError:
        return False


def write_status(native_dir: Path, results: list[PatchResult], extra: dict[str, str]) -> Path:
    status = native_dir / STATUS_NAME
    lines = [f"{k}={v}" for k, v in extra.items()]
    lines += [f"{r.name}={r.status} {r.detail}".rstrip() for r in results]
    status.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return status


def verify_starts(path: Path, timeout: int = 60) -> tuple[bool, str]:
    """Startet das (gepatchte) Binary ueberhaupt? `freebuff --version` genuegt.

    Ein Byte-Patch an der falschen Stelle laesst das Bundle syntaktisch kaputt
    laufen; ohne diese Pruefung faellt das erst auf, wenn der Nutzer die TUI
    startet. Bei Fehlschlag spielt der Patcher das Backup zurueck.
    """
    try:
        proc = subprocess.run(
            [str(path), "--version"], capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    out = proc.stdout.decode(errors="replace").strip().splitlines()
    return proc.returncode == 0, (out[-1] if out else f"rc={proc.returncode}")


def cleanup_partial_downloads(native_dir: Path, now: float | None = None) -> list[str]:
    """Reste abgebrochener Auto-Update-Downloads loeschen (nur alte).

    Am 2026-10-02 lagen drei `.freebuff-download-temp-*` mit je 133 MB in
    $HOME — ein abgebrochener Download pro Startversuch. Nur Eintraege, die
    aelter als `STALE_AFTER_S` sind, werden angefasst: eine laufende Session
    darf ihren laufenden Download nicht wegraeumen.
    """
    now = time.time() if now is None else now
    removed: list[str] = []
    if not native_dir.is_dir():
        return removed
    for entry in sorted(native_dir.iterdir()):
        if not (entry.name.startswith(".freebuff-download-temp-")
                or (entry.name.startswith(".freebuff-") and entry.name.endswith(".tar.gz.part"))):
            continue
        try:
            if now - entry.stat().st_mtime < STALE_AFTER_S:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
        except OSError:
            continue
        removed.append(entry.name)
    return removed


def patch_binary(
    binary: Path,
    native_dir: Path | None = None,
    scroll_step: str = "0.5",
    force: bool = False,
    verify: bool = True,
) -> tuple[list[PatchResult], bool]:
    """Alle Patches anwenden, Datei schreiben, Start pruefen, Stamp setzen.

    Gibt `(results, binary_starts)` zurueck. Schreibt nur, wenn sich etwas
    aendert; die Erkennung "schon gepatcht" sitzt in den Patchern selbst.
    """
    native_dir = native_dir or binary.parent
    stamp = native_dir / STAMP_NAME
    data = binary.read_bytes()
    new, results = apply_patches(data, scroll_step)

    changed = new != data
    if changed:
        if not (native_dir / BACKUP_NAME).exists():
            shutil.copy2(binary, native_dir / BACKUP_NAME)
        tmp = binary.with_suffix(binary.suffix + ".patched")
        with open(tmp, "wb") as fh:
            fh.write(new)
        os.chmod(tmp, 0o755)
        os.replace(tmp, binary)

    ok, version = (True, "uebersprungen")
    if verify and (changed or force):
        ok, version = verify_starts(binary)
        if not ok:
            backup = native_dir / BACKUP_NAME
            if backup.exists():
                shutil.copy2(backup, binary)
                os.chmod(binary, 0o755)

    if ok:
        stamp.write_text(stamp_text(binary) + "\n", encoding="utf-8")
    results.append(PatchResult(START_CHECK, "ok" if ok else "error", version))
    write_status(
        native_dir,
        results,
        {
            "binary": str(binary),
            "size": str(binary.stat().st_size),
            "stamp_format": str(STAMP_FORMAT),
            "patched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    return results, ok


def report(results: list[PatchResult], quiet: bool) -> None:
    if quiet:
        return
    for r in results:
        line = f"{r.name}={r.status}"
        if r.detail:
            line += f" ({r.detail})"
        print(line)


def print_drift_hint() -> None:
    """Der Handweis bei Struktur-Drift — einmal formuliert, fuer jeden Aufrufer.

    `--check` ist die read-only Diagnose und damit der **erste** Schritt, den ein
    Agent macht; der Hinweis muss dort stehen, nicht nur im schreibenden Lauf
    (der folgt erst nach der Analyse). Ein Exit-Code allein sagt nichts.
    """
    print(
        "freebuff: mindestens ein Byte-Patch passt nicht mehr (Upstream hat die "
        "Bundle-Struktur geaendert). Das ist die Runbook-Zeile 'Wenn ein Patch nicht "
        "mehr passt' im Docstring von infra/scripts/freebuff_patch.py — NICHT durch "
        " blosses Neuinstallieren loesbar.",
        file=sys.stderr,
    )


def drifted(results: list[PatchResult]) -> bool:
    """Mindestens ein Patch sitzt nicht — Struktur-Drift, ein Mensch muss ran.

    `binary_start` ist kein Patch, sondern der Starttest danach; sein Urteil
    laeuft ueber den Exit-Code 2 und darf die Patch-Bewertung nicht verfaelschen.
    """
    return any(
        r.status not in ("applied", "already") for r in results if r.name != START_CHECK
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Byte-Patches des freebuff-Binaries")
    ap.add_argument("--native-dir", type=Path, default=DEFAULT_NATIVE_DIR)
    ap.add_argument("--binary", type=Path, default=None)
    ap.add_argument("--scroll-step", default="0.5")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--ensure", action="store_true", help="nur patchen, wenn sich das Binary aenderte")
    mode.add_argument("--check", action="store_true", help="read-only: nur melden, nie schreiben")
    mode.add_argument("--force", action="store_true", help="Stamp ignorieren, immer patchen")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="Starttest nach dem Patchen auslassen")
    args = ap.parse_args(argv)

    binary = args.binary or (args.native_dir / BINARY_NAME)
    if not binary.is_file():
        print(f"freebuff-Binary fehlt: {binary}", file=sys.stderr)
        print("  Einmal ausfuehren: bash ./infra/scripts/freebuff-install.sh", file=sys.stderr)
        return 2

    stamp = args.native_dir / STAMP_NAME
    if args.check:
        # Read-only: die Patcher laufen im Speicher, `applied` heisst hier
        # "fehlt noch im Binary" — ein Check, der "koennte ich patchen" sagt,
        # waere bei abgebrochenem Patcherlauf gruen und damit wertlos.
        _, results = apply_patches(binary.read_bytes(), args.scroll_step)
        results = [
            PatchResult(r.name, "missing" if r.status == "applied" else r.status, r.detail)
            for r in results
        ]
        report(results, args.quiet)
        if not all(r.status == "already" for r in results):
            print_drift_hint()
            return 1
        return 0

    if args.ensure and not args.force and stamp_matches(binary, stamp):
        if not args.quiet:
            print(f"patches=aktuell ({stamp_text(binary)})")
        cleanup_partial_downloads(args.native_dir)
        return 0

    results, ok = patch_binary(
        binary,
        native_dir=args.native_dir,
        scroll_step=args.scroll_step,
        force=args.force,
        verify=not args.no_verify,
    )
    cleanup_partial_downloads(args.native_dir)
    report(results, args.quiet)
    if not ok:
        print("freebuff-Binary startet nach dem Patchen nicht — Backup zurueckgespielt", file=sys.stderr)
        return 2
    if drifted(results):
        print_drift_hint()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())