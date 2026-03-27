# 🤖 Project: Copilot Framework

## 🏗️ Framework Overview
This repository is an agentic automation framework designed to orchestrate specialized AI agents and skills for high-fidelity software engineering.

### 🗺️ Repository Structure
1.  **`.github/`**: The core operational layer containing agent definitions, reusable skills, and global context.
2.  **`flask_blogs/`**: A hosted mono-repo project that the framework's agents are currently configured to manage.
    - **Gateway (Nginx)**: Subdomain routing and security headers.
    - **Hippocooking**: JSON-driven NoSQL recipe application.
    - **Planhead**: Strategic calculator suite using a strict Service-Layer pattern.

## ⚙️ Operational Protocols (The Commissioner)
The Main Agent (Copilot CLI) acts as the **Commissioner** (Orchestrator). It manages the high-level project status and delegates complex tasks to specialized detectives through the **Mission Control Protocol**.

**🛑 MANDATORY ORCHESTRATION PROTOCOL**:
1.  **Identify GitHub Issue**: If a user mentions a GitHub issue (e.g., `#123`), the Main Agent MUST call **Mission Control**.
2.  **Mission Control Tool**: `python .github/skills/general-workflow-manager/scripts/mission_control.py <issue_number>`
3.  **Synchronize Context**: If the status is ambiguous, the Main Agent may use the `explore` agent (via the `task` tool) to map affected areas before delegating.
4.  **Delegate & Stop**: Invoke the recommended agent directly via the `task` tool (e.g. `agent_type: "sherlock"`). The Main Agent **MUST NOT** implement the logic directly if an issue is active.


### 🗺️ The Agentic Lifecycle
Each agent (detective) has a specialized role and MUST NOT automatically hand over or call other agents. They MUST use the **Finalization Protocol** to update the state and stop.

1.  **Refinement (Analyst)**: Understands requirements and defines User Stories.
2.  **Architecture (Architect)**: Designs technical solutions and ensures SEO/Security standards.
3.  **Test Design (QA Lead)**: Formulates the empirical verification strategy.
4.  **Implementation (Developer)**: Writes the application code and the tests.
5.  **Audit (Auditor)**: Rigorously verifies the implementation against all designs.

**🛑 AUTOMATION MANDATE**: 
Each agent MUST ONLY perform its own task and MUST stop after finalization. The Commissioner (Main Agent) handles the overall flow.

**🛑 ISSUE CLOSING FORBIDDEN**: No agent — including the Commissioner — may ever run `gh issue close`. Only the human reviewer closes GitHub issues. Agents may only advance the project board status.

## 🌍 Agent Environment & Paths
- **Current Project Target**: `flask_blogs` (subdirectory).
- **Tooling Root**: All tools and scripts are called relative to the framework root.
- **Skill Paths**: Reusable skills are located in `.github/skills/`.

## 🧭 Navigation for Framework Maintenance
- **Updating Agent Behavior?** Modify the corresponding markdown file in `.github/agents/`.
- **Adding a New Skill?** Add a new directory in `.github/skills/` with a `SKILL.md` and supporting assets.
- **Global Context?** Update `.github/context/env_args.json`.


# ⚙️ Operational Layer: Agent Behavior

## ⚙️ Operational Protocol (Main Agent)
The Main Agent's primary role is **Orchestration** and **Surgical Fixes**. 

- **Orchestration**: For any task linked to a GitHub issue, call `mission_control.py` and invoke the recommended sub-agent directly via the `task` tool (e.g. `agent_type: "sherlock"`).
- **Surgical Fixes**: If a task is independent of the agentic workflow (no GitHub issue), follow the **Research -> Strategy -> Execution** lifecycle.
- **No Shadow Implementation**: Never implement logic for an active GitHub issue outside the sub-agent workflow.


## ⚠️ CLI Stability & Tool Safety
To prevent terminal crashes and context bloat:
- **`view`**: Never read more than **150 lines** at once. Use `view_range: [start, end]`.
- **`grep`**: Minimize context lines (2-3). Use `head_limit` to cap results.
- **`powershell`**: Pipe large outputs to `| Select-Object -First 20` to avoid flooding context.

# 🤖 Project: Flask Blogs Mono-Repo

