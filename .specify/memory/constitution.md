<!--
  Sync Impact Report
  ==================
  Version change: N/A → 1.0.0 (initial ratification)
  Modified principles: N/A (first version)
  Added sections:
    - Core Principles (6 principles)
    - Technology Stack & Constraints
    - Development Workflow
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ no update needed
      (Constitution Check section dynamically references this file)
    - .specify/templates/spec-template.md ✅ no update needed
      (no direct constitution references)
    - .specify/templates/tasks-template.md ✅ no update needed
      (no direct constitution references)
    - .specify/templates/checklist-template.md ✅ no update needed
    - .specify/templates/agent-file-template.md ✅ no update needed
  Follow-up TODOs: none
-->

# SharePoint Foundry Agent Constitution

## Core Principles

### I. Clean Code

All source code MUST be readable, well-structured, and self-documenting.

- Functions MUST have a single, clear responsibility and stay under
  50 lines of logic (excluding docstrings and blank lines).
- Every public function, class, and module MUST have a docstring
  describing purpose, parameters, return value, and raised exceptions.
- Naming MUST be explicit and intention-revealing; abbreviations are
  prohibited unless universally understood (e.g., `id`, `url`).
- Dead code, commented-out blocks, and TODO-without-issue references
  MUST NOT be committed to the main branch.
- Imports MUST be grouped: stdlib → third-party → local, separated
  by a blank line, and sorted alphabetically within each group.

**Rationale**: Readable code reduces onboarding time and defect rates.
Code is read far more often than it is written; optimise for the reader.

### II. Minimal Dependencies

The project MUST keep its dependency tree as small as possible.

- Every third-party package MUST be justified in a comment inside
  `pyproject.toml` (or `requirements.txt`) explaining why it is needed
  and why a stdlib alternative is insufficient.
- Transitive dependency count MUST be audited before adding any new
  package; prefer packages with zero or few transitive dependencies.
- The Microsoft Agent Framework Python SDK (`microsoft-agents`) is the
  primary runtime dependency and is exempt from justification.
- Utility libraries that duplicate stdlib functionality (e.g., `six`,
  `pathlib2`, `typing-extensions` on Python ≥ 3.11) MUST NOT be added.
- Pinned versions MUST be used for all dependencies to guarantee
  reproducible builds.

**Rationale**: Fewer dependencies mean smaller attack surface, faster
installs, and fewer breaking upstream changes.

### III. Agent Framework First

All agent and workflow logic MUST be built on the Microsoft Agent
Framework Python SDK.

- No alternative agent frameworks (LangChain, AutoGen legacy,
  CrewAI, etc.) are permitted in this project.
- Agent definitions MUST use the SDK's declarative or programmatic
  agent APIs; hand-rolled LLM orchestration loops are prohibited.
- Model access MUST go through the SDK's model client abstractions
  to keep provider-switching trivial.
- SDK updates MUST be tracked and adopted within one minor version
  of release to stay on supported APIs.

**Rationale**: A single framework eliminates impedance mismatches,
reduces cognitive load, and ensures consistent tool/memory/planning
behaviour across all agents.

### IV. Orchestration Versatility with Durability

The project MUST support all major orchestration patterns offered
by the Microsoft Agent Framework and guarantee workflow durability.

- Supported patterns: sequential, concurrent (fan-out / fan-in),
  Magentic-One (multi-agent collaborative), selector, handoff,
  swarm, and custom graph-based topologies.
- Every workflow MUST be resumable after transient failures; use
  the SDK's durable task / checkpoint primitives for state
  persistence.
- Orchestration selection MUST be driven by the use case; default
  to the simplest pattern (sequential) unless concurrency or
  multi-agent collaboration is demonstrably required.
- Workflow definitions MUST be versioned; breaking changes to a
  workflow schema require a new version identifier.

**Rationale**: Enterprise workloads demand both flexibility in
orchestration topology and resilience against infrastructure faults.

### V. SharePoint-Only Integration

All external data-source integration MUST target SharePoint
exclusively.

- The project MUST NOT include connectors, adapters, or API calls
  to services other than SharePoint (e.g., no Slack, Jira, or
  Salesforce integrations).
