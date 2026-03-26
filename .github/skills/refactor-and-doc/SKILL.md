---
name: refactor-and-doc
description: Expert procedural guidance for repository-level "Speaking Code" refactoring and automated Service-Layer documentation. Inspired by Aider and Cursor.
---

# Skill: Refactor-and-Doc (Watson)

Expert procedural guidance for repository-level "Speaking Code" refactoring and automated Service-Layer documentation. Inspired by **Aider** and **Cursor**.

## Overview
This skill enables Watson to maintain high code quality and documentation-as-code.

## Core Procedures

### 1. Speaking Code Refactoring
- **Naming Audit**: Replace generic names (e.g., `data`, `process`) with expressive, domain-specific names.
- **Service Layering**: Identify business logic in blueprints and refactor into `app/services/`.
- **DRY Audit**: Identify and consolidate redundant functions within the mono-repo.

### 2. Automated Docstring Generation
- For every new or modified service function:
  - Add Google-style docstrings (Args, Returns, Raises).
  - Include the "Why" behind complex logic.

### 3. Localization Sync
- Scan files for hardcoded strings and automatically wrap them in `_()` (Babel).
- Trigger `flask-translation-manager` if new strings are found.

## Output Standard
- Self-documenting, clean code.
- Updated `.po` files for DE/EN.
- A "Refactoring Summary" in Myosotis (`learnings`).
