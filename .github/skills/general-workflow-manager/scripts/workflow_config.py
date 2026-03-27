# Mapping of personas to the statuses they are authorized to work on.
GATES = {
    "Analyst": ["Backlog"],
    "Architect": ["Technical Design"],
    "QA-Lead": ["Test Design"],
    "Developer": ["Implementation"],
    "Auditor": ["Review"]
}

# Mapping of current status and mission outcome to the next status.
TRANSITIONS = {
    "Backlog": {
        "success": "Technical Design",
        "failure": "Backlog"
    },
    "Technical Design": {
        "success": "Test Design",
        "failure": "Backlog"
    },
    "Test Design": {
        "success": "Implementation",
        "failure": "Technical Design"
    },
    "Implementation": {
        "success": "Review",
        "failure": "Test Design",
        "design_revision_requested": "Technical Design"
    },
    "Review": {
        "audit_passed": "Review",
        "failure": "Implementation",
        "test_revision_requested": "Test Design",
        "design_revision_requested": "Technical Design"
    }
}
