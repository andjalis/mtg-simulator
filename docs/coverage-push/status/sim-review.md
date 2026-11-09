# sim-review handoff (stopped 2026-11-09, end of day)
Role (since 2026-11-09): the only PR reviewer, all lanes. For grammar PRs (sim-grammar, sim-gcond, sim-static) also sample 10-15 newly full cards against Oracle text.
Local state: worktree ~/mtg-worktrees/review is clean, detached on origin/main (52b84d4). No WIP, nothing to push (reviewers never push). Local branches pr-92/pr-237 were deleted (git printed a config-lock warning; if `git branch` still lists them, delete them).
Note: inside the sandbox `gh` fails (TLS/x509 error), so gh/herdr calls need to run unsandboxed.

Open PRs without lead-approved at stop (oldest first): #92, #237, #305, #306, #307, #308, #309, #310.

Done today:
- #237 (grammar-12, prohibitions; #236 is already merged so the whole diff vs main is the PR): CHANGES NEEDED, comment posted, sim-grammar told.
  Bug: Render Silent counts full but "Its controller can't cast spells this turn" bans no one. cx_grammar.players() (mtgsim/cx_grammar.py:749-753) gets the countered StackItem as prev and returns []. Fix: handle a StackItem prev (prev.controller) and add a test with the real card.
  Checked OK: ~25 cards (static/this-turn bans, "other than ~" targets, "those creatures" group extension, "you <imperative>", animate-prev, power-conditioned untap). Gate PASS +34.
  Next: when sim-grammar reports back, re-review only the delta and read the new gate comment.
- #92 (docs, the user's own AGENTS.md de-duplication, not from a lane): diff read, merges cleanly, the removed content exists in README/CONTRIBUTING (except an `assess.py` row). NO COMMENT POSTED YET.
  One risk to state: AGENTS.md is auto-loaded into every agent's context and README is not, so agents lose the layout table. The owner should decide; send it to the lead with that note.

Not started: #305-#310 (issue-fix PRs from 2026-11-08). #305 has pilot-gate FAILURE: read its gate comment first; a FAIL goes back to the author.
Next step on restart: post the #92 note and ping the lead; then review #305 -> #310 in order; re-review #237 when it's fixed.
Issues filed today: none.
