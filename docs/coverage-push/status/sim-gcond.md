# sim-gcond status (2026-11-06, machine shutdown)

State: clean. Nothing uncommitted, nothing half-done. All three branches are pushed and their PRs are open. Worktree is on claude/gcond-3 @ bc8ea3f.

Open PRs, stacked in this order (each needs `git merge origin/main`, then a normal push, once the one below merges):
1. #215 `claude/gcond-1b` @ b0e6fbb: quantities (cx_grammar_quantity, _xq fallback, cxq). +108. On grammar-5 (#207).
   The CI converge failure is fixed in b0e6fbb; the newest fast check and parse-diff pass. Its CI pilot-gate run was cancelled, so the lead's Mac gate comment is still awaited.
2. #239 `claude/gcond-2` @ 2375a18: conditions in cx_condlib, "instead" rider, and the lead-approved one-line etb/land_enters context fix in stack.py. +72.
   CI was still pending when last checked.
3. #290 `claude/gcond-3` @ bc8ea3f: "unless" rider and the cx_unless kind (with the AI test). +30. CI not yet checked.

Next step on restart:
- `gh pr view <n> --comments` for #215/#239/#290: read parse-diff and the pilot-gate comment, copy the gate deltas into the PR bodies,
  and fix any FAIL on that PR's branch (then merge it up the stack: gcond-1b -> gcond-2 -> gcond-3).
- `gh issue list -R andjalis/mtg-simulator --label lane:gcond --state open` (none open at shutdown).
- Then a new round, branched from gcond-3 (or main if the stack has merged): "for each" bodies with data['scales'], fixed-referent
  "its power / that card's mana value", then "for as long as <cond>" durations.
Notes: my before/after delta scripts (delta2.py: status of DB cards whose oracle text matches a regex) were in the session
scratchpad, with a detached base worktree at <scratchpad>/base. If it still exists, remove it with `git worktree remove --force`, or
`git worktree prune` if the directory is gone.
Filed outside my lane: #285 (bestow loses abilities), #286 ("Target player draws" parses as you drawing).
Open questions: none.
