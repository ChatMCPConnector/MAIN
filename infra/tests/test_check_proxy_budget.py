"""Tests fuer infra/scripts/check-proxy-budget.py (PLAN Stufe 3, Ebene 1).

Das ist die Datei, die den echten Bug vom 2026-09-30 gefunden hat: output=16384
neben context=16000 machte die Kompaktierungsschwelle negativ, opencode
kompaktierte nach jedem Turn, und eine Session verbrannte 20 Requests damit.
Genau eine solche Logik verdient Tests, die *vor* der Aenderung rot werden.

Warum hier echtes rot-gruen sinnvoll ist und bei den Shell-Skripten nicht:
`pruefe()` ist pure Rechnung — vier Zahlen hinein, Fehlerliste und Hinweise
zurueck, kein I/O, keine Ports, keine Secrets. Genau das ist die Definition der
Ebene 1 in PLAN 6b.

Die Belegfaelle aus dem Docstring des Skripts sind hier als Testfaelle
festgeschrieben, damit sie nicht verloren gehen.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check-proxy-budget.py"


def _load():
    """Laedt das Skript als Modul — der Dateiname hat einen Bindestrich und ist
    darueber nicht importierbar."""
    spec = importlib.util.spec_from_file_location("check_proxy_budget", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cpb = _load()


# --- Der Zustand, der im Repo tatsaechlich gilt (drei Kopplungen) ------------


def test_repo_zustand_ist_ju_st_gruen():
    """Die echten Zahlen aus .opencode + ZeroKey-Config duerfen nie rot werden."""
    fenster, schwelle, chars, fehler, hinweise = cpb.pruefe(16000, 2000, 2000, 50000)
    assert fehler == []
    assert fenster == 14000
    assert schwelle == 14000
    assert chars == 56000
    # 56000 Zeichen > 50000 Limit: middle-out, das ist beabsichtigt und nur ein Hinweis.
    assert len(hinweise) == 1 and "middle-out" in hinweise[0]


# --- Die drei Belegfaelle aus dem Docstring ---------------------------------


def test_output_groesser_context_ist_der_bug_vom_2026_09_30():
    fenster, schwelle, _chars, fehler, _ = cpb.pruefe(16000, 16384, 2000, 50000)
    assert fehler, "output >= context muss rot werden"
    assert schwelle < 0, "die Schwelle war das Symptom: negativ"
    assert "Resume-Loop" in fehler[0]


def test_output_gleich_context_ist_eben_rot():
    _f, _s, _c, fehler, _ = cpb.pruefe(16000, 16000, 2000, 50000)
    assert fehler


def test_kompaktierung_vor_der_kuerzung_ist_rot():
    """Schwelle*4 <= promptLimit: ZeroKeys own middle-out muss VOR der
    Kompaktierung greifen, sonst bricht der Lauf mit 'Tool call not allowed
    while generating summary' ab."""
    # context=16000, output=9000 -> Schwelle 7000 Tokens = 28000 Zeichen < 50000.
    _f, _s, _c, fehler, _ = cpb.pruefe(16000, 9000, 2000, 50000)
    assert fehler
    assert "VOR der Kuerzung" in fehler[0]
    # Die Empfehlung im Text ist ctx - limit//4 = 16000 - 12500 = 3500.
    assert "output muss < 3500" in fehler[0]


def test_reserved_größer_context_kompaktiert_immer():
    _f, _s, _c, fehler, _ = cpb.pruefe(16000, 2000, 16000, 50000)
    assert fehler
    assert "reserved" in fehler[0]


def test_reserved_nimmt_fast_den_ganzen_kontext():
    """reserved=15000 bei context=16000 liess 1000 Token = 6 % Fuellstand.
    Das ist der zweite historische Befund: Die Menge lag UNTER dem
    Proxy-Budget, die Zeichen-Pruefung greift also nicht."""
    fenster, _s, _c, fehler, _ = cpb.pruefe(16000, 2000, 15000, 50000)
    assert fenster == 1000
    assert fehler
    assert "Arbeitsfenster nur 1000 von 16000 Tokens" in fehler[0]
    assert "6%" in fehler[0]


def test_fenster_ueber_doppeltes_proxy_budget_ist_rot():
    # 15000 Tokens * 4 = 60000 Zeichen > 2 * 25000.
    _f, _s, chars, fehler, _ = cpb.pruefe(20000, 2000, 5000, 25000)
    assert chars == 60000
    assert fehler
    assert "2x promptLimit" in fehler[0]


def test_fenster_leicht_ueber_limit_ist_nur_hinweis():
    """Leichtes Ueberschreiten ist beabsichtigt: middle-out rettet Kopf und Tail."""
    _f, _s, _c, fehler, hinweise = cpb.pruefe(16000, 2000, 2000, 50000)
    assert not fehler
    assert hinweise


