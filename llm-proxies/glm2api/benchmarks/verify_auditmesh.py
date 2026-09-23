#!/usr/bin/env python3
"""Independent post-run oracle for the AuditMesh agent benchmark."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class VerificationError(Exception):
    """Raised when the generated project violates the benchmark contract."""


REQUIRED_FILES = (
    "data/docs/architecture.md",
    "data/docs/runbook.md",
    "data/docs/api_spec.md",
    "data/logs/service_app.log",
    "data/logs/audit_security.txt",
    "data/configs/rules.json",
    "data/configs/services.json",
    "src/auditmesh/__init__.py",
    "src/auditmesh/__main__.py",
    "src/auditmesh/models.py",
    "src/auditmesh/analyzer.py",
    "src/auditmesh/reporter.py",
    "src/auditmesh/parsers/__init__.py",
    "src/auditmesh/parsers/doc_parser.py",
    "src/auditmesh/parsers/log_parser.py",
    "src/auditmesh/parsers/config_loader.py",
    "tests/test_parsers.py",
    "tests/test_analyzer.py",
    "tests/test_reporter.py",
    "pyproject.toml",
)


def fail(message: str) -> None:
    raise VerificationError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"cannot read {path}: {error}")
    except json.JSONDecodeError as error:
        fail(f"invalid JSON in {path}: {error}")


def require_equal(actual: Any, expected: Any, label: str, errors: list[str]) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def require_float(actual: Any, expected: float, label: str, errors: list[str]) -> None:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        errors.append(f"{label}: expected number {expected!r}, got {actual!r}")
    elif not math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9):
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def run_pipeline(root: Path) -> None:
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [sys.executable, "-m", "auditmesh", "--root", str(root)]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError as error:
        fail(f"could not start {' '.join(command)}: {error}")
    except subprocess.TimeoutExpired:
        fail("AuditMesh CLI exceeded the 60 second verifier timeout")

    if result.returncode:
        details = (result.stdout + "\n" + result.stderr).strip()
        fail(
            f"AuditMesh CLI exited with {result.returncode}. "
            f"Output:\n{details[-3000:]}"
        )


def verify_layout_and_fixtures(root: Path) -> None:
    if not root.is_dir():
        fail(f"benchmark root is not a directory: {root}")

    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        fail("missing required files:\n- " + "\n- ".join(missing))

    services = read_json(root / "data/configs/services.json")
    if not isinstance(services, dict) or not isinstance(services.get("services"), list):
        fail("services.json must contain a services array")
    by_name = {
        item.get("name"): item
        for item in services["services"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    expected_services = {
        "gateway": (8080, ["identity", "ledger"]),
        "identity": (8081, []),
        "ledger": (8082, []),
    }
    errors: list[str] = []
    require_equal(set(by_name), set(expected_services), "service names", errors)
    for name, (port, dependencies) in expected_services.items():
        service = by_name.get(name, {})
        require_equal(service.get("port"), port, f"{name}.port", errors)
        require_equal(
            service.get("depends_on"), dependencies, f"{name}.depends_on", errors
        )

    rules = read_json(root / "data/configs/rules.json")
    if not isinstance(rules, dict):
        errors.append("rules.json must be a JSON object")
    else:
        require_float(rules.get("max_error_rate"), 0.4, "max_error_rate", errors)
        require_float(
            rules.get("min_runbook_coverage"), 0.75, "min_runbook_coverage", errors
        )
        require_equal(rules.get("max_security_events"), 3, "max_security_events", errors)

    app_log = (root / "data/logs/service_app.log").read_text(encoding="utf-8")
    app_lines = [line for line in app_log.splitlines() if line.strip()]
    require_equal(len(app_lines), 12, "service_app.log line count", errors)
    require_equal(app_log.count("ERR-101"), 2, "ERR-101 fixture count", errors)
    require_equal(app_log.count("ERR-500"), 1, "ERR-500 fixture count", errors)
    require_equal(app_log.count("ERR-404"), 1, "ERR-404 fixture count", errors)

    security_log = (root / "data/logs/audit_security.txt").read_text(encoding="utf-8")
    security_lines = [line for line in security_log.splitlines() if line.strip()]
    require_equal(len(security_lines), 4, "audit_security.txt line count", errors)
    require_equal(security_log.count("AUTH_FAIL"), 2, "AUTH_FAIL fixture count", errors)
    require_equal(
        security_log.count("ACCESS_DENIED"), 1, "ACCESS_DENIED fixture count", errors
    )
    require_equal(security_log.count("RATE_LIMIT"), 1, "RATE_LIMIT fixture count", errors)

    runbook = (root / "data/docs/runbook.md").read_text(encoding="utf-8")
    api_spec = (root / "data/docs/api_spec.md").read_text(encoding="utf-8")
    for marker, text in (("ERR-101", runbook), ("ERR-500", runbook), ("obsolete.md", api_spec)):
        if marker not in text:
            errors.append(f"required documentation marker missing: {marker}")

    if errors:
        fail("fixture contract failed:\n- " + "\n- ".join(errors))


def verify_metrics(root: Path, *, mutated: bool = False) -> dict[str, Any]:
    metrics_path = root / "output/metrics.json"
    report_path = root / "output/audit_report.md"
    if not metrics_path.is_file() or not report_path.is_file():
        fail("CLI did not create output/metrics.json and output/audit_report.md")

    metrics = read_json(metrics_path)
    if not isinstance(metrics, dict):
        fail("metrics.json must contain a JSON object")

    errors: list[str] = []
    if mutated:
        expected_entries = 13
        expected_errors = 5
        expected_error_rate = 5 / 13
        expected_err_101 = 3
        expected_limit = 0.35
        expected_error_check = False
        expected_passed = 0
        expected_score = 0.0
    else:
        expected_entries = 12
        expected_errors = 4
        expected_error_rate = 4 / 12
        expected_err_101 = 2
        expected_limit = 0.4
        expected_error_check = True
        expected_passed = 1
        expected_score = 1 / 3

    require_equal(metrics.get("schema_version"), 1, "schema_version", errors)
    require_equal(metrics.get("app_log_entries"), expected_entries, "app_log_entries", errors)
    require_equal(metrics.get("app_error_entries"), expected_errors, "app_error_entries", errors)
    require_float(metrics.get("error_rate"), expected_error_rate, "error_rate", errors)
    require_equal(
        metrics.get("error_code_counts"),
        {"ERR-101": expected_err_101, "ERR-404": 1, "ERR-500": 1},
        "error_code_counts",
        errors,
    )
    require_equal(
        metrics.get("documented_error_codes"),
        ["ERR-101", "ERR-500"],
        "documented_error_codes",
        errors,
    )
    require_equal(
        metrics.get("undocumented_error_codes"),
        ["ERR-404"],
        "undocumented_error_codes",
        errors,
    )
    require_float(metrics.get("runbook_coverage"), 2 / 3, "runbook_coverage", errors)
    require_equal(
        metrics.get("broken_local_links"),
        [{"source": "api_spec.md", "target": "obsolete.md"}],
        "broken_local_links",
        errors,
    )
    require_equal(
        metrics.get("security_event_counts"),
        {"ACCESS_DENIED": 1, "AUTH_FAIL": 2, "RATE_LIMIT": 1},
        "security_event_counts",
        errors,
    )
    require_equal(metrics.get("security_event_total"), 4, "security_event_total", errors)

    checks = metrics.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be a JSON object")
        checks = {}
    expected_checks = {
        "error_rate": (expected_error_rate, expected_limit, expected_error_check),
        "runbook_coverage": (2 / 3, 0.75, False),
        "security_events": (4, 3, False),
    }
    for name, (actual, limit, passed) in expected_checks.items():
        check = checks.get(name)
        if not isinstance(check, dict):
            errors.append(f"checks.{name} must be a JSON object")
            continue
        require_float(check.get("actual"), float(actual), f"checks.{name}.actual", errors)
        require_float(check.get("limit"), float(limit), f"checks.{name}.limit", errors)
        require_equal(check.get("passed"), passed, f"checks.{name}.passed", errors)

    require_equal(metrics.get("passed_checks"), expected_passed, "passed_checks", errors)
    require_equal(metrics.get("total_checks"), 3, "total_checks", errors)
    require_float(metrics.get("compliance_score"), expected_score, "compliance_score", errors)
    require_equal(metrics.get("compliant"), False, "compliant", errors)

    if not mutated:
        report = report_path.read_text(encoding="utf-8")
        for marker in ("ERR-404", "obsolete.md", "NON_COMPLIANT"):
            if marker not in report:
                errors.append(f"audit_report.md is missing marker {marker!r}")

    if errors:
        label = "mutated input" if mutated else "baseline"
        fail(f"{label} metrics failed:\n- " + "\n- ".join(errors))
    return metrics


def verify_dynamic_behavior(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="auditmesh-verifier-") as directory:
        clone = Path(directory) / "project"
        shutil.copytree(
            root,
            clone,
            ignore=shutil.ignore_patterns("output", ".venv", "__pycache__", ".pytest_cache", "*.pyc"),
        )
        app_log = clone / "data/logs/service_app.log"
        with app_log.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n2026-01-15T09:00:12Z | ERROR | identity | ERR-101 | verifier injected\n"
            )

        rules_path = clone / "data/configs/rules.json"
        rules = read_json(rules_path)
        if not isinstance(rules, dict):
            fail("cannot mutate non-object rules.json")
        rules["max_error_rate"] = 0.35
        rules_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")

        run_pipeline(clone)
        verify_metrics(clone, mutated=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a completed AuditMesh glm2api benchmark run."
    )
    parser.add_argument("root", type=Path, help="benchmark project root")
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        verify_layout_and_fixtures(root)
        run_pipeline(root)
        verify_metrics(root)
        verify_dynamic_behavior(root)
    except VerificationError as error:
        print(f"FAIL AuditMesh benchmark: {error}", file=sys.stderr)
        return 1

    print("OK AuditMesh benchmark verified: baseline and mutated fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
