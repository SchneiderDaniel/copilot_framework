---
name: ignore-file-checker
description: Audits .gitignore and .geminiignore files for consistency, finds tracked files that should be ignored, and identifies untracked files that are missing from ignore lists. Use when the user asks to "check ignores", "clean up the repository", or when troubleshooting why certain files (like env or pycache) are visible.
---

# Ignore File Checker

## Overview
This skill provides a systematic way to audit repository ignore files (`.gitignore` and `.geminiignore`). It helps maintain a clean workspace by identifying common configuration errors, such as non-recursive patterns, and flagging files that are accidentally being tracked by Git despite matching ignore rules.

## Quick Start
To perform a comprehensive audit of the project's ignore settings:

1. **Run the Audit Script**: Execute the bundled Python script to scan the root and all submodules.
   ```bash
   python .gemini/skills/ignore-file-checker/scripts/check_ignores.py
   ```

2. **Analyze the Report**:
   - **Tracked but Ignored**: These files are currently in the Git index but match an ignore pattern. They should usually be removed from Git using `git rm --cached <file>`.
   - **Untracked but Not Ignored**: These are new files that haven't been added to any ignore list. Determine if they should be ignored (e.g., local logs, temporary artifacts) or tracked.
   - **Non-Recursive Patterns**: The script flags patterns like `env/` that might miss directories in subfolders. Recommend updating them to `**/env/`.

3. **Apply Fixes**: Based on the report, update the `.gitignore` or `.geminiignore` files as needed.

## Common Fixes

### Removing Tracked Files
If a file is reported as "Tracked but Ignored":
```bash
git rm --cached path/to/file
```

### Updating Non-Recursive Patterns
Ensure common patterns are recursive to cover the entire project tree:
- Change `env/` to `**/env/`
- Change `__pycache__/` to `**/__pycache__/`
- Change `.pytest_cache/` to `**/.pytest_cache/`

## Resources

### scripts/
- **check_ignores.py**: The primary audit tool. It performs the Git checks and pattern analysis recursively across the project and its submodules.
