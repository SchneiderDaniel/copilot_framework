import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Add scripts directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_gate import check_gate

def mock_gh_issue_view(status_name):
    # Mock output for gh issue view --json projectItems
    return json.dumps({
        "projectItems": [
            {
                "status": {"name": status_name},
                "project": {"id": "proj_123", "number": 1}
            }
        ]
    })

@patch("subprocess.run")
def test_gate_success(mock_run):
    """T-CG-1: Mock 'Technical Design'. Run for 'Mycroft'. Expect Success."""
    mock_run.return_value = MagicMock(stdout=mock_gh_issue_view("Technical Design"), check=True)
    assert check_gate(106, "Mycroft") is True

@patch("subprocess.run")
def test_gate_wrong_persona(mock_run):
    """T-CG-2: Mock 'Technical Design'. Run for 'Sherlock'. Expect Failure."""
    mock_run.return_value = MagicMock(stdout=mock_gh_issue_view("Technical Design"), check=True)
    assert check_gate(106, "Sherlock") is False

@patch("subprocess.run")
def test_gate_wrong_status(mock_run):
    """T-CG-3: Mock 'Implementation'. Run for 'Lestrade'. Expect Failure."""
    mock_run.return_value = MagicMock(stdout=mock_gh_issue_view("Implementation"), check=True)
    assert check_gate(106, "Lestrade") is False

@patch("subprocess.run")
def test_gate_no_project(mock_run):
    """T-CG-4: Mock empty projectItems. Expect Failure."""
    mock_run.return_value = MagicMock(stdout=json.dumps({"projectItems": []}), check=True)
    assert check_gate(106, "Watson") is False

@patch("subprocess.run")
def test_gate_command_failure(mock_run):
    """T-CG-5: Mock 'gh' command failure. Expect Failure."""
    from subprocess import CalledProcessError
    mock_run.side_effect = CalledProcessError(1, "gh", stderr="No internet connection")
    assert check_gate(106, "Watson") is False
