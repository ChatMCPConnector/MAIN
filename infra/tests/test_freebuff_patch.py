"""Tests fuer infra/scripts/freebuff_patch.py — die Update-Festigkeit der Patches.

Worum es hier geht: das native freebuff-Binary wird vom npm-Launcher bei jedem
Update ungefragt ersetzt, und die vier Bedien-Patches (Mausrad-Scroll,
Pfeil-Scroll, Wortgrenzen, Entf in /history) liegen als Bytes in genau dieser
Datei. Am 2026-10-02 hat ein Update sie restlos geloescht — der Nutzer hat es
zuerst an der Bedienung gemerkt, nicht an einer Meldung.

Deshalb wird hier **nicht** gegen das echte 136-MB-Binary getestet, sondern
gegen ein Bundle-Fixture, das strukturell gleich ist und **absichtlich andere
Bezeichner** traegt als das echte: der Minifier hat `LGA`/`_GA` (0.0.204) in
`iKA`/`yKA` (0.2.12) umbenannt, und genau daran ist `patch_word_boundary`
live gestorben ("0 Treffer fuer Muster"). Ein Test mit den echten Namen wuerde
den naechsten Rename nicht fangen — der Fixture-Bezeichner ist der Test.

Der zweite Punkt ist das Erkennen des eigenen Zustands: "bereits gepatcht" muss
strukturell erkannt werden. Der erste Wurf erkannte es am Fusszeilentext
`Del / Ctrl+D to remove`, den es in 0.2.12 nicht gibt — der Patch war drauf und
wurde beim zweiten Lauf trotzdem als "unangetastet" gemeldet. Der
Idempotenz-Test (zweimal patchen) faengt genau diese Klasse.
"""

import importlib.util
import os
import re
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "freebuff_patch.py"


