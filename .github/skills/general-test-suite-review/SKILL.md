---
name: general-test-suite-review
description: >
  Audits a project's test suite for integrity, quality, and trustworthiness. Detects the critical
  anti-pattern of "test tuning" — where agents or developers modify test assertions, expected values,
  or skip/xfail markers to make failing tests pass instead of fixing the production code. Produces a
  structured report with a Test Integrity Score, tuning suspects, coverage gaps, and improvement
  recommendations. Use when asked to "review the tests", "audit the test suite", "check test quality",
  "are the tests trustworthy?", or after a Developer phase to guard against test corruption.
  Inspired by the 18 k-star VoltAgent/awesome-claude-code-subagents collection (model: opus).
---

# Skill: general-test-suite-review

> **Source**: Inspired by [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (18 k ⭐) — `categories/04-quality-security/qa-expert.md` + `categories/04-quality-security/test-automator.md` + `categories/04-quality-security/code-reviewer.md`

Test suite integrity audit skill. Detects test-tuning anti-patterns (tests adapted to pass broken code), assesses coverage quality, assertion meaningfulness, and test isolation. Produces an actionable report the team can act on immediately.

---

## 🎯 Trigger Conditions

Invoke this skill when the user asks to:
- "Review the tests" / "Audit the test suite"
- "Are the tests trustworthy?" / "Check test quality"
- "Did the agent tune the tests?"
- "Test integrity review" / "Test health check"
- After any Developer phase where a test failure was reported and then silently disappeared

---

## 🚨 Primary Mission: Detect Test Tuning

**Test tuning** is the critical anti-pattern where, instead of fixing broken production code, tests are modified to accept the broken output. This produces a green CI pipeline with wrong behavior.

Common tuning signatures to hunt for:

| Tuning Pattern | Example |
|---|---|
| Hardcoded expected values changed to match wrong output | `assert result == "wrong_value"` |
| Assertions weakened or removed entirely | `assert result is not None` replacing `assert result == expected` |
| Tests skipped or marked xfail without justification | `@pytest.mark.skip`, `@pytest.mark.xfail` added recently |
| Exception no longer asserted | `pytest.raises(ValueError)` removed or commented out |
| Tolerance/epsilon inflated | `assert abs(result - expected) < 1000` instead of `< 0.01` |
| Mock return values changed to match broken code | `mock.return_value = broken_output` |
| Test scope narrowed to exclude broken cases | Parametrize list trimmed |
| Assert replaced with print/log | `print(result)` left where `assert` was |

---

## 🔍 Review Process

### Phase 1 — Test Suite Discovery

1. Use `glob` to locate all test files: `tests/**/*.py`, `**/test_*.py`, `**/*_test.py`.
2. Identify the test framework in use (pytest, unittest, nose, jest, etc.).
3. List all test modules and their target production modules.
4. Check for CI configuration (`pytest.ini`, `setup.cfg`, `pyproject.toml`, `.github/workflows/*.yml`) to understand what runs in CI.

### Phase 2 — Test Tuning Detection  *(Highest Priority)*

For each test file, perform the following systematic checks. Cite **specific file paths and line numbers** as evidence.

#### 2a. Skip / XFail Marker Audit
- Search for all `@pytest.mark.skip`, `@pytest.mark.xfail`, `unittest.skip`, `xit(`, `test.skip(`.
- **Flag any marker added without a linked issue or expiry condition.**
- A skip without a reason is a tuning red flag.

#### 2b. Assertion Weakness Analysis
- Locate all `assert` statements. Check for:
  - `assert True` / `assert 1 == 1` — meaningless tautologies.
  - `assert result is not None` where a specific value should be checked.
  - `assert len(result) > 0` instead of `assert len(result) == expected_count`.
  - `assert result` (truthy check) instead of `assert result == expected`.
- **Flag assertions that cannot distinguish correct from incorrect behavior.**

#### 2c. Hardcoded Expected Value Suspicion
- For numerical assertions, check if expected values look like they were reverse-engineered from broken output (e.g., suspiciously round numbers that don't match documented requirements).
- Cross-reference expected values against specification, docstrings, or comments.

#### 2d. Exception Assertion Audit
- Search for `pytest.raises`, `assertRaises`, `with self.assertRaises`.
- **Flag any location where an exception was previously expected but the assertion has been removed or commented out.**
- Check git blame or comments for "removed" notes if possible.

#### 2e. Mock Integrity Check
- Locate all `mock.patch`, `MagicMock`, `unittest.mock`, `monkeypatch`.
- **Flag mocks that return values which bypass the actual logic under test.**
- A mock that returns a pre-cooked correct answer from a broken function is a tuning mechanism.

#### 2f. Parametrize Completeness
- For `@pytest.mark.parametrize`, check if the parameter list covers edge cases:
  - Empty inputs, zero, negative numbers, None, empty strings, max values.
  - **Flag parametrize lists that seem suspiciously short or missing obvious edge cases.**

### Phase 3 — Coverage Quality Assessment

#### 3a. Test-to-Production Mapping
- For every production module (service, utility, model), verify a corresponding test module exists.
- **Flag production modules with zero test coverage.**

#### 3b. Happy Path vs. Error Path Balance
- Count test functions testing the happy path vs. error/edge case paths.
- Healthy ratio: at least 1 error-path test per 2 happy-path tests.
- **Flag modules where all tests only test success scenarios.**

#### 3c. Test Isolation
- Check if tests use shared mutable state (class-level variables, module-level fixtures that are mutated).
- **Flag tests that depend on execution order.**
- Look for missing `teardown` / `autouse` fixture cleanup.

#### 3d. Integration vs. Unit Balance
- Classify tests as unit (mocked dependencies) vs. integration (real dependencies).
- **Flag test suites that only have integration tests** — they are slow and often skipped.

### Phase 4 — Test Code Quality

#### 4a. Test Naming Clarity
- Test function names should describe the scenario: `test_<unit>_<scenario>_<expected_result>`.
- **Flag tests named `test_1`, `test_it`, `test_func` — unreadable and unmaintainable.**

#### 4b. Arrange-Act-Assert Structure
- Each test should have a clear setup, one action, and assertion(s).
- **Flag tests with multiple unrelated actions and assertions (testing too much at once).**

#### 4c. Test Duplication
- Look for copy-pasted test logic that should be extracted into parametrize or fixtures.

---

## 📋 Output Format

Deliver a structured Markdown report with the following sections:

```markdown
# Test Suite Review Report — <Project/Module Name>
**Date**: YYYY-MM-DD | **Reviewer**: Test Suite Review Skill | **Scope**: <scope>

## 🏆 Test Integrity Score: X / 10

| Dimension | Score | Assessment |
|-----------|-------|------------|
| Tuning Resistance | X/10 | No evidence of tuning / Minor suspects / CRITICAL |
| Assertion Quality | X/10 | Strong / Weak / Tautological |
| Coverage Completeness | X/10 | Full / Gaps present / Major gaps |
| Test Isolation | X/10 | Isolated / Shared state / Order-dependent |
| Naming & Structure | X/10 | Clear / Inconsistent / Unreadable |

## ⚠️ CRITICAL: Suspected Test Tuning  *(Must investigate immediately)*
| # | File | Line | Pattern | Risk |
|---|------|------|---------|------|
| 1 | tests/test_foo.py | L42 | Assertion weakened | HIGH |

> ✅ No tuning detected  *(use this row if clean)*

## 🔴 High-Priority Issues  *(MUST-FIX)*
| Priority | Issue | File | Evidence | Recommendation |
|----------|-------|------|----------|----------------|
| P1 | ... | ... | ... | ... |

## 🟡 Medium-Priority Issues  *(SHOULD-FIX)*
| # | Issue | File | Suggestion |
|---|-------|------|-----------|
| 1 | ... | ... | ... |

## ✅ Test Suite Strengths
| # | Strength | Evidence |
|---|----------|----------|
| 1 | ... | path/to/file.py:L10 |

## 🗺️ Remediation Roadmap
1. **Immediate**: Investigate all tuning suspects — verify against production code behavior.
2. **Short-term**: Add missing edge-case tests for flagged modules.
3. **Long-term**: Enforce assertion linter / mutation testing in CI.
```

---

## 🛡️ Anti-Tuning Protocol for Agent Workflows

When this skill is used to guard the Developer → Auditor handoff, enforce the following rules:

### Rule 1 — Tests Are Contracts, Not Targets
> Tests define the *expected* behavior of production code. **If a test fails, the production code is wrong. The test is the ground truth.**

### Rule 2 — Evidence of Regression Required
> If an agent removes or modifies a test assertion, it MUST provide:
> 1. The original requirement that justified the old assertion.
> 2. A documented change to the requirement that justifies the new assertion.
> 3. A link to the issue or PR where this change was approved.
> Without these three items, the modification is classified as tuning and **MUST be reverted**.

### Rule 3 — Failing Is Informative, Passing Is Not
> A test that always passes — regardless of what the production code does — has zero value. When reviewing, ask: *"Would this test catch a regression if I broke the code it tests?"*

### Rule 4 — Skip Markers Expire
> Any `@pytest.mark.skip` or `@pytest.mark.xfail` MUST include a reason and a linked issue. Markers without issues are deleted on the next audit cycle.

---

## 🧭 Framework-Specific Guidance

For this mono-repo (`flask_blogs/`):

- **Planhead & Sudoku Services**: Tests MUST assert the actual calculated output value, not just that a value was returned. Verify service tests in `flask_planhead/tests/` and `flask_sudoku/tests/`.
- **Hippocooking**: JSON-driven content tests should assert the exact structure and values loaded, not just `len(result) > 0`.
- **ForestRAG**: Run tests from `forestrag/` with `.venv\Scripts\python -m pytest tests -q`.
- **Translation Pipeline**: If translation tests exist, verify they assert exact translated strings, not just that the translation key resolves.

---

## 📁 Resources
- Source subagents: `VoltAgent/awesome-claude-code-subagents` — `categories/04-quality-security/qa-expert.md`, `test-automator.md`, `code-reviewer.md`
- Complementary skill: `general-general-agentic-qa` (test generation)
- Complementary skill: `general-general-bdd-test-designer` (test design)
- Complementary skill: `general-general-sequential-pytest-runner` (test execution)
- Complementary skill: `general-architecture-review` (structural audit)