- SharePoint access MUST use the Microsoft Graph API with
  least-privilege application permissions scoped to Sites.
- Authentication MUST use Azure Identity (DefaultAzureCredential
  or managed identity) for service-to-service auth — no hard-coded
  secrets or API keys. User-delegation flows (e.g., OBO) MUST use
  MSAL (`msal`) when `DefaultAzureCredential` cannot perform the
  required token exchange.
- All SharePoint data flowing into agent context MUST be sanitised
  and size-bounded to prevent prompt-injection and token overflow.

**Rationale**: Scoping integration to a single platform simplifies
security review, reduces maintenance burden, and keeps the agent's
tool surface predictable.

### VI. Test-Driven Quality

Every feature MUST be accompanied by tests that validate its
behaviour before it ships.

- Unit tests MUST cover all public functions and class methods;
  target ≥ 80 % line coverage per module.
- Integration tests MUST verify agent ↔ SharePoint interactions
  and multi-step workflow orchestrations end-to-end.
- Tests MUST be written (and seen to fail) before the corresponding
  implementation code — Red-Green-Refactor cycle.
- Mocks or fakes for SharePoint responses MUST be maintained in a
  shared fixture directory (`tests/fixtures/`).
- CI MUST block merge on any test failure or coverage regression.

**Rationale**: Automated tests are the primary safety net; they
document expected behaviour and catch regressions early.

## Technology Stack & Constraints

- **Language**: Python 3.11+
- **Agent SDK**: Microsoft Agent Framework Python SDK
  (`microsoft-agents`)
- **SharePoint API**: Microsoft Graph REST API v1.0
- **Authentication**: `azure-identity` (DefaultAzureCredential)
- **Testing**: `pytest` with `pytest-asyncio` for async workflows
- **Linting / Formatting**: `ruff` (lint + format in one tool)
- **Type Checking**: `pyright` in strict mode
- **Package Management**: `uv` or `pip` with pinned
  `requirements.lock`
- **CI**: GitHub Actions
- **Minimum Python Version**: 3.11 (required for `TaskGroup`,
  `ExceptionGroup`, and modern typing features)

Constraints:

- All code MUST pass `ruff check`, `ruff format --check`, and
  `pyright` with zero errors before merge.
- No runtime dependency on Docker; the agent MUST run as a plain
  Python process or Azure-hosted service.
- Secrets MUST be managed via environment variables or Azure
  Key Vault — never committed to source control.

## Development Workflow

1. **Branch**: Create a feature branch from `main` following the
   naming convention `<issue-number>-<short-description>`.
2. **Spec**: Author a feature spec in `specs/<branch>/spec.md`
   using the spec template.
3. **Plan**: Produce an implementation plan validated against this
   constitution's principles (Constitution Check gate).
4. **Implement**: Write failing tests first, then implement to
   green; commit in small, atomic increments.
5. **Review**: Open a pull request; at least one reviewer MUST
   verify constitution compliance, test coverage, and clean-code
   adherence.
6. **Merge**: Squash-merge to `main` after CI passes and review
   is approved.
7. **Release**: Tag releases with semantic versioning; update
   changelog.

Quality gates enforced by CI:

- All tests pass (`pytest`).
- Coverage does not regress.
- Linting and formatting pass (`ruff`).
- Type checking passes (`pyright`).

## Governance

This constitution is the authoritative source of project standards.
It supersedes all other practice documents or informal agreements.

- **Amendments** require a pull request with a clear rationale,
  review by at least one maintainer, and an updated version number
  following semantic versioning (MAJOR for principle
  removal/redefinition, MINOR for new principles or material
  expansion, PATCH for clarifications and typo fixes).
- Every pull request and code review MUST verify compliance with
  the principles defined above; non-compliance MUST be flagged.
- Exceptions to any principle MUST be documented in the PR
  description with a justification and an expiration date or
  follow-up issue.
- Compliance reviews SHOULD occur quarterly to ensure the
  constitution reflects current project realities.

**Version**: 1.0.0 | **Ratified**: 2026-02-07 | **Last Amended**: 2026-02-07
