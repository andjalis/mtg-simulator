# sim-gplayers handoff (updated 2026-11-06, stopped for machine shutdown)

State: clean. Nothing uncommitted, nothing unpushed; local == origin for all branches. Worktree ~/mtg-worktrees/gplayers is on claude/gplayers-4.

Open PRs:
1. #197 claude/gplayers-1b @43b91a8 (on claude/grammar-5): damage verbs. Approved by review; lead's local gate for this head not seen yet.
2. #208 claude/gplayers-2 @2fa32a9 (on #197 + #222 grammar-7): imperative player verbs, random/whole-hand discards, @ai_value. Burning Inquiry review fix pushed; awaiting re-review + gate.
3. #289 claude/gplayers-3 @7fb26a5 (on #208): power damage, 'it' damage source, policy.damage_amount AI helper. Fixes #261. Awaiting review + gate.
4. #298 claude/gplayers-4 @a377bae (on claude/grammar-5 only): 'target player draws' targets a player. Fixes #286. Awaiting review + gate.

Next step on restart:
- Read gate comments ('<!-- pilot-gate --> Local gate ... for head <sha>') on #197/#208/#289/#298; copy deltas into PR bodies; fix FAILs on the same branch; merge lower branches upward (1b -> 2 -> 3) when one changes, one push per branch per round.
- gh issue list -R andjalis/mtg-simulator --label lane:gplayers --state open (counted-full-but-wrong first).
- Then new coverage: bite wordings ('target creature you control deals damage equal to its power to ...' -> fight_mark + bite) or 'may' player verbs.
Open questions: none.