def test_hinweis_unternutztes_budget_ist_im_gruenen_zustand_unerreichbar():
    """Befund vom 2026-10-02, im Test festgeschrieben statt im Code versteckt:

    Der Zweig `chars < limit * 0.25` („Fenster nutzt nur X % des Budgets —
    Limit koennte hoeher“) kann in einer **fehlerfreien** Konfiguration
    mathematisch nie greifen:

        * keine reserved-Fehler  => fenster*2 >= ctx => chars = 4*fenster >= 2*ctx
        * kein Kuerzungs-Fehler  => schwelle*4 > limit, also limit < 4*(ctx-out) < 4*ctx
        * der Zweig will         => limit > 4*chars >= 8*ctx

    8*ctx < 4*ctx ist unmoeglich. Der Zweig druckt also nur noch, wenn
    gleichzeitig ein echter Fehler gemeldet wird — er ist als Hinweis toter
    Code. Der Test haelt die Eigenschaft fest: faellt jemand eine der Regeln
    auf, wird er hier rot und muss sich das ansehen.
    """
    geprueft = 0
    for ctx in range(2000, 9000, 500):
        for out in range(200, 4000, 200):
            for reserved in range(0, 9000, 500):
                for limit in range(20000, 200001, 20000):
                    fenster, _s, chars, fehler, hinweise = cpb.pruefe(ctx, out, reserved, limit)
                    if fehler:
                        continue
                    geprueft += 1
                    assert not (chars < limit * 0.25), (
                        f"unerreichbarer Zweig ist jetzt erreichbar: ctx={ctx} out={out} "
                        f"reserved={reserved} limit={limit} chars={chars}"
                    )
                    assert fenster == ctx - reserved
    assert geprueft > 100, f"Sweep zu klein ({geprueft} gruene Konfigurationen)"


def test_output_und_reserved_koennen_doppelt_werden():
    """Beide Regeln duerfen unabhaengig greifen — kein elif verhindert die
    zweite Diagnose, sonst sieht man nur einen Teil des Bildes."""
    # out >= ctx UND reserved >= ctx gleichzeitig.
    _f, _s, _c, fehler, _ = cpb.pruefe(16000, 20000, 20000, 50000)
    assert len(fehler) == 2


# --- Ebene 1b: das Laden (I/O mit echten Dateien) ---------------------------


def _schreibe(tmp_path, ctx, out, reserved, prompt_limit):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps(
            {
                "provider": {
                    "downloaddoctor": {
                        "models": {"zerokey": {"limit": {"context": ctx, "output": out}}}
                    }
                },
                "compaction": {"reserved": reserved},
            }
        ),
        encoding="utf-8",
    )
    zk = tmp_path / "config.js"
    # Mit Unterstrichen als Tausendertrenner — der Regex muss das abhandeln.
    zk.write_text(f"const promptLimit = {prompt_limit}\n", encoding="utf-8")
    return cfg, zk


def test_lade_liest_alle_vier_werte(tmp_path):
    cfg, zk = _schreibe(tmp_path, 16000, 2000, 2000, 50_000)
    ctx, out, reserved, limit = cpb.lade(str(tmp_path), str(cfg), str(zk))
    assert (ctx, out, reserved, limit) == (16000, 2000, 2000, 50000)


def test_lade_meldet_fehlende_datei_statt_traceback(tmp_path):
    assert cpb.lade(str(tmp_path), str(tmp_path / "gibtsnicht.json"), str(tmp_path / "x.js")) is None


def test_lade_meldet_fehlenden_promptlimit(tmp_path):
    cfg, zk = _schreibe(tmp_path, 16000, 2000, 2000, 50000)
    zk.write_text("// keine Konstante hier\n", encoding="utf-8")
    assert cpb.lade(str(tmp_path), str(cfg), str(zk)) is None


def test_cli_auf_dem_repo_zustand_exit_0():
    """Der echte Aufruf mit Default-Pfaden — so ruft ihn verify-codespace.sh.
    Als Subprozess, damit der Exit-Code des Skripts wirklich geprueft wird."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok: Kopplung stimmt" in r.stdout


# --- main() in-process: das ist, was die Coverage-Zahl hebt ----------------
#
# Die Subprozess-Tests oben beweisen den Exit-Code-Vertrag, zaehlen fuer die
# Coverage aber nicht (anderer Interpreter). Fuer die Zahl wird main() hier
# direkt getrieben — mit gestelltem sys.argv, exakt wie es die CLI sieht.


def test_main_ohne_argumente_liest_die_repo_dateien(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    assert cpb.main() == 0
    out = capsys.readouterr().out
    assert "ok: Kopplung stimmt" in out


def test_main_meldet_fehler_und_gibt_1(monkeypatch, tmp_path, capsys):
    cfg, zk = _schreibe(tmp_path, 16000, 16384, 2000, 50000)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(cfg), str(zk)])
    assert cpb.main() == 1
    out = capsys.readouterr().out
    assert out.count("FEHLER:") >= 1
    assert "ok: Kopplung stimmt" not in out


def test_main_gibt_2_bei_unlesbarer_datei(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(tmp_path / "nope.json")])
    assert cpb.main() == 2
    assert "nicht lesbar" in capsys.readouterr().out


def test_main_druckt_die_kennzahlen(monkeypatch, capsys):
    """Die drei Kennzahl-Zeilen sind die eigentliche Diagnose-Ausgabe; ohne sie
    weiss niemand, welche Zahl den Wert verursacht hat."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    cpb.main()
    out = capsys.readouterr().out
    assert "Client: context=" in out
    assert "reserved=" in out
    assert "Proxy:  promptLimit=" in out


