# sim-tokens handoff (updated 2026-11-06, shutdown)

State: all work committed AND pushed; no local WIP. Local == origin for every branch:
tokens-1 e494421 (#191) | tokens-2 1fe4931 (#203) | tokens-3 8cfbb81 (#204) | tokens-4 a911c43 (#205)
| tokens-5 733a615 (#211) | tokens-6 c683b0e (#291). Stacked in that order, all base main.
- #191 token grammar: gate PASS (+133), HeuristicAI tests added; waiting on sim-review "ready" / merge.
- #203 riders, #204 copy tokens: code approved; last gates FAILed only on tests/test_dimir_cards.py, fixed in
  1fe4931 (merged up the stack); new gate results pending for 203/204/205/211/291.
- #205 they/that player + Food-or-Treasure: Vraska HeuristicAI test added; awaiting re-review.
- #211 counts + CDA tokens: awaiting review. #291 old doubling wording, ", then populate", hybrid devotion (Fixes #269).
Worktrees: ~/mtg-worktrees/tokens is on tokens-4. Scratch worktrees r2/r4 lived in /private/tmp (scratchpad) and may
be gone after reboot: run `git worktree prune` in ~/mtg-worktrees/tokens, then recreate as needed (symlink .venv and
mtgsim/data/cards.sqlite3; NEVER git add -A; .venv is in info/exclude).
Next step: read `<!-- pilot-gate -->` comments on 203/204/205/211/291, copy deltas into PR bodies, fix any FAIL on
its own branch and merge up; answer sim-review. When a lower PR merges: `git fetch && git merge origin/main` on the
next branch, push once. Then round 7 (local until ready): "if kicked / N of those tokens instead", "those tokens gain
haste" after copy_perm, X-sized tokens from spell X.
Open: issue #253 (target player/opponent creates) waits on sim-grammar #193's side rule in default_choose_target.
