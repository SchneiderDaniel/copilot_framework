---
name: flask-translation-manager
description: Manage and repair Flask-Babel translations. Use when German translations in .po files exhibit encoding corruptions, fuzzy flags block compilation, or headers are missing.
---

# Skill: Flask Translation Manager

This skill provides specialized workflows for maintaining high-quality German translations, resolving issues caused by PowerShell or stale catalogs.

## PO Management Workflows

Use the bundled `po_manager.py` for common fixes:

### 1. Repair Encoding
Fixes common corruptions like `Whlen`, `jÃ¤hrlich`, or `ÃÂ¤`.
```bash
python .gemini/skills/flask-translation-manager/scripts/po_manager.py flask_blogs/flask_planhead/app/translations/de/LC_MESSAGES/messages.po --repair
```

### 2. Remove Fuzzy Flags
Required if `pybabel compile` skips entries marked as fuzzy.
```bash
python .gemini/skills/flask-translation-manager/scripts/po_manager.py flask_blogs/flask_planhead/app/translations/de/LC_MESSAGES/messages.po --unfuzzy
```

### 3. Restore Header
Fixes compilation errors due to missing or corrupted PO headers.
```bash
python .gemini/skills/flask-translation-manager/scripts/po_manager.py flask_blogs/flask_planhead/app/translations/de/LC_MESSAGES/messages.po --header
```

## Compilation Workflow

After manual updates or using the manager, always recompile to update the UI:
```bash
# Example for Planhead
pybabel compile -d flask_blogs/flask_planhead/app/translations
```

## Update Workflow

To update empty `msgstr` entries:
1. Identify the empty entries (e.g., by searching for `msgstr ""` in the `.po` files).
2. Use the `replace` tool to update `msgstr ""` with the correct German text.
3. **CRITICAL**: Always use `encoding='utf-8'` when reading or writing PO files.
4. After updates, run `python flask_blogs/flask_planhead/manage_translations.py compile` to refresh the application.
