# BDD & Test Pyramid Designer

## Objective
To formulate a comprehensive, robust test plan based on Behavior-Driven Development (BDD) using Gherkin syntax, while strictly adhering to the Test Pyramid strategy.

## Methodology

### 1. Behavior-Driven Development (BDD) via Gherkin
Transform every User Story and Acceptance Criteria into formal BDD scenarios. This ensures clear, executable specifications.
- **Feature**: The high-level functionality being tested.
- **Scenario**: A specific test case or flow.
- **Given**: The initial context, setup, or state.
- **When**: The action, event, or trigger.
- **Then**: The expected outcome, state change, or assertion.

### 2. The Test Pyramid Strategy
Categorize every designed test into the appropriate layer of the Test Pyramid to ensure a balanced, fast, and reliable test suite:
- **Unit Tests (Base - ~70%)**: Fast, isolated tests for individual functions, methods, and service-layer logic. Explicitly design tests around **Boundary Value Analysis** (edge cases) and **Equivalence Partitioning** (grouping inputs).
- **Integration Tests (Middle - ~20%)**: Tests that verify the interaction between different components (e.g., Blueprint controllers calling Services, API endpoint responses, database transactions).
- **UI / End-to-End Tests (Peak - ~10%)**: Slow, brittle, but highly realistic tests (e.g., using Playwright) that simulate a real user in the browser. Limit these strictly to core User Journeys and critical "Happy Paths".

## Output Format
Your final "Test Design" document MUST be structured exactly as follows:

```markdown
### Test Design

#### 1. BDD Scenarios (Gherkin)
*(List all Given/When/Then scenarios derived from the requirements)*
- **Scenario:** ...
  - **Given** ...
  - **When** ...
  - **Then** ...

#### 2. Unit Tests (Pytest)
*(List specific function-level tests. Focus on edges and exceptions)*
- [ ] `test_<module>_<function>_<condition>`: Description of the specific boundary or logic tested.

#### 3. Integration Tests (Pytest)
*(List tests for API endpoints, routing, and database integrations)*
- [ ] `test_<blueprint>_<route>_<scenario>`: Description of the interaction being verified.

#### 4. UI / E2E Tests (Playwright)
*(List the critical browser-based user journeys)*
- [ ] `test_ui_<page>_<journey>`: High-level description of the browser interactions.
```