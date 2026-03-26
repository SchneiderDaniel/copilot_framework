---
name: playwright-ui-tester
description: Performs browser-based UI testing using Playwright. Use when Gemini CLI needs to verify application functionality through a real browser, including running the Flask app in the background and executing Python Playwright tests.
---

# Skill: Playwright UI Tester

This skill enables automated UI testing of applications using Playwright and Python.

## Workflow

1.  **Environment Setup**: Ensure `playwright` and `pytest-playwright` are installed.
2.  **Start Application**: Run the target application (e.g., Flask app) in a background process.
3.  **Execute Tests**: Use the provided wrapper script from the root or the app directory.
    ```bash
    # From mono-repo root
    python .gemini/skills/playwright-ui-tester/scripts/run_ui_test.py flask_blogs/flask_planhead 5002 flask_blogs/flask_planhead/tests/ui_test.py
    ```
4.  **Teardown**: The script automatically shuts down the application and background processes.
5.  **Reporting**: Review the output of the script for test results.

## Tools and Resources

- **`.gemini/skills/playwright-ui-tester/scripts/run_ui_test.py`**: A wrapper script that automates the start/stop cycle of the app and runs the tests.
- **`.gemini/skills/playwright-ui-tester/assets/test_template.py`**: A boilerplate Playwright test script.

## Best Practices

- Use `pytest` for running Playwright tests for better reporting.
- Use headless mode by default unless visual debugging is needed.
- Always ensure the application is reachable before starting tests.
- Clean up any temporary files or background processes after testing.
