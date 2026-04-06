# Skill: Files Overview Table

## Purpose
Generate a comprehensive, column-rich Markdown table of every meaningful source file in a project. The table makes it easy to spot outdated files, understand ownership, and prioritise maintenance work.

---

## Trigger Phrases
Use this skill when the user says any of:
- "create a files overview table"
- "table of all files"
- "audit all files"
- "list all files with purpose"
- "file inventory"

---

## Output Format

Produce a Markdown table grouped by area with these **exact columns**:

| File | Purpose | Why located here | Outdated | Lines | Needs Maintenance |
|------|---------|-----------------|----------|-------|-------------------|

### Column definitions
| Column | Rules |
|--------|-------|
| **File** | Path relative to the project root. Keep it short — omit the root prefix. |
| **Purpose** | One crisp sentence: what the file *does* (not what it contains). |
| **Why located here** | One short phrase: architectural reason for this directory. |
| **Outdated** | `Yes` / `No`. `Yes` if the file references deleted modules, stale config keys, superseded patterns, or build artifacts from an old layout. |
| **Lines** | Integer line count. |
| **Needs Maintenance** | `No` — or a short flag: `Stale reference`, `Dead code`, `Needs update`, `Large — split`, `Missing tests`, etc. |

---

## Procedure

### Step 1 — Discover files
```powershell
Get-ChildItem -Recurse -File "<PROJECT_ROOT>" |
  Where-Object {
    $_.FullName -notmatch '\\\.venv\\'        -and
    $_.FullName -notmatch '\\node_modules\\'  -and
    $_.FullName -notmatch '\\__pycache__\\'   -and
    $_.FullName -notmatch '\\\.git\\'         -and
    $_.FullName -notmatch '\\build\\'         -and
    $_.FullName -notmatch '\\dist\\'          -and
    $_.FullName -notmatch '\\target\\'        -and
    $_.FullName -notmatch '\\\.pytest_cache\\' -and
    $_.FullName -notmatch '\\\.mypy_cache\\'
  } |
  ForEach-Object {
    $lines = (Get-Content $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    $rel   = $_.FullName.Replace("<PROJECT_ROOT>\", "")
    "$lines`t$rel"
  } | Sort-Object
```

**Always exclude:**
- Build artefacts: `build/`, `dist/`, `target/`, `*.pkg`, `*.exe`, `*.zip`, `*.pyc`, `*.pyz`
- Lock files: `package-lock.json`, `Cargo.lock`, `poetry.lock`
- Auto-generated schemas/toc files
- Binary assets: `*.ico`, `*.png`, `*.jpg`
- Runtime data directories: `data/storage/`, `data/samples/`
- Empty `__init__.py` files (0 lines)

### Step 2 — Read files for assessment
Before filling in **Outdated** and **Needs Maintenance**, **read the file** (use `view` or `grep`). Look for:

- Imports of deleted modules
- References to old environment variable names
- References to old config keys or file paths
- TODO / FIXME / HACK comments
- Duplicated logic that exists elsewhere
- Files whose name suggests a role that no longer exists
- PyInstaller `.spec` files — check if `pathex`, `datas`, and `hiddenimports` match current layout
- Documentation files — check if described file tree / commands match current reality

### Step 3 — Group by area
Use bold headings to group rows. Example groups (adapt to the actual project):

**Root** · **Scripts** · **Backend Core** · **Backend API** · **Backend Ingest** · **Backend Integrations** · **Backend Presentation** · **Backend Shared** · **Frontend Core** · **Frontend Components** · **Frontend Tests** · **Tests** · **Infrastructure / CI**

### Step 4 — Write the table
- Save the table to `<SESSION_STATE>/files/<project>_files_table.md`
- Print a summary line: `N files audited — M outdated, K need maintenance`

### Step 5 — Derive improvements (optional, triggered by user)
After the table is built, iterate over every row where **Outdated = Yes** or **Needs Maintenance ≠ No** and:
1. Group fixes by effort: Quick (< 10 min) / Medium / Large
2. Implement Quick fixes immediately
3. For Medium/Large fixes: insert a `todo` into the SQL session DB and report to user

---

## Quality Checklist
- [ ] Every file row was read before being assessed (no guessing)
- [ ] No build artefacts or lock files in the table
- [ ] All groups use the bold-heading separator pattern
- [ ] Summary line included at the end
- [ ] Table saved to session files folder
