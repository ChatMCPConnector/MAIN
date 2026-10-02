"""Tests fuer infra/scripts/port-drift-check.py.

Ebene 1 aus PLAN 6b: reine Logik, kein I/O in der eigentlichen Entscheidung.
`labelled_ports`, `bound_ports` und `devcontainer_ports` lesen nur Text — also
genau die Sorte Funktion, die man ehrlich testen kann.

**Warum dieser Check Tests braucht und nicht nur einen Baseline-Eintrag:**
die erste Fassung erkannte `PORT=8001` (unquotiert), aber `PORT="7250"`
(quotiert) nicht. Der Negativtest „Label entfernen" lief deshalb durch, statt
anzuschlagen — der Check war gruen und haette Drift durchgelassen. Genau das
ist der Fehler, den Tests hier fangen: nicht der Ausgabe, sondern der
Erkennung. Die Anfuehrungszeichen sind darum als Testfall festgeschrieben.
"""

import importlib.util
import json
import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "port-drift-check.py"


def _load():
    """Laedt das Skript als Modul — der Dateiname hat einen Bindestrich und ist
    darueber nicht importierbar."""
    spec = importlib.util.spec_from_file_location("port_drift_check", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pdc = _load()


# --- labelled_ports: ports.sh ist die Quelle ------------------------------


def test_ports_sh_liefert_labels():
    labels = pdc.labelled_ports()
    assert labels, "ports.sh muss Labels liefern"
    assert 8001 in labels and "glm2api" in labels[8001]
    assert 4096 in labels and "opencode" in labels[4096]
    assert 9878 in labels and "antigravity" in labels[9878]


def test_zerokey_port_7250_hat_ein_label():
    """Regression: 7250 fehlte, obwohl zerokey seit A7 im Boot-Pfad laeuft."""
    assert 7250 in pdc.labelled_ports()


# --- bound_ports: was wird tatsaechlich gebunden ---------------------------


def test_unquotiertes_PORT_wird_erkannt(tmp_path):
    """`PORT=8001` — die Form aus infra/scripts/glm2api.sh."""
    f = tmp_path / "s.sh"
    f.write_text('#!/usr/bin/env bash\nHOST="127.0.0.1"\nPORT=8001\nHEALTH="$HOST:$PORT"\n')
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {8001: ["s.sh"]}


def test_quotiertes_PORT_wird_erkannt(tmp_path):
    """`PORT="7250"` — die Form aus start-zerokey.sh.

    Genau dieser Fall fehlte in der ersten Fassung; ohne ihn faellt der
    Negativtest des Checks still durch.
    """
    f = tmp_path / "s.sh"
    f.write_text('#!/usr/bin/env bash\nPORT="7250"\nMODELS_URL="http://h:${PORT}/v1"\n')
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {7250: ["s.sh"]}


def test_einfach_quotiertes_PORT_wird_erkannt(tmp_path):
    f = tmp_path / "s.sh"
    f.write_text("PORT='9878'\n")
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {9878: ["s.sh"]}


def test_export_PORT_wird_erkannt(tmp_path):
    f = tmp_path / "s.sh"
    f.write_text("export PORT=4096\n")
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {4096: ["s.sh"]}


def test_double_dash_port_wird_erkannt(tmp_path):
    """`opencode serve --port 4096`."""
    f = tmp_path / "s.sh"
    f.write_text("opencode serve --port 4096 &\n")
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {4096: ["s.sh"]}


def test_js_port_feld_wird_erkannt(tmp_path):
    """zerokey/constants.js: `PORT: process.env.PORT || 7250,`"""
    f = tmp_path / "c.js"
    f.write_text("module.exports = {\n  PORT: process.env.PORT || 7250,\n};\n")
    assert pdc.bound_ports(tmp_path, ["c.js"]) == {7250: ["c.js"]}


def test_kommentarzeilen_werden_ignoriert(tmp_path):
    """Sonst wuerde eine historische Notiz den Check rot machen — genau die
    Umschreibung, die der Plan gerade vermeiden will."""
    f = tmp_path / "s.sh"
    f.write_text('# PORT=1234 war mal der alte Test-Port\n# echo "Port=5678"\n')
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {}


def test_echo_zeilen_werden_ignoriert(tmp_path):
    """`echo "Port ${PORT} ist belegt"` ist keine Deklaration."""
    f = tmp_path / "s.sh"
    f.write_text('echo "ss -tlnp | grep :9878"\nprintf "port=4321\\n"\n')
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {}


def test_url_mit_port_ist_keine_deklaration(tmp_path):
    """Ein curl gegen einen bekannten Port bindet nichts."""
    f = tmp_path / "s.sh"
    f.write_text('curl -s http://127.0.0.1:9878/v1/models\n')
    assert pdc.bound_ports(tmp_path, ["s.sh"]) == {}


def test_fehlende_datei_wird_uebersprungen(tmp_path):
    assert pdc.bound_ports(tmp_path, ["gibt-es-nicht.sh"]) == {}


# --- devcontainer_ports: beide erlaubten Formen ----------------------------


def test_devcontainer_int_form(tmp_path):
    f = tmp_path / "devcontainer.json"
    f.write_text(json.dumps({"forwardPorts": [4096, 8001]}))
    assert pdc.devcontainer_ports(f) == {4096, 8001}


def test_devcontainer_objekt_form(tmp_path):
    """vs-Code erlaubt `{"containerPort": 8001, "hostPort": 8001}`."""
    f = tmp_path / "devcontainer.json"
    f.write_text(json.dumps({"forwardPorts": [{"containerPort": 8001, "hostPort": 8001}]}))
    assert pdc.devcontainer_ports(f) == {8001}


def test_devcontainer_ohne_forwardports(tmp_path):
    f = tmp_path / "devcontainer.json"
    f.write_text(json.dumps({"name": "MAIN"}))
    assert pdc.devcontainer_ports(f) == set()


def test_devcontainer_kaputt_liefert_leer_statt_raisen(tmp_path):
    """Ein kaputtes JSON darf den Check nicht mit einem Traceback killen."""
    f = tmp_path / "devcontainer.json"
    f.write_text("{ kein json")
    assert pdc.devcontainer_ports(f) == set()


def test_devcontainer_fehlend_liefert_leer(tmp_path):
    assert pdc.devcontainer_ports(tmp_path / "nope.json") == set()


# --- Der Zustand, der im Repo tatsaechlich gilt -----------------------------


def test_echter_repo_zustand_ist_ju_st_gruen():
    """Wenn dieser Test rot wird, ist wirklich ein Port ohne Label da."""
    assert pdc.main([]) == 0


def test_echte_ports_sind_die_vier_bekannten():
    """Gegenueber A7/§9.8: die vier Dienste des Codespaces.

    Faellt einer weg, laeuft der Dienst ohne Label — oder der Check hat einen
    echten Port verloren (der Bug, den die erste Fassung hatte).
    """
    bound = set(pdc.bound_ports())
    assert {4096, 7250, 8001, 9878} <= bound


# --- Negativtest als Prozess: der Weg, den Hook und CI fahren ----------------


def test_quiet_modus_gibt_nur_exit_code():
    assert pdc.main(["--quiet"]) == 0


def test_fehlende_labels_sind_exit_2():
    """Wenn ports.sh keine Labels mehr liefert, ist das ein kaputter Parser —
    und muss sich von echter Drift (Exit 1) unterscheiden."""
    empty = SCRIPT.parent / "ports.sh"
    orig = empty.read_text(encoding="utf-8")
    try:
        empty.write_text("#!/usr/bin/env bash\nlabel() { echo x; }\n", encoding="utf-8")
        assert pdc.main([]) == 2
    finally:
        empty.write_text(orig, encoding="utf-8")


def test_negativtest_end_to_end():
    """Der ganze Weg ueber den echten Aufruf: Label entfernen -> Exit 1.

    Ohne diesen Test koennte der Check still nichts mehr erkennen und trotzdem
    gruen sein — das war der Fehler der ersten Fassung.
    """
    ports = SCRIPT.parent / "ports.sh"
    orig = ports.read_text(encoding="utf-8")
    try:
        ports.write_text(orig.replace('7250) echo "zerokey', '9999) echo "zerokey'), encoding="utf-8")
        res = subprocess.run(
            [str(SCRIPT)], capture_output=True, text=True, timeout=60
        )
        assert res.returncode == 1, res.stdout + res.stderr
        assert "7250" in res.stdout
    finally:
        ports.write_text(orig, encoding="utf-8")

    res = subprocess.run([str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr