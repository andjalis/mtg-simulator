# sim-mech handoff (final before shutdown): nothing uncommitted, nothing half-done

Worktrees: ~/mtg-worktrees/mech (claude/mech-fix-nocost checked out) and ~/mtg-worktrees/mech-dev (claude/mech-10 checked out; writes there need the sandbox off; card db is a symlink to mech's).
Never `git clean -x/-X`. I run only lint + my own test modules; gates run on the lead's Mac.

Open PRs, all independent, all pushed and complete, waiting on gate/review:
- #209 no-printed-mana-cost cards not castable (Fixes #279); waiting on lead's local gate for head 52903f4
- #210 freerunning/web-slinging/beam/reinforce/recover/prowl (claude/mech-4; has HeuristicAI tests)
- #218 prepared self targets + hexproof from colour (claude/mech-5; has AI test)
- #219 Spacecraft become artifact creatures at the station threshold (claude/mech-6; Fixes #243)
- #235 Rooms (claude/mech-7; cmc fixed per cast half and on the battlefield)
- #240 bestowed Aura keeps activated abilities (claude/mech-8)
- #262 multi-splice (claude/mech-9; Fixes #251)
- #299 explore with empty library + alt-cost variants keep cost_reduction (claude/mech-10; Fixes #276, #278)

Next step: read the gate/review comments on each PR (gh pr view <n> --comments) and fix any FAIL/changes on the same branch.
After #210/#218/#240 merge, branch from origin/main for: #268 (Beam prefer a nontoken creature; Recover choice via the pay_optional hook; both in cx_mech.py from #210), #270 (check hexproof_from with a recoloured source permanent: set_colors ContinuousEffect, then continuous.refresh; test it), #274 (bestow_face keeps triggers too; needs #240).
Parked (issues exist): #254 Battles/Sieges, #255 Contraptions/Attractions, #256 spellbooks. Low value: #252.
Later bundle idea: gravestorm, champion, cumulative upkeep with two costs, equip/entwine/eternalize with sacrifice/discard costs, specialize, double team, banding.
Open questions: none.
