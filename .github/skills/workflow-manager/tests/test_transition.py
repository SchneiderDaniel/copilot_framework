import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Add scripts directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from transition import transition_workflow

def mock_gh_issue_view(status_name):
    return json.dumps({
        "projectItems": [
            {
                "id": "item_123",
                "status": {"name": status_name},
                "project": {"id": "proj_123", "number": 1}
            }
        ]
    })

def mock_gh_field_list():
    return json.dumps({
        "fields": [
            {
                "id": "field_status_id",
                "name": "Status",
                "options": [
                    {"id": "opt_refinement", "name": "Refinement"},
                    {"id": "opt_tech_design", "name": "Technical Design"},
                    {"id": "opt_test_design", "name": "Test Design"},
                    {"id": "opt_implementation", "name": "Implementation"},
                    {"id": "opt_audit", "name": "Audit"},
                    {"id": "opt_done", "name": "Done"}
                ]
            }
        ]
    })

@patch("subprocess.run")
def test_transition_success(mock_run):
    """T-TR-1: Status 'Test Design' and outcome 'success'. Target: 'Implementation'."""
    # Side effects for multiple calls:
    # 1. gh issue view (for transition_workflow current status)
    # 2. gh issue view (for update_status project details)
    # 3. gh project field-list
    # 4. gh project item-edit
    mock_run.side_effect = [
        MagicMock(stdout=mock_gh_issue_view("Test Design"), check=True),
        MagicMock(stdout=mock_gh_issue_view("Test Design"), check=True),
        MagicMock(stdout=mock_gh_field_list(), check=True),
        MagicMock(stdout="updated", check=True)
    ]
    
    assert transition_workflow(106, "success") is True
    
    # Verify the last call was item-edit with 'Implementation' option ID (opt_implementation)
    last_call_args = mock_run.call_args_list[-1][0][0]
    assert "item-edit" in last_call_args
    assert "opt_implementation" in last_call_args

@patch("subprocess.run")
def test_transition_failure_fallback(mock_run):
    """T-TR-2: Status 'Test Design' and outcome 'failure'. Target: 'Technical Design'."""
    mock_run.side_effect = [
        MagicMock(stdout=mock_gh_issue_view("Test Design"), check=True),
        MagicMock(stdout=mock_gh_issue_view("Test Design"), check=True),
        MagicMock(stdout=mock_gh_field_list(), check=True),
        MagicMock(stdout="updated", check=True)
    ]
    
    assert transition_workflow(106, "failure") is True
    
    # Verify target status is 'Technical Design' (opt_tech_design)
    last_call_args = mock_run.call_args_list[-1][0][0]
    assert "opt_tech_design" in last_call_args

@patch("subprocess.run")
def test_transition_from_refinement(mock_run):
    """T-TR-3: Status 'Refinement' and outcome 'success'. Target: 'Technical Design'."""
    mock_run.side_effect = [
        MagicMock(stdout=mock_gh_issue_view("Refinement"), check=True),
        MagicMock(stdout=mock_gh_issue_view("Refinement"), check=True),
        MagicMock(stdout=mock_gh_field_list(), check=True),
        MagicMock(stdout="updated", check=True)
    ]
    
    assert transition_workflow(106, "success") is True
    last_call_args = mock_run.call_args_list[-1][0][0]
    assert "opt_tech_design" in last_call_args

@patch("subprocess.run")
def test_invalid_outcome(mock_run):
    """T-TR-4: Invalid outcome."""
    # We use argparse choices, but if called programmatically:
    # transition_workflow doesn't check choices internally, but TRANSITIONS.get will return None
    mock_run.side_effect = [
        MagicMock(stdout=mock_gh_issue_view("Refinement"), check=True)
    ]
    assert transition_workflow(106, "invalid_outcome") is False
