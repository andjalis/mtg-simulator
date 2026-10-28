# Graft activated abilities and Warrior's Resolve

All ten requested cards now match every rules-text template in the unchanged local
card database. Matching is separate from complete Magic rules verification.

| Card | Supported behavior |
| --- | --- |
| Aquastrand Spider | Grants reach until cleanup to a creature with a +1/+1 counter |
| Helium Squirter | Grants flying with the same target restriction |
| Plaxcaster Frogling | Grants shroud, preventing subsequent friendly and opposing targeting |
| Sporeback Troll | Creates a regeneration shield using the existing destruction replacement |
| Vigean Graftmage | Untaps a legal counter-bearing creature, including an opponent's |
| Cytoplast Manipulator | Pays mana and taps; control ends immediately if that exact source leaves |
| Cytoplast Root-Kin | Its entry trigger distributes counters to eligible other allies; its activated ability moves one counter onto itself |
| Simic Basilisk | Grants a temporary combat-damage trigger that schedules destruction at end of combat |
| Vigean Hydropon | Cannot attack or block, but retains its normal graft behavior |
| Warrior's Resolve | Grants training and draws at its controller's end step if a currently controlled counter-bearing creature attacked this turn |

These are reusable templates with no card-name checks. Counter-bearing target
restrictions apply during activation and again during resolution. Root-Kin's move
is an effect, not a cost: targeting a creature without counters is legal and moves
nothing. Source departure, self-targeting, and donor death do not duplicate counters.

Source-dependent and until-end-of-turn control effects share ordered bookkeeping.
Ending an older effect leaves a newer effect intact; ending a newer effect reveals
the latest remaining effect. Control changes preserve ownership, counters, tapping
and battlefield identity, remove the creature from combat, and reset its continuous
control tenure. The existing Threaten effect still untaps and enables attacking.
The bookkeeping implements these two duration types, not the entire control layer.

Basilisk's granted trigger expires at cleanup. Once triggered, its delayed
destruction survives the granting or damaging creature leaving; it never follows a
blinked victim to a new battlefield object. Warrior's Resolve uses per-object,
per-turn attack history and checks its intervening condition both when the trigger
is created and when it resolves.

## Validation

`tests/test_graft_abilities.py` adds 44 behavior tests. The focused regression run
also includes the previous counter batch, training/dethrone, regeneration, combat
triggers, identity events and zone/layer actions: 194 tests passed.

`coverage-delta.json` records the ten-card before/after inventory: all ten changed
from partial to full template matches, with zero parser exceptions. This is a
targeted inventory, not a full-database coverage census. `validation.json` records
the completed full-suite, lint and whitespace checks.

The full suite discovered and executed 1,300 tests across 114 modules: 1,299 passed,
one optional test skipped, zero failures or errors. Every discovered test occurrence
matched the execution inventory. Modules ran in four isolated processes, completing
in 178.4 seconds. The temporary runner increased Python's regex compilation cache
capacity to 16,384; it changed no tests or assertions. Lint reported zero findings,
and `git diff --check` passed. Source hashes recorded before the full run were
verified again after it completed.

`smoke.json` records real-database automatic main-phase activations by both
HeuristicAI and BaselineAI for Manipulator and Root-Kin. These functional checks
make no win-rate or pilot-strength claim. Automatic ability valuation now uses the
source's targeting context, preventing Root-Kin from selecting a useless self-move
when there are no other counter-bearing donors.

Commands from the repository root:

```sh
.venv/bin/python -m unittest tests.test_graft_abilities -v
.venv/bin/python -m unittest discover -s tests -t . -v
.venv/bin/python scripts/lint.py
git diff --check
```
