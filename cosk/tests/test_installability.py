from __future__ import annotations

import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest


COSK_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_editable_install_from_cosk_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=COSK_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"


@pytest.mark.integration
def test_imports_after_editable_install() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import cosk;"
                "import cosk.extraction;"
                "import cosk.indexing;"
                "import cosk.graph;"
                "import cosk.mcp;"
                "import cosk.safety"
            ),
        ],
        cwd=COSK_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"


@pytest.mark.integration
def test_console_script_cosk_help_succeeds_after_editable_install() -> None:
    install_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=COSK_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install_result.returncode == 0, f"stdout:\n{install_result.stdout}\n\nstderr:\n{install_result.stderr}"

    scripts_dir = Path(sysconfig.get_path("scripts"))
    candidates = [scripts_dir / "cosk", scripts_dir / "cosk.exe", scripts_dir / "cosk-script.py"]
    executable = next((candidate for candidate in candidates if candidate.exists()), None)
    assert executable is not None, f"Could not find cosk script in {scripts_dir}"

    if executable.suffix.lower() == ".py":
        command = [sys.executable, str(executable), "--help"]
    else:
        command = [str(executable), "--help"]

    result = subprocess.run(
        command,
        cwd=COSK_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    assert "index" in result.stdout
    assert "serve" in result.stdout
    assert "inspect" in result.stdout
