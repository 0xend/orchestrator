---
name: pr-reviewer
description: "Staff-level GitHub pull request review for the elsabor repo. Use when asked to review a PR, audit code changes, or provide a full, high-signal review using gh CLI, with focus on correctness, security, performance, architecture, testing, and project standards."
---

# PR Review Workflow

Follow this workflow every time.

1. Confirm context
- Ensure the request is for GitHub PR review via gh CLI.
- If PR number or URL is missing, ask for it.
- If gh auth is missing, ask the user to run `gh auth login`.

2. Gather PR data with gh
- Prefer using `scripts/pr-review-bundle.sh <PR>` to capture a bundle (diff, checks, comments, metadata).
- If the script is unavailable, run the commands below and capture outputs:
  - `gh pr view <PR> --json number,title,author,baseRefName,headRefName,labels,reviewDecision,files,additions,deletions,body,url`
  - `gh pr diff <PR>`
  - `gh pr checks <PR>`
  - If needed, `gh pr view <PR> --comments` for context.
- If file-level context is needed, use `gh pr checkout <PR>` and review the local files.

3. Load repo standards
- Read `AGENTS.md` in the repo root and apply all rules.

4. Review deeply and systematically
- Correctness, edge cases, and data flow
- Security boundaries and input validation
- Architecture and maintainability
- Performance and scalability
- Tests and coverage
- DX and clarity

# Project Standards (Always Enforce)

- Python: Ruff formatting, type hints on all functions, Pydantic for API validation, repository pattern for data access.
- TypeScript: Strict mode, no `any`, use `@/` alias for imports, Tailwind CSS only, SWR for server state.
- Security: No hardcoded secrets, validate inputs at API boundaries, parameterized queries, sanitize data before UI render.
- Testing: New features need tests, bug fixes need regression tests, maintain coverage.
- Architecture: Single responsibility, edit existing files before creating new ones, follow existing patterns.

# Staff-Level Review Checklist

- Correctness: off-by-one, null handling, race conditions, concurrency, retries, idempotency.
- Contracts: API compatibility, schema changes, versioning, migrations.
- Data integrity: transactions, constraints, repository usage, query safety.
- Security: authz/authn gaps, injection, secret leakage, insecure defaults, unsafe deserialization.
- Performance: N+1 queries, unbounded loops, memory growth, large payloads, cache invalidation.
- Observability: logging, metrics, tracing, error surfaces, actionable context.
- Resilience: timeouts, fallbacks, partial failure behavior, retries with backoff.
- UX: error messages, loading states, edge UX paths, accessibility regressions.
- Maintainability: duplication, unclear naming, leaky abstractions, architectural drift.
- Tests: missing unit/integration/e2e, weak assertions, nondeterminism, missing regression.

# Review Output Format

Provide a full audit with findings ordered by severity.

- Summary: 2 to 4 sentences describing overall risk and readiness.
- Findings: List each issue with severity (P0, P1, P2, P3), location, impact, and a concrete fix.
- Tests: Call out missing tests or gaps, and suggest specific tests.
- Questions: Only if required to unblock or resolve ambiguity.

# Quality Bar

- Prefer evidence over speculation. Cite files and lines if available.
- Assume the reviewer is staff-level: highlight architectural drift, long-term maintenance risks, and scaling implications.
- Be firm on standards and security, but acknowledge tradeoffs and offer solutions.
