---
name: safe-po-manager
description: Safely update .po files by merging .pot templates without losing existing translations or dropping "obsolete" strings. Use when pybabel update is too aggressive or when translation domains overlap.
---

# Safe PO Manager

This skill provides a non-destructive way to update translation files (`.po`). It ensures that existing translations are never overwritten or deleted, even if `pybabel` thinks they are obsolete.

## Core Workflow

When you need to add new translatable strings to a project without risking existing content:

1.  **Extract** new strings to a temporary `.pot` file using `pybabel` or the project's management script.
2.  **Merge** the `.pot` file into the target `.po` file using the `safe_merge_po.py` script.
3.  **Compile** the updated `.po` file to refresh the application's runtime.

## Usage

### Safe Merge Script

Use the bundled Python script to perform the merge:

```bash
python .gemini/skills/safe-po-manager/scripts/safe_merge_po.py <path_to_po> <path_to_pot>
```

**Parameters:**
- `po`: Path to the existing translation file (e.g., `app/translations/de/LC_MESSAGES/messages.po`).
- `pot`: Path to the newly extracted template file (e.g., `messages.pot`).

### Example Integration

In this project (`flask_blogs/flask_planhead`), if you want to update `messages.po`:

1.  **Extract**: `python flask_blogs/flask_planhead/manage_translations.py extract messages`
2.  **Safe Merge**: `python .gemini/skills/safe-po-manager/scripts/safe_merge_po.py flask_blogs/flask_planhead/app/translations/de/LC_MESSAGES/messages.po flask_blogs/flask_planhead/messages.pot`
3.  **Compile**: `python flask_blogs/flask_planhead/manage_translations.py compile messages`

## Why Use This Over `pybabel update`?

- **Zero Content Loss**: It never deletes entries. "Obsolete" entries (strings removed from code but still in PO) are kept as-is.
- **Revival**: If a previously "obsolete" string is added back to the code, the script automatically moves it back to the active section without losing its original translation.
- **Occurrence Tracking**: Updates source code line references without touching the translations.
- **Fuzzy Prevention**: Does not mark strings as fuzzy unless they are truly new and empty.
