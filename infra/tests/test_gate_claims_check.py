"""Tests fuer infra/scripts/gate-claims-check.py.

Der Check existiert wegen eines konkreten Fehlers: der Coverage-Floor ist GLOBAL
(`fail_under` auf TOTAL), aber vier Gate-Dateien behaupteten „pro Datei" — und
nichts hielt diese Aussagen gegen `infra/coverage-floor.rc`. Aufgefallen ist es
erst, als ein neues Skript mit 0 % die Summe von 95 % auf 77 % zog.

Die zwei Richtungen sind beide festgeschrieben: eine falsche Aussage MUSS
anschlagen (Negativtest), eine korrekte Aussage darf NICHT anschlagen
(Positivtest). Ohne den Positivtest waere ein Check, der immer rot ist, gruen
getestet.
"""

import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gate-claims-check.py"


def _load():
    """Laedt das Skript als Modul — der Dateiname hat einen Bindestrich."""
    spec = importlib.util.spec_from_file_location("gate_claims_check", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gcc = _load()


# --- floor_scope: wo steht fail_under? ------------------------------------


def test_floor_scope_global_bei_report_sektion():
    assert gcc.floor_scope("[report]\nfail_under = 90\n") == "global"


def test_floor_scope_per_file_bei_report_mit_datei():
    assert gcc.floor_scope("[report:foo.py]\nfail_under = 90\n") == "per-file"


def test_floor_scope_default_ohne_fail_under_ist_global():
    assert gcc.floor_scope("[report]\nshow_missing = True\n") == "global"


def test_floor_scope_ignoriert_kommentierte_zeile_nicht_sektion():
    # Eine Zeile mit `=` in der falschen Sektion darf die Scope nicht kippen.
    text = "[run]\nsource = infra/scripts\n[report]\nfail_under = 90\n"
    assert gcc.floor_scope(text) == "global"


# --- line_problem: Aussage gegen Scope ------------------------------------


def test_global_und_pro_datei_schlaegt_an():
    why = gcc.line_problem("global", "## cov-floor: Gate. Bewusst pro Datei, nicht global:")
    assert why is not None


def test_global_und_nicht_pro_datei_schlaegt_nicht_an():
    why = gcc.line_problem("global", "der Floor ist GLOBAL, nicht pro Datei")
    assert why is None


def test_global_und_nicht_pro_datei_grossgeschrieben_ok():
    why = gcc.line_problem("global", "# cov: Dateien), NICHT pro Datei — frueher falsch")
    assert why is None


def test_global_und_einzeldatei_behauptung_schlaegt_an():
    why = gcc.line_problem("global", "# Der Floor gilt fuer check-proxy-budget.py — der Bug")
    assert why is not None


def test_global_und_einzeldatei_ohne_floor_kontext_ok():
    # `.py` + "fuer" ohne Floor-Kontext ist keine Floor-Aussage.
    why = gcc.line_problem("global", "# das gilt fuer helper.py und fuer main.py")
    assert why is None


def test_pro_datei_ohne_coverage_kontext_ok():
    # "pro Datei" in einem ganz anderen Zusammenhang darf nicht anschlagen.
    why = gcc.line_problem("global", "# Die Regel laeuft pro Datei, unabhaengig")
    assert why is None


def test_per_file_und_global_behauptung_schlaegt_an():
    why = gcc.line_problem("per-file", "# Der Floor ist global (fail_under auf TOTAL)")
    assert why is not None


def test_per_file_mit_korrekter_aussage_ok():
    why = gcc.line_problem("per-file", "# Floor gilt pro Datei, fail_under je Sektion")
    assert why is None


# --- check(): gegen ein tmp-Repo ------------------------------------------


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _minimal_repo(root: pathlib.Path, floor: str, claims: dict) -> None:
    _write(root, "infra/coverage-floor.rc", floor)
    defaults = {
        "pyproject.toml": "# leer\n",
        "Makefile": "# leer\n",
        ".github/workflows/checks.yml": "# leer\n",
    }
    defaults.update(claims)
    for rel, text in defaults.items():
        _write(root, rel, text)


def test_check_findet_falsche_pro_datei_aussage(tmp_path):
    _minimal_repo(
        tmp_path,
        "[report]\nfail_under = 90\n",
        {"Makefile": "## cov-floor: Bewusst pro Datei, nicht global:\n"},
    )
    problems = gcc.check(tmp_path)
    assert len(problems) == 1
    assert "Makefile:1" in problems[0]
    assert "pro-Datei" in problems[0]


def test_check_sauber_bei_korrekten_aussagen(tmp_path):
    _minimal_repo(
        tmp_path,
        "[report]\nfail_under = 90\n",
        {"Makefile": "# Der Floor ist GLOBAL (fail_under auf TOTAL)\n"},
    )
    assert gcc.check(tmp_path) == []


def test_check_meldet_fehlende_config(tmp_path):
    problems = gcc.check(tmp_path)
    assert problems and "fehlt" in problems[0]


def test_check_meldet_fehlende_gate_datei(tmp_path):
    _write(tmp_path, "infra/coverage-floor.rc", "[report]\nfail_under = 90\n")
    problems = gcc.check(tmp_path)
    assert any("pyproject.toml: fehlt" in p for p in problems)


def test_check_per_file_scope_kippt_die_richtung(tmp_path):
    # Dieselbe Zeile ist bei per-file-Scope korrekt und bei global falsch.
    _minimal_repo(
        tmp_path,
        "[report:foo.py]\nfail_under = 90\n",
        {"pyproject.toml": "# Floor je Datei, fail_under pro Sektion\n"},
    )
    assert gcc.check(tmp_path) == []


# --- main(): der echte Aufruf ---------------------------------------------


def test_main_auf_dem_echten_repo_ist_gruen():
    assert gcc.main([]) == 0


def test_main_quiet_gibt_bei_drift_exit_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gcc, "REPO", tmp_path)
    _minimal_repo(tmp_path, "[report]\nfail_under = 90\n", {"Makefile": "# cov-floor: pro Datei\n"})
    assert gcc.main(["--quiet"]) == 1
    assert capsys.readouterr().out == ""  # --quiet schweigt


def test_main_ohne_quiet_meldet_drift(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gcc, "REPO", tmp_path)
    _minimal_repo(tmp_path, "[report]\nfail_under = 90\n", {"Makefile": "# cov-floor: pro Datei\n"})
    assert gcc.main([]) == 1
    out = capsys.readouterr().out
    assert "Widerspruch" in out and "Makefile:1" in out
