# sim-trig handoff (updated after graveyard-heads commit)
Worktrees: ~/mtg-worktrees/trig (branch claude/trig-2), ~/mtg-worktrees/trig-b (trig-3/4/5; .venv there is a symlink to ../trig/.venv, never stage it; stage explicit paths only).
Open PRs, stacked order (all base main, none merged yet except #184):
- #198 claude/trig-2: 'when that creature dies this turn' watcher (+HeuristicAI test). Code approved.
- #201 claude/trig-3 (on #198): events surveil/explores/coin flip/life loss/player damage, per-blocker blocked_by. Fixes #245. .venv untracked (132a1a7).
- #221 claude/trig-4 (on #201): attack-with heads, Aura upkeep-of-controller heads, game.attackers cleared at end of combat (Fixes #244), P/T counters, day/night/phase/dice/exert/play-or-cast heads. .venv untracked (a74a765).
Local only (NOT pushed): claude/trig-5 (on trig-4), commit 'Graveyard-arrival heads' = card_to_gy event in engine/turns.py zone_arrived + gy_head/gy_match in cx_trig_events.py + tests/test_cx_trig_graveyard.py; ~15 cards parse full by local scan. Tests + lint pass.
Next: read CI/local gate comments on #198/#201/#221 (gh pr view N -R andjalis/mtg-simulator --comments) and fix FAILs on the same branch; then push trig-5 and open PR (stacked on #221, 'review commits after a74a765') once ready; add self-graveyard heads ('~ is put into your graveyard from ...') and 'N or more counters put on' as further heads for size.
Open issues (lane:trig): #250 reflexive payoff 'it/that creature' + targets chosen after the action (follow-up). #245/#244 fixed in the PRs above.
Open questions: none. Note #284 (simplify) edits the same day/night hook condition in engine/battlefield.py as #221 ('starts_day'); whichever merges second keeps both.
Known gap: Faebloom Trick 'tap target creature an opponent controls' can target own creature (shared wording file core.json, audit P6, lead has it).

## FINAL state at shutdown
All work committed; nothing uncommitted in trig or trig-b. trig-b is on claude/trig-5 (tip 7d98b93, local only, not pushed): complete and tested, PR not yet opened.
Exact next step: (1) read gate comments on #198/#201/#221 and fix FAILs on the same branch; (2) git fetch origin && git merge origin/main on trig-5 (and trig-4 if #201/#198 merged), rerun tests/test_cx_trig_graveyard.py + lint, push trig-5 and open the PR stacked on #221 (review only commits after a74a765) with the delta from the gate comment.
