# sim-static handoff (updated 2026-11-06, before shutdown)
Worktree ~/mtg-worktrees/static, clean, checked out on claude/static-7 (= pushed #294). No WIP or local-only commits. All branches are from main, none stacked.
Open PRs (all reviewer sim-review2; copy the lead's `<!-- pilot-gate -->` delta into each body when it lands):
- #195 claude/static-2: devotion / most-common-colour conditions, devotion quantity, Gods' "isn't a creature". Fix round pushed (Thassa's Rebuff X=0, lead-approved counter hook). Waiting on re-review + gate.
- #213 claude/static-3: static damage prevention (cx_static_prevent, on the cx_shields engine). Waiting.
- #220 claude/static-anthem-fix: priority fix for anthem group words. Gate done (full +4; 2 intended "regressions" explained in the body, see issue #248). Waiting.
- #224 claude/static-4: damage modifiers (double / triple / +N / half). Waiting.
- #230 claude/static-5: chosen colour on entering (Gates, Thriving lands, protection), plus the fix that stops choose-a-colour cards without a mana ability making mana. Waiting.
- #238 claude/static-6: "~ can't attack/block unless <cond>". Waiting.
- #294 claude/static-7: cost_of applies every increase before every reduction (Fixes #258, #263). Waiting.
Next step: run `gh issue list -R andjalis/mtg-simulator --label lane:static --state open`. Open follow-up: #259 chosen-colour anthems (needs #220 and #230 merged). Then attack/block taxes ("unless you pay {N}").
Notes: heavy queue and gh need the sandbox off; make branches with `git switch --no-track -c`; my local `results/pilot_gate/` dirs stay uncommitted.
Parked from review: #296 (chosen-colour protection defaults to white on an empty board; take it with #259).
Open questions: none. Nothing was in progress at shutdown.
