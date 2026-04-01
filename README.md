# copilot_framework


To prevent a "Three Pipe Problem" with submodules, we recommend these global or project-local configurations:

```bash
# Automatically update submodules after a pull—no manual labor required.
git config submodule.recurse true

# Ensure no clues (submodule commits) are left behind before pushing the main case.
git config push.recurseSubmodules check

# View the actual history of changes in submodules during a 'git diff'.
git config diff.submodule log

# Keep a summary of submodule status in your 'git status' reports.
git config status.submoduleSummary true
```