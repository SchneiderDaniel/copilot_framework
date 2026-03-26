import sys
import os

# Add scripts directory to sys.path for importing workflow_config
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from workflow_config import GATES, TRANSITIONS

def test_all_personas_present():
    """T-UC-1: Verify all core personas are present in GATES."""
    expected_personas = {"Sherlock", "Mycroft", "Lestrade", "Watson", "Hounds"}
    assert all(p in GATES for p in expected_personas)

def test_all_statuses_have_transitions():
    """T-UC-2: Verify every status in GATES has a transition for both success and failure."""
    for persona, allowed_statuses in GATES.items():
        for status in allowed_statuses:
            assert status in TRANSITIONS, f"Status '{status}' (allowed for {persona}) has no transitions defined."
            assert "success" in TRANSITIONS[status], f"Status '{status}' has no 'success' outcome."
            assert "failure" in TRANSITIONS[status], f"Status '{status}' has no 'failure' outcome."

def test_transition_targets_exist():
    """T-UC-3: Verify all target statuses exist in the allowed gates or is 'Done'."""
    all_allowed_statuses = set()
    for statuses in GATES.values():
        all_allowed_statuses.update(statuses)
    
    # Standard statuses for the project
    valid_statuses = all_allowed_statuses | {"Done"}
    
    for status, outcomes in TRANSITIONS.items():
        for outcome, target in outcomes.items():
            assert target in valid_statuses, f"Target status '{target}' from '{status}' is not a valid status."
