#!/usr/bin/env python3
"""Independent post-run oracle for the AuditMesh agent benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn


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

BASE_APP_LOG_LINES = (
    "2026-01-15T09:00:00Z | INFO  | gateway  | REQUEST_STARTED | request=r-001",
    "2026-01-15T09:00:01Z | INFO  | identity | TOKEN_VALIDATED | request=r-001",
    "2026-01-15T09:00:02Z | WARN  | gateway  | CACHE_MISS | key=profile-17",
    "2026-01-15T09:00:03Z | ERROR | identity | ERR-101 | upstream timeout",
    "2026-01-15T09:00:04Z | INFO  | ledger   | SYNC_OK | batch=42",
    "2026-01-15T09:00:05Z | ERROR | gateway  | ERR-500 | ledger unavailable",
    "2026-01-15T09:00:06Z | WARN  | ledger   | RETRY_SCHEDULED | after=5s",
    "2026-01-15T09:00:07Z | ERROR | gateway  | ERR-101 | upstream timeout",
    "2026-01-15T09:00:08Z | INFO  | gateway  | REQUEST_OK | request=r-002",
    "2026-01-15T09:00:09Z | ERROR | catalog  | ERR-404 | catalog entry missing",
    "2026-01-15T09:00:10Z | INFO  | identity | SESSION_CLOSED | request=r-001",
    "2026-01-15T09:00:11Z | INFO  | gateway  | HEALTHY | latency_ms=12",
)

BASE_SECURITY_LOG_LINES = (
    "2026-01-15T09:00:20Z | AUTH_FAIL | user=alice | source=198.51.100.10",
    "2026-01-15T09:00:21Z | AUTH_FAIL | user=bob | source=198.51.100.11",
    "2026-01-15T09:00:22Z | ACCESS_DENIED | user=carol | resource=ledger",
    "2026-01-15T09:00:23Z | RATE_LIMIT | client=mobile | limit=100",
)

IGNORED_SNAPSHOT_PARTS = {"output", ".venv", "__pycache__", ".pytest_cache"}


def fail(message: str) -> NoReturn:
    raise VerificationError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"cannot read {path}: {error}")
    except json.JSONDecodeError as error:
        fail(f"invalid JSON in {path}: {error}")


def values_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            values_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            values_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def require_equal(actual: Any, expected: Any, label: str, errors: list[str]) -> None:
    if not values_equal(actual, expected):
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def require_float(actual: Any, expected: float, label: str, errors: list[str]) -> None:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        errors.append(f"{label}: expected number {expected!r}, got {actual!r}")
    elif not math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9):
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def snapshot_immutable_files(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_SNAPSHOT_PARTS for part in relative.parts):
            continue
        snapshot[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def verify_immutable_files(before: dict[str, str], after: dict[str, str]) -> None:
    changed = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    if changed:
        fail("the CLI modified files outside output:\n- " + "\n- ".join(changed))


def run_pipeline(root: Path) -> None:
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "auditmesh", "--root", str(root)]
    result: subprocess.CompletedProcess[str]
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


def local_markdown_links(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"\[[^\]]+\]\(([^)\s]+)\)", text)
        if not match.group(1).startswith(("http://", "https://", "#"))
    }


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
    require_equal(len(services["services"]), 3, "service count", errors)
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
    require_equal(
        tuple(app_lines), BASE_APP_LOG_LINES, "service_app.log contents", errors
    )

    security_log = (root / "data/logs/audit_security.txt").read_text(encoding="utf-8")
    security_lines = [line for line in security_log.splitlines() if line.strip()]
    require_equal(
        tuple(security_lines), BASE_SECURITY_LOG_LINES, "audit_security.txt contents", errors
    )

    architecture = (root / "data/docs/architecture.md").read_text(encoding="utf-8")
    runbook = (root / "data/docs/runbook.md").read_text(encoding="utf-8")
    api_spec = (root / "data/docs/api_spec.md").read_text(encoding="utf-8")
    for service_name in ("gateway", "identity", "ledger"):
        if service_name not in architecture:
            errors.append(f"architecture.md is missing service {service_name}")
    if not {"runbook.md", "api_spec.md"}.issubset(local_markdown_links(architecture)):
        errors.append("architecture.md is missing required local Markdown links")
    for error_code in ("ERR-101", "ERR-500"):
        if not re.search(rf"(?m)^#+\s+.*\b{error_code}\b", runbook):
            errors.append(f"runbook.md is missing a heading for {error_code}")
    if not {"architecture.md", "obsolete.md"}.issubset(local_markdown_links(api_spec)):
        errors.append("api_spec.md is missing required local Markdown links")

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
        expected_error_counts = {"ERR-101": 3, "ERR-404": 1, "ERR-500": 1}
        expected_documented = ["ERR-101", "ERR-404", "ERR-500"]
        expected_undocumented: list[str] = []
        expected_coverage = 1.0
        expected_broken_links: list[dict[str, str]] = []
        expected_security_counts = {"ACCESS_DENIED": 1, "AUTH_FAIL": 3, "RATE_LIMIT": 1}
        expected_security_total = 5
        expected_services = ["catalog", "gateway", "identity", "ledger"]
        expected_unknown_services: list[str] = []
        expected_service_count = 4
        expected_dependency_edges = 2
        expected_checks = {
            "error_rate": (expected_error_rate, 5 / 13, True),
            "runbook_coverage": (1.0, 1.0, True),
            "security_events": (5, 5, True),
        }
        expected_passed = 3
        expected_score = 1.0
        expected_compliant = True
        expected_report_status = "AUDIT_STATUS: COMPLIANT"
    else:
        expected_entries = 12
        expected_errors = 4
        expected_error_rate = 4 / 12
        expected_error_counts = {"ERR-101": 2, "ERR-404": 1, "ERR-500": 1}
        expected_documented = ["ERR-101", "ERR-500"]
        expected_undocumented = ["ERR-404"]
        expected_coverage = 2 / 3
        expected_broken_links = [{"source": "api_spec.md", "target": "obsolete.md"}]
        expected_security_counts = {"ACCESS_DENIED": 1, "AUTH_FAIL": 2, "RATE_LIMIT": 1}
        expected_security_total = 4
        expected_services = ["gateway", "identity", "ledger"]
        expected_unknown_services = ["catalog"]
        expected_service_count = 3
        expected_dependency_edges = 2
        expected_checks = {
            "error_rate": (expected_error_rate, 0.4, True),
            "runbook_coverage": (2 / 3, 0.75, False),
            "security_events": (4, 3, False),
        }
        expected_passed = 1
        expected_score = 1 / 3
        expected_compliant = False
        expected_report_status = "AUDIT_STATUS: NON_COMPLIANT"

    require_equal(metrics.get("schema_version"), 1, "schema_version", errors)
    require_equal(metrics.get("app_log_entries"), expected_entries, "app_log_entries", errors)
    require_equal(metrics.get("app_error_entries"), expected_errors, "app_error_entries", errors)
    require_float(metrics.get("error_rate"), expected_error_rate, "error_rate", errors)
    require_equal(
        metrics.get("configured_services"),
        expected_services,
        "configured_services",
        errors,
    )
    require_equal(
        metrics.get("unknown_log_services"),
        expected_unknown_services,
        "unknown_log_services",
        errors,
    )
    require_equal(metrics.get("service_count"), expected_service_count, "service_count", errors)
    require_equal(
        metrics.get("dependency_edge_count"),
        expected_dependency_edges,
        "dependency_edge_count",
        errors,
    )
    require_equal(
        metrics.get("error_code_counts"),
        expected_error_counts,
        "error_code_counts",
        errors,
    )
    require_equal(
        metrics.get("documented_error_codes"),
        expected_documented,
        "documented_error_codes",
        errors,
    )
    require_equal(
        metrics.get("undocumented_error_codes"),
        expected_undocumented,
        "undocumented_error_codes",
        errors,
    )
    require_float(metrics.get("runbook_coverage"), expected_coverage, "runbook_coverage", errors)
    require_equal(
        metrics.get("broken_local_links"),
        expected_broken_links,
        "broken_local_links",
        errors,
    )
    require_equal(
        metrics.get("security_event_counts"),
        expected_security_counts,
        "security_event_counts",
        errors,
    )
    require_equal(
        metrics.get("security_event_total"), expected_security_total, "security_event_total", errors
    )

    checks = metrics.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be a JSON object")
        checks = {}
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
    require_equal(metrics.get("compliant"), expected_compliant, "compliant", errors)

    report = report_path.read_text(encoding="utf-8")
    for marker in (
        "| Error code | Occurrences | Documentation | Status |",
        "| ERR-404 |",
        expected_report_status,
    ):
        if marker not in report:
            errors.append(f"audit_report.md is missing marker {marker!r}")
    if not mutated and "obsolete.md" not in report:
        errors.append("audit_report.md is missing marker 'obsolete.md'")

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
        app_text = app_log.read_text(encoding="utf-8")
        app_log.write_text(
            app_text.rstrip("\n")
            + "\n2026-01-15T09:00:12Z | ERROR | identity | ERR-101 | verifier injected\n",
            encoding="utf-8",
        )

        security_log = clone / "data/logs/audit_security.txt"
        security_text = security_log.read_text(encoding="utf-8")
        security_log.write_text(
            security_text.rstrip("\n")
            + "\n2026-01-15T09:00:24Z | AUTH_FAIL | user=dave | source=198.51.100.12\n",
            encoding="utf-8",
        )

        runbook_path = clone / "data/docs/runbook.md"
        runbook_text = runbook_path.read_text(encoding="utf-8")
        runbook_path.write_text(
            runbook_text.rstrip("\n")
            + "\n\n## ERR-404\n\nCatalog entry recovery procedure.\n",
            encoding="utf-8",
        )
        (clone / "data/docs/obsolete.md").write_text(
            "# Retired API endpoint\n", encoding="utf-8"
        )

        rules_path = clone / "data/configs/rules.json"
        rules = read_json(rules_path)
        if not isinstance(rules, dict):
            fail("cannot mutate non-object rules.json")
        rules["max_error_rate"] = 5 / 13
        rules["min_runbook_coverage"] = 1.0
        rules["max_security_events"] = 5
        rules_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")

        services_path = clone / "data/configs/services.json"
        services = read_json(services_path)
        if not isinstance(services, dict) or not isinstance(services.get("services"), list):
            fail("cannot mutate services.json without a services array")
        services["services"].append(
            {"name": "catalog", "port": 8083, "depends_on": []}
        )
        services_path.write_text(json.dumps(services, indent=2) + "\n", encoding="utf-8")

        before = snapshot_immutable_files(clone)
        run_pipeline(clone)
        verify_immutable_files(before, snapshot_immutable_files(clone))
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
        before = snapshot_immutable_files(root)
        run_pipeline(root)
        verify_immutable_files(before, snapshot_immutable_files(root))
        verify_metrics(root)
        verify_dynamic_behavior(root)
    except VerificationError as error:
        print(f"FAIL AuditMesh benchmark: {error}", file=sys.stderr)
        return 1

    print("OK AuditMesh benchmark verified: baseline and mutated fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
