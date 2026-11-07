# sim-abil handoff — STOPPED for shutdown (worktrees: ~/mtg-worktrees/abil, ~/mtg-worktrees/abil-r4)
State: both worktrees clean, everything committed AND pushed (no WIP, no unpushed work).
- abil worktree is on claude/abil-7 (58e7863); abil-r4 worktree is on claude/abil-4 (3da5b06).
Open PRs, none merged yet (sim-review code-approved #212/#214/#216; lead's gate/merge pending):
- #212 claude/abil-3  graveyard returns: sacrifice costs, restrictions, counters; AI worth gate
- #214 claude/abil-4  STACKED on #212 (review commits after 345bf35): general restricted mana + mana adders + AI boost + Pillar/colour fix
- #216 claude/abil-5  bare '{T}: Add N mana of any one color...' real mana sources (simplified) + AI cast test
- #242 claude/abil-7  damage grammar (cx_abil_damage.py); updated twice after review (it = earlier target else card; that creature = earlier target else trigger creature; Javelineer/Deadshot/Halana tests); awaiting sim-review re-review
Filed: issue #295 (mandatory damage triggers fizzle when no creature is killable; AI/engine, lane:abil label).
Next step when resumed: check PR comments/gate (gh pr view <n> -R andjalis/mtg-simulator --comments) and fix any change requests on the same branches;
once #212 merges, in abil-r4: git fetch origin && git merge origin/main (no rebase/force-push) so #214 reads cleanly.
Then new round: gh issue list -R andjalis/mtg-simulator --label lane:abil --state open (counted-full-but-wrong first, 'Fixes #n');
else cost parts (forage, collect evidence, blight, exile this card from hand, sacrifice N other creatures), then activate-only condition atoms.
Rules: lint + own tests only, no local pilot gate, push only when ready, never git clean -x, only repo andjalis/mtg-simulator.
Open question: none.
