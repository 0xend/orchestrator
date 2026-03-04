# AGENTS.md

Operational contract for agents working in this repository.

## Agent Roles

### 1. Planner
- Goal: understand request and produce an actionable implementation plan.
- Must identify impacted files, migrations, and verification steps.
- Must call out security/auth/state-transition impacts when relevant.

### 2. Plan Reviewer
- Goal: validate plan correctness, completeness, and risk coverage.
- Focus areas:
  - auth/authz
  - idempotency
  - task state-machine legality
  - migration/test completeness

### 3. Implementer
- Goal: execute approved plan with minimal, coherent diffs.
- Requirements:
  - maintain backward compatibility unless explicitly requested otherwise
  - update tests for behavior changes
  - keep Docker + local workflows working (`Makefile` commands)

### 4. Code Reviewer
- Goal: detect bugs/regressions and fix or flag them.
- Priority:
  1. correctness and data integrity
  2. security boundaries
  3. operational reliability (containers, startup, migrations)
  4. test adequacy

## Standard Workflow

1. Understand context and impacted surfaces.
2. Make focused changes.
3. Run relevant validation:
   - backend: `make backend-check`
   - frontend: `make frontend-check`
   - full: `make check`
4. Summarize outcomes and residual risks.

## Guardrails

1. Never bypass task ownership checks.
2. Never bypass state transition checks.
3. Never remove idempotency protections from mutating phase endpoints.
4. Never widen tool filesystem/command access without explicit design decision.
5. Never commit secrets, tokens, or machine-local credentials.

## Definition Of Done

- Code compiles and checks pass for touched surfaces.
- Behavior is covered by tests or explicitly documented as a gap.
- Docs/config updated when behavior or workflow changes.
- Changes are understandable without external context.
