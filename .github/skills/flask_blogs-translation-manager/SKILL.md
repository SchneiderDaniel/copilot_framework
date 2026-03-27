# Skill: flask_blogs-translation-manager

## Purpose
Manage all translations for the **PlAnhead** Flask app. The single source of truth for translations is `translations.db` (SQLite). `.po` and `.mo` files are **generated artefacts** — never edited directly.

---

## ⚠️ CRITICAL: Pipeline Order

```
translations.db  →  export_sqlite_to_mo.py  →  .po / .mo files
```

**Always edit the DB first, then export. Never the reverse.**

---

## Workflows

### 1. Translate missing strings (fill empty msgstr)
```sql
-- Find all untranslated rows for a locale
SELECT id, domain, msgid, msgstr
FROM translations
WHERE locale = 'fr' AND (msgstr = '' OR msgstr IS NULL)
ORDER BY domain;
```
Then `UPDATE translations SET msgstr = '...', updated_at = datetime('now') WHERE id = ...`

After all updates:
```bash
cd flask_blogs/flask_planhead
python scripts/export_sqlite_to_mo.py
```

### 2. Add new UI strings (new feature)
```bash
cd flask_blogs/flask_planhead
# 1. Extract new strings from source
pybabel extract -F babel.cfg -o app/translations/messages.pot .

# 2. Update .po stubs for all locales
pybabel update -i app/translations/messages.pot -d app/translations

# 3. Import new stubs into DB (does not overwrite existing translations)
python scripts/migrate_po_to_sqlite.py

# 4. Translate new strings in DB (SQL UPDATE)
# 5. Export
python scripts/export_sqlite_to_mo.py
```

### 3. Verify coverage
```bash
cd flask_blogs/flask_planhead
python -m pytest tests/test_translation_completeness_db.py -v
```

Check counts directly:
```sql
SELECT locale, COUNT(*) as total,
       SUM(CASE WHEN msgstr = '' OR msgstr IS NULL THEN 1 ELSE 0 END) as empty
FROM translations
GROUP BY locale;
```

---

## Database Schema
**File**: `flask_blogs/flask_planhead/app/translations.db`  
**Table**: `translations`

| Column | Description |
|--------|-------------|
| id | Primary key |
| locale | `en`, `de`, `fr`, `es` |
| domain | Feature domain (e.g. `bank_account`, `main`, `messages`) |
| msgctxt | Optional context |
| msgid | English source string (never change this) |
| msgid_plural | Plural source string (if applicable) |
| msgstr | Translated string ← **edit this** |
| msgstr_plural | Translated plural (JSON array for plural forms) |
| updated_at | Timestamp |

---

## Key Scripts (run from `flask_blogs/flask_planhead/`)

| Script | Purpose |
|--------|---------|
| `scripts/export_sqlite_to_mo.py` | DB → `.po` + `.mo` (use after any DB edit) |
| `scripts/migrate_po_to_sqlite.py` | `.po` → DB (use only when importing new stubs) |

---

## Translation Guidelines
- **Register**: Formal (DE uses "Sie" → FR "vous" → ES "usted")
- **Format specifiers**: Preserve exactly — `%(var)s`, `%(var)d`, `%s`, `%d`
- **HTML/newlines**: Preserve exactly
- **Plural forms**: FR and ES both use `msgstr[0]` = singular, `msgstr[1]` = plural
- **Fallback**: Missing translations fall back to `en`
- **Reference**: Use `de` translations as style/register reference when translating `fr`/`es`

---

## Supported Locales
`en` · `de` · `fr` · `es`