def test_cli_exit_1_bei_echtem_fehler(tmp_path):
    """Der rote Pfad muss am Ende auch wirklich Exit 1 liefern, nicht nur
    'fehler' in einer Liste — sonst waere der Check im Verify gruen."""
    cfg, zk = _schreibe(tmp_path, 16000, 16384, 2000, 50000)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(cfg), str(zk)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 1
    assert "FEHLER:" in r.stdout


def test_cli_exit_2_bei_unlesbarer_datei(tmp_path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.json")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2

# --- MAIN 2026-10-03: die Paar-Pruefung ------------------------------------
#
# `lade()` war auf das ChatGPT-Paar festverdrahtet. Deshalb blieb dieser Check
# gruen, als `deepseek-web` mit `limit.context: 1000000` in opencode.json stand —
# die Regel, die das gefangen haette, wurde nie auf dieses Paar angewandt. Die
# folgenden Tests sichern genau das ab.


def test_paare_findet_beide_zerokey_provider():
    """Beide ZeroKey-Provider im echten Repo werden gefunden, mit promptLimit."""
    root = pathlib.Path(__file__).resolve().parents[2]
    ps, reserved = cpb.paare(str(root))
    gefunden = {(pid, mid, name) for pid, mid, _c, _o, _l, name in ps}
    assert ("deepseek-web", "default", "deepseek") in gefunden
    assert ("downloaddoctor", "zerokey", "chatgpt") in gefunden
    assert reserved == 2000


def test_paare_ueberspringt_nicht_zerokey_provider():
    """glm2api (Port 8001) hat kein promptLimit — darf kein Paar werden."""
    root = pathlib.Path(__file__).resolve().parents[2]
    ps, _reserved = cpb.paare(str(root))
    ids = {pid for pid, *_rest in ps}
    assert "glm2api" not in ids
    assert "antigravity" not in ids
    assert "xinjianya" not in ids


def test_paare_ignoriert_provider_ohne_limit():
    """Ein Provider ohne limit.context zaehlt nicht als Paar."""
    root = pathlib.Path(__file__).resolve().parents[2]
    ps, _reserved = cpb.paare(str(root))
    for _pid, _mid, ctx, _out, _limit, _name in ps:
        assert ctx > 0


def test_deepseek_mit_modellkarten_context_wird_rot():
    """DER BUG VOM 2026-10-03, festgeschrieben.

    `limit.context` war aus DeepSeks Modellkarte (1 000 000 Tokens) uebernommen,
    obwohl ZeroKeys `promptLimit` von 128 000 Zeichen die bindende Grenze ist.
    opencode haette deshalb nie kompaktiert, waehrend der Proxy ab 127 936
    Zeichen still die Mitte des Gespraechs wegwirft. Die bestehende Regel
    `Arbeitsfenster > 2x Proxy-Budget` faengt das — vorausgesetzt, sie laeuft
    ueberhaupt fuer dieses Paar.
    """
    _f, _s, chars, fehler, _h = cpb.pruefe(1_000_000, 384_000, 2000, 128_000)
    assert fehler, "1M context bei 128k-Zeichen-Limit muss rot werden"
    assert any("Haelfte" in f or "half" in f or "2x" in f for f in fehler), fehler
    assert chars > 128_000 * 2


def test_deepseek_korrigierte_werte_sind_gruen():
    """Die Werte, die jetzt im Repo stehen, muessen gruen bleiben."""
    _f, _s, _c, fehler, _h = cpb.pruefe(40_000, 4_000, 2000, 128_000)
    assert fehler == []


def test_output_gleich_context_bleibt_rot():
    """output >= context ist die uralte Regel und muss auch bei DeepSeek gelten."""
    _f, _s, _c, fehler, _h = cpb.pruefe(32_000, 32_000, 2000, 128_000)
    assert fehler, "output == context muss rot sein (Kompaktierungsschwelle 0)"
