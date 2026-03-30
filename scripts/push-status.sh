#!/usr/bin/env bash
# Robust status.json push with rebase-conflict recovery.
# Usage: scripts/push-status.sh <key> [--rows N]
#
# Called from GitHub Actions after the dataset update step.
# Handles concurrent pushes from parallel workflows by retrying
# with fresh fetches on conflict.

set -euo pipefail

MAX_RETRIES=5

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

for i in $(seq 1 $MAX_RETRIES); do
  # Clean up any stuck rebase from a previous iteration
  git rebase --abort 2>/dev/null || true

  # Fetch latest remote and surgically reset only status.json
  # (preserves any other uncommitted files like cache files)
  git fetch origin main
  git checkout origin/main -- status.json

  # Apply our status update on top of the latest remote state
  python scripts/update-status.py "$@"
  git add status.json

  # Nothing changed? Done.
  git diff --cached --quiet && { echo "No status change needed"; exit 0; }

  git commit -m "status: $1 updated $(date -u +%Y-%m-%d)"
  git push origin main && { echo "Status pushed (attempt $i)"; exit 0; }

  echo "Push failed (attempt $i/$MAX_RETRIES), retrying..."
  git reset HEAD~1
  sleep $((RANDOM % 5 + 2))
done

echo "::warning::Failed to push status.json after $MAX_RETRIES attempts"
exit 0  # Don't fail the workflow just because status push failed
