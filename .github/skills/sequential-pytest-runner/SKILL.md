---
name: sequential-pytest-runner
description: "Executes pytest tests one by one sequentially instead of all at once. Stops immediately when a test fails. Use this when the user asks to run all tests to prevent the agent from getting overwhelmed by too many failures at once."
---

# Skill: Sequential Pytest Runner

This skill ensures that test execution happens one test at a time, halting immediately upon a failure so the failure can be investigated and fixed before proceeding to the next test.

## How to use

Execute the provided Python script to gather all tests and run them sequentially.

### For Planhead
```bash
cd flask_blogs/flask_planhead
$env:PYTHONPATH="."
python ../../../.gemini/skills/sequential-pytest-runner/scripts/run_sequential_tests.py .
```

### For Hippocooking
```bash
cd flask_blogs/flask_hippocooking
$env:PYTHONPATH="."
python ../../../.gemini/skills/sequential-pytest-runner/scripts/run_sequential_tests.py .
```

The script automatically:
1. Collects all tests in the specified directory using `pytest --collect-only -q`.
2. Executes them one by one.
3. If a test fails, the script will stop immediately with exit code 1.

**Crucial Step:** When a test fails, DO NOT attempt to run the remaining tests or use a different test execution strategy. **Fix the failed test first**, ensure it passes, and then re-run the script.
