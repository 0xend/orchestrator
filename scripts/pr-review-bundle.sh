#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: scripts/pr-review-bundle.sh <pr-number|url> [output-dir]"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI is required. Install it and try again."
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run: gh auth login"
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "Error: must run inside a git repository."
  exit 1
fi

PR_REF="$1"
OUT_DIR="${2:-}"
export GH_PAGER=cat

PR_NUM="$(gh pr view "$PR_REF" --json number --jq '.number')"
if [[ -z "$PR_NUM" ]]; then
  echo "Error: unable to resolve PR number from '$PR_REF'."
  exit 1
fi

if [[ -z "$OUT_DIR" ]]; then
  TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
  OUT_DIR="$REPO_ROOT/.pr-review/PR-${PR_NUM}-${TIMESTAMP}"
fi

mkdir -p "$OUT_DIR"

gh pr view "$PR_REF" \
  --json number,title,author,baseRefName,headRefName,labels,reviewDecision,files,additions,deletions,body,url,createdAt,updatedAt,mergedAt,closedAt,commits,statusCheckRollup \
  > "$OUT_DIR/pr.json"

gh pr diff "$PR_REF" > "$OUT_DIR/diff.patch"

gh pr view "$PR_REF" --comments > "$OUT_DIR/comments.txt"

gh pr checks "$PR_REF" > "$OUT_DIR/checks.txt" || {
  echo "Warning: gh pr checks exited non-zero; output may be incomplete." >> "$OUT_DIR/checks.txt"
}

cat <<'README' > "$OUT_DIR/README.txt"
PR review bundle contents:
- pr.json: PR metadata, files, commits, and status checks
- diff.patch: full PR diff
- comments.txt: PR conversation and review comments
- checks.txt: CI/checks status

Tip: add .pr-review/ to .gitignore if you don't want bundles tracked.
README

echo "Saved PR review bundle to: $OUT_DIR"
