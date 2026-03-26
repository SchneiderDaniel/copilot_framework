---
name: agentic-qa
description: Expert procedural guidance for automated test generation, visual regression, and "reproduction-first" debugging. Inspired by Qodo (CodiumAI).
---

# Skill: Agentic-QA (Lestrade)

Expert procedural guidance for automated test generation, visual regression, and "reproduction-first" debugging. Inspired by **Qodo (CodiumAI)**.

## Overview
This skill enables Lestrade to provide empirical proof for every code change.

## Core Procedures

### 1. Reproduction-First Loop
- For every reported bug:
  - Create a failing test case in `tests/test_[name].py`.
  - Record the failure logs.
  - Hand over to Watson only after the failure is confirmed.

### 2. Automated Test Suite Generation
- For every new service:
  - Generate a full suite of unit tests with Pytest.
  - Cover edge cases (nulls, empty inputs, type errors).
  - Use `sequential-pytest-runner` for validation.

### 3. Visual & UI Verification
- Use **Playwright** to capture screenshots of UI changes.
- Verify Bootstrap responsiveness across desktop/mobile viewports.
- Check DE/EN translation presence in the UI.

## Output Standard
- A "Quality Assurance Report" in Myosotis (`quality_assurance`).
- 100% test coverage for the modified path.
- Verified screenshots of UI changes.
