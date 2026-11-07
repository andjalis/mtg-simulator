#!/bin/bash
# Merge every open PR labelled lead-approved whose checks are all green, oldest first (squash).
# Usage: merge_batch.sh [wait-seconds]   (sleeps first, so a background run fires one batch later)
sleep "${1:-0}"
cd ~/mtg-simulator || exit 1
merged=() skipped=()
for n in $(gh pr list --label lead-approved --state open --json number -q 'sort_by(.number)|.[].number'); do
  checks=$(gh pr checks "$n" 2>&1)
  if echo "$checks" | grep -qE $'\t(fail|pending)\t'; then skipped+=("#$n:ci-not-green"); continue; fi
  if gh pr merge "$n" --squash >/dev/null 2>&1; then merged+=("#$n"); else skipped+=("#$n:merge-failed(conflict?)"); fi
done
git pull -q --ff-only
echo "batch $(date +%H:%M) merged: ${merged[*]:-none} | skipped: ${skipped[*]:-none} | main now $(git log --oneline -1)"
[ ${#merged[@]} -gt 0 ] && ~/mtg-worktrees/bin/census.sh
