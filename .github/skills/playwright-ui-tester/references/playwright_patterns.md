# Playwright Testing Patterns

This reference provides common patterns for writing Playwright tests for Flask applications in this workspace.

## Setup

Ensure `pytest-playwright` and `requests` (for app waiting) are installed:

```bash
pip install pytest-playwright requests
playwright install chromium
```

## Writing Tests

Tests should use the `page` and `base_url` fixtures provided by `pytest-playwright`.

### Locators

Prefer user-facing locators:

- `page.get_by_role("button", name="Submit")`
- `page.get_by_text("Welcome")`
- `page.get_by_label("Username")`

### Assertions

Use the `expect` library for web-first assertions:

- `expect(page).to_have_title("Dashboard")`
- `expect(page.get_by_text("Error")).to_be_visible()`
- `expect(page).to_have_url(re.compile(r"/dashboard$"))`

## Running Tests

Use the `run_ui_test.py` script provided in the skill:

```bash
python .gemini/skills/playwright-ui-tester/scripts/run_ui_test.py flask_blogs/flask_planhead 5000 flask_blogs/flask_planhead/tests/ui_test.py
```

## Handling Dash Components

For apps using Plotly Dash (like Planhead):

- Use `page.wait_for_selector(".dash-spreadsheet-container")` to wait for tables.
- Use `page.wait_for_load_state("networkidle")` to wait for background data loading.
