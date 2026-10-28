# All ten residual roadmap tasks

This batch completes the ten tasks recorded in the previous
[backlog snapshot](../capability_batch/backlog.json). All eighteen listed ignored
clauses now match, and all sixteen example cards are fully template-matched.
[Closed task records](completed-backlog.json) preserve the original scopes and
clauses; [clause-level results](completed-clauses.json) record the resolved gaps.
The [active backlog](../../BACKLOG.md) contains only verified remaining work.

## Coverage result

The same offline database and CardDB path were used for both complete censuses.
Compared with [the previous after-batch census](../capability_batch/after/README.md),
388 cards improve and 283 become newly full template matches. There are no
coverage-status regressions and no parser exceptions. Parser coverage does not
establish complete Magic rules correctness.

| Classification | Before | After |
| --- | ---: | ---: |
| Full template match | 11,557 | 11,840 |
| Recorded simplifications | 228 | 228 |
| Partial | 22,344 | 22,061 |
| Parser error | 0 | 0 |
| Total entries | 34,129 | 34,129 |

[Every changed card](coverage-delta.json) and the
[complete after census](after/README.md) include changes beyond the named examples.
Existing working trigger templates keep their event-specific paths. The new
filtered-trigger parser handles unresolved wording rather than replacing those paths.

## Implemented scopes

| Closed task | Shared implementation and behavioral evidence |
| --- | --- |
| Filtered entry/death triggers | Shared selectors for nontoken and power-bound subjects; grouped entries/deaths per simultaneous batch, independent once-per-turn gates; optional payments; pre-action death-wave characteristics and last-known watchers for simultaneous destruction |
| Quoted activated abilities | Team and Aura-host grants; recipient-bound costs/source references; generic tap mana grants; removal and suppression of grant providers; stacked abilities surviving provider departure |
| Variable amounts | Board maximum mana value, board type counts and own/all-graveyard card-type counts; values fixed at the required entry/resolution boundary |
| Related targets | Same-controller and distinct-object constraints during selection, activation and resolution; fixed/optional counter quantities; no removal when the recipient is illegal and no addition when the donor is illegal |
| Delayed durations | Creature/artifact blinking to the next end step, using physical-card generations and owner control; tokens stay gone; registrations during an end step wait for the next one |
| Graveyard filters | Exact-mana-value single-card targets; optional zero targets; generation-safe hand/battlefield returns and modal selection |
| Subtype sacrifice costs | Existing joint payment planner selects owned battlefield candidates of the required subtype, including changeling and Kindred permanents; no double-use as consumed mana |
| Token-granted abilities | Named-token bodies with supported quoted triggers; literal names protected from source abbreviation; each token owns its independent triggers |
| Aura movement | One/all Aura movement with controller relationships, host-type/control legality and protection; no new entry events and no ownership changes |
| Action restrictions | Active global attacker/blocker limits and zero-attack restrictions; timed player instant/sorcery and nonmana-activation locks through actual action APIs, including cycling, station and graveyard abilities; mana and triggered abilities remain available |

These are reusable mechanic templates with no card-name checks. More complex
variants remain ignored rather than being silently approximated: base power/toughness predicates,
equipment-host grants, once-limited granted-ability
identities, unsupported quantity definitions, variable target allocations,
next-turn durations, multi-card graveyard selectors, token activated/static bodies,
additional Aura host predicates and other action restrictions. The active backlog
lists concrete remaining clauses, not the already implemented subsets.

The public `enter_battlefield_many(player, cards, **kwargs)` entry point groups a
simultaneous instruction. Token creation, multiple copies, and bulk graveyard
returns share that batch path; grouped watchers are queued after all entries and
before the resulting state-based action wave.

The optional `choose_counter_transfer(game, player, donor, recipient, counter,
available)` hook chooses how many counters to move for “any number”; the default
moves all. Explicit targets use the existing spell/activation APIs. Automatic
selection and valuation retain earlier choices while selecting dependent targets;
partially supplied spell targets preserve their original anchors.

## Validation

`tests/test_backlog_roadmap.py` adds 78 behavior tests. The final full run discovers
and executes all 1,423 tests across 116 modules: 1,422 pass and one optional test
skips, with zero failures/errors. Executed test IDs exactly match the discovery
inventory. Lint reports zero findings and `git diff --check` passes. Runtime/test
source hashes recorded before that final run are verified unchanged afterward.

The full run uses four isolated module processes and a temporary Python regex
cache capacity of 32,768; test assertions and parser logic are unchanged. It took
167.9 seconds. Earlier runs found trigger-path interception and missing related-target
planning; both were corrected before this complete final run.

[Real-database smoke scenarios](smoke.json) pass with HeuristicAI and BaselineAI
across all ten scopes, including automatic Bioshift targeting, Abiding Grace modal
selection, subtype sacrifice activation and Aura movement. These functional
comparisons make no win-rate or pilot-strength claim.
[validation.json](validation.json) records source/data hashes and module outcomes.

Reproduce from the repository root:

```sh
python -m mtgsim.database_coverage --save results/roadmap_batch/after --progress
python results/roadmap_batch/measure.py
PYTHONPATH=. python results/roadmap_batch/smoke.py
python -m unittest tests.test_backlog_roadmap -v
python -m unittest discover -s tests -t . -v
python scripts/lint.py
git diff --check
```

Use a fresh census directory for subsequent batches, preserving this report as history.
