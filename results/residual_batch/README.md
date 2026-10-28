# Next thirty residual effects

This batch implements thirty effects selected from freshly re-parsed partial
cards. The [request snapshot](requested-backlog.json) records each original
ignored clause. All thirty clauses now match, and **all 25 associated cards have
no ignored text or recorded simplifications**. This includes all nine clauses
remaining after the previous batch. [Closed task records](completed-backlog.json)
and [clause-level results](completed-clauses.json) preserve the selection and proof.

## Shared rules

The implementation extends reusable selectors and event/zone boundaries rather
than identifying cards by name:

- Filtered mass destruction and graveyard-to-hand returns, all-creature bounce,
  regeneration riders, all/targeted graveyard exile and player-chosen exile.
- Other-land subtype entry conditions, ownership thresholds checked both when a
  trigger fires and when it resolves, unpaid-spell triggers, and enchanted-host
  controller/end-step/attack-history checks.
- Adapt and consumable next-Adapt exceptions; Miracle reveal choice, first-draw
  checks, a triggered casting window, alternate payment and physical hand references.
- Opponent-only graveyard replacements and graveyard/library entry and casting
  restrictions. A prevented entry leaves the physical card in its original zone,
  preserving references and avoiding spurious zone-leave events. Older handlers
  that remove before entering are handled at the shared entry boundary.
- Creature entry/death trigger suppression, including simultaneous entry/death
  snapshots and sources leaving in the same death wave. Noncreature entry triggers,
  replacement effects and actual death bookkeeping remain independent.
- Creature activation restrictions including mana abilities, artifact/creature
  restrictions with mana exceptions, and gates on general abilities and Equipment.
- Life-total locks, legality of life payments, global player/permanent counter
  restrictions, controller-scoped poison/negative-counter prevention, and layered
  keyword removal that respects later explicit grants.
- Opponent, token, nontoken and global-color anthems, keyword riders, and type-union
  rules making opponents' new permanents enter tapped.

Static providers are indexed and rechecked for live suppression. Entry, departure
and card changes invalidate the index; ordinary permanents avoid repeated ability
checks. Regression cases cover changed cards and converted land abilities.

## Existing behavior corrected

The Elesh Norn scenarios exposed a previously template-matched friendly anthem
being parsed as a creature subtype named `Other`. Shared selectors now interpret
“other creatures” as a source-exclusion predicate. This is a behavioral correction,
not an additional parser todo or a thirty-first selected effect.

Two older Mystic Sanctuary tests now supply three supporting Islands. Their
identity and trigger-resolution assertions are retained; they no longer rely on
its previously ignored entry condition.

## Complete coverage and test result

The same canonical offline CardDB path compares all **34,129 cards** with the
previous census. **137 cards improve**, including **85 newly full
matches**, with zero coverage-status regressions and zero parser errors.

| Classification | Before | After |
| --- | ---: | ---: |
| Full template match | 11,969 | 12,054 |
| Recorded simplifications | 229 | 231 |
| Partial | 21,931 | 21,844 |
| Parser error | 0 | 0 |

The final full run executes **1,563 tests** across 118 modules: **1,562 pass**
and one optional test skips, with zero failures or errors. Discovered/executed IDs
match exactly. Source hashes recorded before that run are verified unchanged.
The full run took 217.1 seconds. Lint reports zero findings and whitespace
checks pass. Provider-index regression cases and the four-game comparison preserve
behavior while avoiding repeated checks of unrelated permanents.

## Validation

The batch adds **73 behavior tests** in `tests/test_residual_batch.py`, using saved
Oracle fixtures independent of the database. The complete census, full-suite
inventory, source hashes and outcomes are recorded in [validation.json](validation.json)
and [coverage-delta.json](coverage-delta.json). Parser matching alone is not a
claim of complete Magic rules correctness or every variant in a mechanic family.

[Policy smoke results](policy-smoke.json) record four seeded games with the same
deck and both HeuristicAI/BaselineAI assignments. Both pilots also plan and cast
the filtered board wipe in a behavior scenario. The static-provider index preserves
all four seeded outcomes and turn counts. These are functional comparisons, not
win-rate estimates or pilot-strength claims.

Reproduce the focused checks with:

```sh
.venv/bin/python -m unittest tests.test_residual_batch tests.test_advanced_batch -q
.venv/bin/python scripts/lint.py
```

Full validation uses four isolated module processes, a temporary Python regex
cache of 32,768 and an exact comparison of discovered/executed test IDs (including
duplicate occurrences). The production cache and test assertions are unchanged.

The [active backlog](../../BACKLOG.md) contains only freshly verified residual
clauses. The completed snapshot is historical and is not open work.