## 🏗️ Architectural Overview
This mono-repo orchestrates three distinct Python applications under a single domain, utilizing **Nginx** as the central gateway and **Docker Compose** for infrastructure.

### 🗺️ Service Map & Patterns
1. **Gateway (Nginx)**:
   - **Entry Points**: `nginx/nginx_dev.conf` (Local), `nginx/nginx_prd.conf` (Production).
   - **Role**: SSL termination (Certbot), subdomain routing via uWSGI, and security header injection (CSP, HSTS).
   - **Routing**: 
     - `hippocooking.localhost` -> `flask_hippocooking:5001`
     - `ui.planhead.localhost` / `localhost` -> `flask_planhead:5002`
2. **Hippocooking (Sub-App 1 - The Chef)**:
   - **Architecture**: **JSON-driven NoSQL architecture**.
   - **Logic**: All content (recipes, site-wide translations) is stored as JSON in `flask_hippocooking_volume/`.
   - **Key Pattern**: Thin Blueprints (`homepage/`) dynamically load content based on `locale_id` and `recipe_id` from the filesystem. No traditional database migrations are needed for content updates.
3. **Planhead (Sub-App 2 - The Strategist)**:
   - **Architecture**: **Strict Service-Layer Pattern**.
   - **Logic**: Thin Blueprints (`app/blueprints/`) act as controllers, delegating complex calculations and business logic to the Service Layer (`app/services/`).
   - **SEO & i18n**: Advanced Flask-Babel integration. Uses `?lang=de|en` for session switching. Implements 301 canonical redirects for English to maintain clean URLs for SEO.
   - **Persistence**: Hybrid. SQLite for analytics (`analytics.db`) and JSON for static state.
4. **Myosotis (Sub-App 3 - The Memory)**:
   - **Architecture**: **Agentic Memory Service (CLI + FastAPI)**.
   - **Logic**: Provides semantic search and a Knowledge Graph for memory persistence.
   - **Entry Points**: `myosotis/myosotis/cli/main.py` (CLI) and `myosotis/myosotis/api/app.py` (FastAPI).
   - **Persistence**: High-performance Vector Index and SQLite store in `myosotis_volume/`.

## 🛠️ Technology Stack & Data Storage
- **Runtime**: Python 3.11+, Flask, FastAPI, Dash (Planhead simulations).
- **Communication**: uWSGI (Binary protocol) for Flask apps; REST/FastAPI for Myosotis.
- **Persistence** (NEVER delete `*_volume/`):
  - `flask_hippocooking_volume/recipes`: JSON recipes and images.
  - `flask_planhead_volume/data`: Analytics SQLite DB and simulations.
  - `myosotis_volume/index`: Vector storage and Knowledge Graph.

## 🌍 Localization (i18n) Mandate
- **Hippocooking**: Dual-track. UI strings via Babel `_()`; Recipe content via dynamic JSON loader (`utils.py`).
- **Planhead**: URL-param driven (`?lang=`). Session persistence.
- **⚠️ Planhead Translation Pipeline (CRITICAL — always follow this order)**:
  1. **Edit `translations.db`** (SQLite) — the single source of truth for all translations. Use SQL `UPDATE` statements to fill or correct `msgstr` values in the `translations` table.
  2. **Export to .po/.mo** — run `python scripts/export_sqlite_to_mo.py` from `flask_planhead/` to regenerate all `.po` and `.mo` files from the DB.
  3. **Never edit `.po` files directly** — they are generated artefacts. Changes will be overwritten on next export.
  4. **Adding new strings**: wrap in `_()` in code → run `pybabel extract` + `pybabel update` to sync `.pot`/`.po` stubs → import stubs into DB via `python scripts/migrate_po_to_sqlite.py` → translate in DB → export.
- **Supported locales**: `en`, `de`, `fr`, `es`. All four must be present in `translations.db` for every domain.

## ⚙️ Operational Protocols
The development lifecycle is tailored to task complexity. Standard tasks follow the Research -> Strategy -> Execution (Plan-Act-Validate) workflow. For more complex features, refer to the available specialized agents.

## 🧭 Navigation for Agents
- **Adding a Recipe?** Modify `flask_hippocooking_volume/recipes`.
- **New Calculation Logic?** Add a service to `flask_planhead/app/services/`.
- **New Page?** Register a Blueprint in `flask_planhead/app/__init__.py`.

