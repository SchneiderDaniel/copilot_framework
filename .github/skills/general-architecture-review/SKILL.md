---
name: general-architecture-review
description: >
  Deep architectural review of a codebase or module using senior-architect heuristics. Evaluates
  Separation of Concerns, SOLID principles, scalability, maintainability, technology choices, and
  security architecture. Produces a structured Markdown report with strengths, critical risks, and
  improvement recommendations. Use when asked to "review architecture", "audit the design",
  "check scalability", "evaluate our tech stack", or "technical debt review". Inspired by the
  18 k-star VoltAgent/awesome-claude-code-subagents collection (model: opus).
---

# Skill: general-architecture-review

> **Source**: Inspired by [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (18 k ⭐) — `categories/04-quality-security/architect-reviewer.md`

Deep architectural review skill. Evaluates structural integrity, scalability, security, and long-term maintainability. Produces an actionable report the team can act on immediately.

---

## 🎯 Trigger Conditions

Invoke this skill when the user asks to:
- "Review the architecture" / "Audit the design"
- "Check scalability" / "Evaluate our tech stack"
- "Find technical debt" / "Assess maintainability"
- "Architecture health check"

---

## 🔍 Review Process

### Phase 1 — High-Level Context Mapping
1. Use `glob` / `grep` to identify top-level directories, entry points, and module boundaries.
2. Locate configuration files (`docker-compose.yml`, `nginx.conf`, `__init__.py`, `run.py`, etc.).
3. Identify the architectural pattern in use (Layered, Service-Layer, Hexagonal, Monolith, etc.).
4. Map data flow: where data enters, how it traverses layers, and where it persists.

### Phase 2 — Systematic Checklist Evaluation

Evaluate every pillar below and cite **specific file paths or line numbers** as evidence.

#### 1. Separation of Concerns (SoC) & Modularity
- **Clear Layer Boundaries**: Distinct Presentation / Business Logic / Data Access layers?
- **Leaking Abstractions**: Does the service layer expose HTTP `req/res` objects or raw DB cursors?
- **Module Cohesion**: Are "utility" / "helper" modules scoped or a dumping ground?
- **Coupling**: Excessive direct imports across major components?

#### 2. SOLID Principles
- **Single Responsibility**: Classes/modules doing too many things?
- **Open/Closed**: Adding a new feature requires modifying many existing files vs. adding new ones?
- **Dependency Inversion**: High-level modules import concrete DB drivers / ORMs directly?

#### 3. Scalability & Resilience
- **Async Operations**: Long-running tasks (email, report generation) blocking the main thread?
- **Database Interaction**: N+1 query patterns inside loops?
- **State Management**: Are services stateless and horizontally scalable?
- **Error Handling**: Graceful degradation on DB loss, external API timeout?

#### 4. Maintainability & Testability
- **DRY**: Duplicated logic blocks that should be abstracted?
- **Dependency Injection**: Dependencies hardcoded (makes unit testing impossible)?
- **Configuration Management**: Secrets / URLs hardcoded vs. environment variables?

#### 5. Technology Evaluation
- **Stack Appropriateness**: Is the chosen stack well-suited to the problem domain?
- **Technology Maturity & Community Support**: Are libraries actively maintained?
- **Future Viability**: Migration complexity if a dependency is deprecated?

#### 6. Integration Patterns
- **API Design Quality**: REST conventions, versioning, contract stability?
- **Service Communication**: Synchronous vs. event-driven where appropriate?
- **Circuit Breakers / Retry Logic**: External calls protected?

#### 7. Security Architecture
- **Authentication & Authorization**: Design sound, not bolted on?
- **Secret Management**: No credentials in source code or logs?
- **Data Encryption**: Sensitive data at rest and in transit?
- **Audit Logging**: Security events captured?

#### 8. Data Architecture
- **Data Models**: Normalised where needed, denormalised where performance requires?
- **Consistency Requirements**: Are transactions scoped correctly?
- **Backup & Recovery**: Strategy documented and tested?

#### 9. Technical Debt Assessment
- **Architecture Smells**: God objects, circular dependencies, anaemic domain models?
- **Outdated Patterns**: Legacy approaches that block modernisation?
- **Remediation Priority**: Risk × effort matrix for top findings?

---

## 📋 Output Format

Deliver a structured Markdown report with the following sections:

```markdown
# Architecture Review Report — <Project/Module Name>
**Date**: YYYY-MM-DD | **Reviewer**: Architecture Review Skill | **Scope**: <scope>

## Executive Summary
<2-4 sentence high-level verdict>

## ✅ Architectural Strengths
| # | Finding | Evidence |
|---|---------|----------|
| 1 | ...     | path/to/file.py:L42 |

## ⚠️ Critical Architectural Risks  *(MUST-FIX)*
| Priority | Risk | Impact | Evidence | Recommendation |
|----------|------|--------|----------|----------------|
| P1 | ... | High | ... | ... |

## 💡 Areas for Improvement  *(SHOULD-FIX)*
| # | Area | Suggestion | Effort |
|---|------|-----------|--------|
| 1 | ... | ...        | Low    |

## 🗺️ Remediation Roadmap
1. **Immediate** (sprint 1): ...
2. **Short-term** (1-2 sprints): ...
3. **Long-term** (future quarters): ...
```

---

## 🧭 Framework-Specific Guidance

For this mono-repo (`flask_blogs/`):
- **Planhead & Sudoku**: Verify the Service-Layer pattern is intact — Blueprints must NOT contain business logic.
- **Hippocooking**: Confirm JSON-loading utilities are isolated and locale/recipe IDs are never hardcoded.
- **Nginx Gateway**: Review `nginx_dev.conf` / `nginx_prd.conf` for CSP headers, uWSGI upstream health, SSL config.
- **Docker Compose**: Validate volume mounts, network isolation, and `*_volume/` paths are never deleted.
- **Myosotis**: Check FastAPI service for async correctness and SQLite concurrency safety.

---

## 📁 Resources
- Source subagent: `VoltAgent/awesome-claude-code-subagents` — `categories/04-quality-security/architect-reviewer.md`
- Complementary skill: `general-general-system-integrity-guard` (security + SEO scan)
- Complementary skill: `general-general-code-simplifier` (post-review refactoring)