def _load():
    """Laedt das Skript als Modul — der Dateiname hat einen Bindestrich und ist
    darueber nicht importierbar."""
    spec = importlib.util.spec_from_file_location("freebuff_patch", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fp = _load()


# --- Fixture: ein Bundle mit anderen Bezeichnern als das echte ------------------
#
# Scroll-Schrittweite: `Math.floor(G*qP)` neben `viewport.height`, `qP=0.8`.
SCROLL = b"let G=H.viewport.height,v=Math.floor(G*qP);qP=0.8;"
# history-up/down -> onScrollUp/Down. Die Actions heissen hier `wQ`/`xQ`.
ARROW = (
    b'case"slash-menu-select":return wQ.onSlashMenuSelect(),!0;'
    b'case"history-up":return wQ.onHistoryUp(),!0;'
    b'case"history-down":return wQ.onHistoryDown(),!0;'
    b'case"toggle-agent-mode":return wQ.onToggleAgentMode(),!0;'
)
# Wort-Bewegung: `zzQ` = word-backward, `aaQ` = word-forward (echt: iKA/yKA).
WORD = (
    b"function zzQ(H,A){let $=Math.max(0,Math.min(A,H.length));"
    b"while($>0&&/\\s/.test(H[$-1]))$--;while($>0&&!/\\s/.test(H[$-1]))$--;return $}"
    b"function aaQ(H,A){let $=Math.max(0,Math.min(A,H.length));"
    b"while($<H.length&&!/\\s/.test(H[$]))$++;while($<H.length&&/\\s/.test(H[$]))$++;return $}"
)
# History-Komponente. Die Bezeichner sind 1-2 Zeichen lang, weil der Minifier
# so vergibt — und weil der Patch **in die vorhandene Byte-Lage passen muss**
# (das Bundle haengt an Fixed Offsets). Die Namen sind andere als im echten
# Bundle (dort `C,p,S,F,Y,h,A,qD,ht,b`), damit ein Test mit echten Namen nicht
# einen Rename als "passt" meldet.
HISTORY = (
    b"yA=iA.useCallback((b)=>{t(b.id)},[t]),dl=iA.useCallback((b)=>{t(b.id)},[t]),"
    b"onKey=iA.useCallback((b)=>{"
    b'if(b.name==="escape"){if(c.length>0)g("");else z();return!0}'
    b'if(b.name==="up")return T((s)=>Math.max(0,s-1)),!0;'
    b'if(b.name==="down"){let t=Math.min(M.length,ht.MAX_RENDERED_CHATS)-1;'
    b"return T((s)=>Math.min(t,s+1)),!0}"
    b'let rv=b.name==="right"&&!b.ctrl&&!b.meta&&!b.option&&!b.shift;'
    b"if(iE(b)||rv){let t=M[J];if(t)oE(t.id);return!0}"
    b'if(b.name==="c"&&b.ctrl)return z(),!0;'
    b"return!1},[c,g,T,M,J,oE,z]),"
)
FOOTER = b"Click [\\xD7] to remove"


def bundle() -> bytes:
    """Ein Stueck Bundle mit allen vier Patch-Stellen, ungepatcht."""
    return b"\x00ELF-fake\x00" + SCROLL + ARROW + WORD + HISTORY + FOOTER + b"\x00trailer"


# --- Die vier Patches ----------------------------------------------------------
def test_alle_vier_werden_erkannt_und_angewandt():
    data = bundle()
    out, results = fp.apply_patches(data)
    assert [r.name for r in results] == ["scroll_step", "arrow_scroll", "word_boundary",
                                         "history_delete"]
    assert all(r.status == "applied" for r in results), [r.status for r in results]
    assert len(out) == len(data), "Bundle ist an Fixed Offsets verlinkt: Laenge muss gleich bleiben"


def test_idempotenz_zweiter_lauf_meldet_alles_als_already():
    """Der Test, der den Footer-Text-Bug gefangen haette: nach einem Patch muss der
    naechste Lauf 'schon gepatcht' sagen und die Bytes unveraendert lassen."""
    once, _ = fp.apply_patches(bundle())
    twice, results = fp.apply_patches(once)
    assert all(r.status == "already" for r in results), [(r.name, r.status) for r in results]
    assert twice == once


def test_paedagogisch_erwartete_texte_sitzen_drin():
    out, _ = fp.apply_patches(bundle())
    assert b"qP=0.5" in out                      # halbe Seite statt 80 %
    assert b"onScrollUp()" in out and b"onHistoryUp()" not in out
    assert b'.ctrl&&(b==="d"' not in out          # Struktur, nicht Text
    assert b'==="delete"' in out                  # Entf in /history
    assert b"Del / Ctrl+D to remove" in out       # Fusszeilenhinweis (Bonus)
    # Wortgrenzen: die zweite Schleife ist weg, die Flag-Variable da
    assert b"while($>0&&!/\\s/.test(H[$-1]))$--;" not in out
    assert b"===/\\s/.test" in out


def test_fehlende_struktur_wird_gemeldet_nicht_geraten():
    """Kein Muster -> unangetastet. Ein still falsch gepatchtes Bundle waere
    schlimmer als ein unveraendertes: es startet nicht mehr."""
    for r in fp.apply_patches(b"nur ein unbekanntes bundle")[1]:
        assert r.status == "unrecognized", r.name
    data = bundle().replace(WORD, b"function zzQ(H,A){return 0}")
    out, results = fp.apply_patches(data)
    word = next(r for r in results if r.name == "word_boundary")
    assert word.status == "unrecognized"
    assert b"function zzQ(H,A){return 0}" in out, "unbekannte Stelle unangetastet"


def test_zu_langer_ersatztext_wird_gemeldet_nicht_geschnitten():
    """Der History-Patch muss in die vorhandene Byte-Lage passen (Fixed Offsets).

    Passiert der neue Code nicht hinein, gibt es kein Padding — dann lieber
    "error" melden und die Datei unveraendert lassen, als sie zu zerlegen.
    """
    assert fp.fit_replacement(b"ab", b"abcd") is None
    assert fp.fit_replacement(b"abcd", b"ab") == b"ab  "
    data = bundle().replace(b"dl=iA.", b"deleteChatAction=iA.").replace(
        b"onKey=iA.", b"onKeyInterceptOfTheHistoryDialog=iA."
    )
    out, results = fp.apply_patches(data)
    hist = next(r for r in results if r.name == "history_delete")
    assert hist.status == "error", hist.detail
    assert b"onKeyInterceptOfTheHistoryDialog" in out, "unveraendert gelassen"


def test_zwei_stellen_werden_nicht_vermutet():
    data = bundle() + ARROW
    out, results = fp.apply_patches(data)
    arrow = next(r for r in results if r.name == "arrow_scroll")
    assert arrow.status == "unrecognized", "zwei Treffer heissen: raten waere blind"
    assert out.count(b"onScrollUp()") == 0


def test_generierte_bezeichner_keilen_nicht():
    """Der History-Patch erfindet zwei Bezeichner (`k` und `s`).

    Sind die im Bundle schon belegt, entstehen Two-Bindings-Declarationen und
    der Handler benutzt die falsche Variable — der Patch muss sich darum freie
    Namen aus dem Minifier-Alphabet suchen. `k` und `s` werden hier auf `cancel`
    und `items` gelegt: beide Stellen liegen *im* Muster, ohne es zu zerreissen
    (ein freistehendes `let k=1` davor wuerde den Match zerstoeren und damit
    nichts ueber das Verhalten testen).
    """
    data = bundle()
    for alt, neu in (
        (b"else z();", b"else k();"),
        (b"return z(),!0", b"return k(),!0"),
        (b"Math.min(M.length,", b"Math.min(s.length,"),
        (b"let t=M[J];", b"let t=s[J];"),
        (b"T,M,J,oE,z])", b"T,s,J,oE,k])"),  # Dep-Array zuletzt: enthaelt z und M
    ):
        assert alt in data, f"Fixture-Stelle fehlt: {alt!r}"
        data = data.replace(alt, neu)
    out, results = fp.apply_patches(data)
    hist = next(r for r in results if r.name == "history_delete")
    assert hist.status == "applied", hist.detail
    kopf = re.search(rb"let (\w)=b\.name,(\w)=\w+\[\w+\]", out)
    assert kopf, "generierter Handler-Kopf fehlt"
    assert kopf.group(1) not in (b"k", b"s") and kopf.group(2) not in (b"k", b"s")
    assert b'==="delete"' in out


# --- Datei-Ebene: Stamp, Status, Cleanup ---------------------------------------
def _fake_binary(tmp_path: pathlib.Path, rc: int = 0) -> pathlib.Path:
    """Binary-Ersatz mit allen Patch-Stellen, aber startbar wie das echte.

    `rc` steuert den Starttest: 0 = startet (wie 0.2.12 gepatcht), 1 = startet
    nicht (dann muss der Patcher das Backup zurueckspielen).
    """
    native = tmp_path / "manicode"
    native.mkdir(exist_ok=True)
    binp = native / "freebuff"
    binp.write_bytes(b"#!/bin/sh\nexit %d\n" % rc + bundle())
    binp.chmod(0o755)
    return binp


def test_patch_binary_schreibt_stamp_und_status(tmp_path):
    binp = _fake_binary(tmp_path)
    results, ok = fp.patch_binary(binp)
    assert ok
    assert fp.stamp_matches(binp, tmp_path / "manicode" / fp.STAMP_NAME)
    status = (tmp_path / "manicode" / fp.STAMP_NAME.replace(fp.STAMP_NAME, fp.STATUS_NAME)).read_text()
    assert "binary_start=ok" in status and "patched_at=" in status
    assert (tmp_path / "manicode" / fp.BACKUP_NAME).exists(), "Backup des Originals"


def test_ensure_patcht_nur_wenn_sich_das_binary_aendert(tmp_path):
    binp = _fake_binary(tmp_path)
    stamp = tmp_path / "manicode" / fp.STAMP_NAME
    assert fp.main(["--native-dir", str(tmp_path / "manicode"), "--ensure", "--quiet"]) == 0
    assert stamp.exists()
    mtime = binp.stat().st_mtime_ns

    # Unveraendert: der Fast-Path darf die Datei nicht einmal anfassen.
    assert fp.main(["--native-dir", str(tmp_path / "manicode"), "--ensure", "--quiet"]) == 0
    assert binp.stat().st_mtime_ns == mtime

    # Auto-Update: neue Datei mit gleicher Groesse, andere mtime. Der Stamp
    # passt nicht mehr -> der Patcher muss die vier Muster neu pruefen.
    os.utime(binp, (0, 0))
    assert not fp.stamp_matches(binp, stamp), "mtime geaendert heisst Stamp veraltet"
    assert fp.main(["--native-dir", str(tmp_path / "manicode"), "--ensure", "--quiet"]) == 0
    assert fp.stamp_matches(binp, stamp), "--ensure hat nicht neu geprueft"


def test_check_ist_read_only_und_meldet_fehlende_patches(tmp_path):
    binp = _fake_binary(tmp_path)
    native = str(tmp_path / "manicode")
    before = binp.read_bytes()
    rc = fp.main(["--native-dir", native, "--check", "--quiet"])
    assert rc == 1, "ungepatchtes Binary: --check muss rot sein"
    assert binp.read_bytes() == before, "--check darf nie schreiben"
    assert not (tmp_path / "manicode" / fp.STAMP_NAME).exists()

    fp.patch_binary(binp, verify=False)
    assert fp.main(["--native-dir", native, "--check", "--quiet"]) == 0


def test_kaputtes_binary_holt_backup_zurueck(tmp_path):
    binp = _fake_binary(tmp_path, rc=1)
    original = binp.read_bytes()
    results, ok = fp.patch_binary(binp)
    assert not ok
    assert binp.read_bytes() == original, "Backup muss zurueckgespielt sein"
    assert any(r.name == fp.START_CHECK and r.status == "error" for r in results)


def test_fehlendes_binary_ist_exit_2_kein_traceback(tmp_path, capsys):
    assert fp.main(["--native-dir", str(tmp_path / "leer")]) == 2
    assert "fehlt" in capsys.readouterr().err


def test_cleanup_raeumt_nur_alte_reste(tmp_path):
    native = tmp_path / "manicode"
    native.mkdir()
    alt = native / ".freebuff-download-temp-2258"
    alt.mkdir()
    (alt / "freebuff").write_bytes(b"x")
    neu = native / ".freebuff-download-temp-9999"
    neu.mkdir()
    (neu / "freebuff").write_bytes(b"x")
    part = native / ".freebuff-0.2.99-abc.tar.gz.part"
    part.write_bytes(b"x")
    os.utime(alt, (0, 0))
    os.utime(part, (0, 0))

    now = 1_000_000.0
    assert set(fp.cleanup_partial_downloads(native, now=now)) == {alt.name, part.name}
    assert neu.exists(), "ein laufender Download darf nicht weggeraeumt werden"


def test_cli_als_modul_laeuft(tmp_path):
    """So ruft der Wrapper es auf — inklusive Exit-Code, auf den er sich verlaesst."""
    _fake_binary(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--native-dir", str(tmp_path / "manicode"), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "history_delete=missing" in proc.stdout

# --- Randfaelle, die im Betrieb teuer wuerden ---------------------------------
def test_zwei_kandidaten_fuer_die_schrittweite_werden_nicht_geraten(tmp_path):
    """Auch `Math.floor` an zwei Stellen neben `viewport.height` heisst: raten
    waere blind, also unangetastet."""
    data = SCROLL + b"other=1;Math.floor(M*wP)*viewport.height;wP=0.8;"
    out, results = fp.apply_patches(data)
    step = next(r for r in results if r.name == "scroll_step")
    assert step.status == "unrecognized" and "Definitionsstellen" in step.detail
    assert out == data


def test_schrittweite_mit_anderer_laenge_wird_gemeldet():
    """`0.25` passt nicht in die 3 Bytes von `0.8` — melden, nicht schneiden."""
    _, res = fp.patch_scroll_step(SCROLL, want="0.25")
    assert res.status == "error" and "Laengendifferenz" in res.detail


def test_fehlende_delete_action_wird_gemeldet():
    data = bundle().replace(b"yA=iA.useCallback((b)=>{t(b.id)},[t]),", b"")
    out, results = fp.apply_patches(data)
    hist = next(r for r in results if r.name == "history_delete")
    assert hist.status == "unrecognized" and "Delete-Actions" in hist.detail
    assert b"dl=iA.useCallback((b)=>{t(b.id)},[t]),onKey=" in out, "Handler unangetastet"


def test_nicht_startbares_binary_meldet_statt_traceback(tmp_path):
    """Kein Exec-Bit: der Starttest wirft, der Patcher faengt es als Urteil."""
    binp = _fake_binary(tmp_path)
    binp.chmod(0o644)
    ok, detail = fp.verify_starts(binp)
    assert not ok and "PermissionError" in detail or not ok


def test_cleanup_ueberspringt_loeschfehler_statt_abzubrechen(monkeypatch, tmp_path):
    """Ein nicht loeschbarer Rest ist kein Grund abzubrechen — der naechste Start
    probiert es again. (Fehler per monkeypatch statt ueber Dateirechte: das
    Verhalten haengt sonst am Dateisystem und waere nicht ueberall gleich.)"""
    native = tmp_path / "manicode"
    native.mkdir()
    alt = native / ".freebuff-download-temp-1"
    alt.mkdir()
    os.utime(alt, (0, 0))

    def boom(*_args, **_kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(fp.shutil, "rmtree", boom)
    assert fp.cleanup_partial_downloads(native, now=1_000_000.0) == []
    assert alt.exists()


def test_ensure_meldet_im_fast_path_und_force_ignoriert_den_stamp(tmp_path, capsys):
    binp = _fake_binary(tmp_path)
    native = str(tmp_path / "manicode")
    assert fp.main(["--native-dir", native, "--ensure", "--quiet"]) == 0
    capsys.readouterr()
    assert fp.main(["--native-dir", native, "--ensure"]) == 0
    assert "patches=aktuell" in capsys.readouterr().out

    stamp = tmp_path / "manicode" / fp.STAMP_NAME
    stamp.write_text("kaputt\n", encoding="utf-8")
    assert fp.main(["--native-dir", native, "--force"]) == 0
    assert fp.stamp_matches(binp, stamp), "--force muss den Stamp neu setzen"


def test_ohne_verify_wird_nicht_gestartet(tmp_path):
    """`--no-verify` gibt den Starttest ab — der Patcher darf daran scheitern."""
    binp = _fake_binary(tmp_path, rc=1)
    results, ok = fp.patch_binary(binp, verify=False)
    assert ok and any(r.name == fp.START_CHECK and r.detail == "uebersprungen" for r in results)
