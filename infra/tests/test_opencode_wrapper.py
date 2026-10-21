"""Der Wrapper darf v2 nicht auf den v1-Attach-Pfad schicken."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "infra/scripts/opencode-wrapper.sh"


def fake_binary(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "opencode-fake"
    path.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "--version" ]; then printf "%s\\n" "$FAKE_VERSION"; exit 0; fi\n'
        'printf "argv:"; printf " [%s]" "$@"; printf "\\n"\n'
    )
    path.chmod(0o755)
    return path


def test_v2_is_passed_through_without_attach(tmp_path: Path) -> None:
    fake = fake_binary(tmp_path, "opencode v2.1.2")
    result = subprocess.run(
        ["bash", str(WRAPPER), "run", "demo"],
        env={**os.environ, "OPENCODE_BIN": str(fake), "FAKE_VERSION": "opencode v2.1.2"},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "argv: [run] [demo]\n"


def test_v2_plain_semver_is_also_recognized(tmp_path: Path) -> None:
    fake = fake_binary(tmp_path, "2.1.2")
    result = subprocess.run(
        ["bash", str(WRAPPER), "run", "demo"],
        env={**os.environ, "OPENCODE_BIN": str(fake), "FAKE_VERSION": "2.1.2"},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "argv: [run] [demo]\n"
