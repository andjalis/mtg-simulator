# Named tokens, quoted abilities and count conditions

This batch preserves supported token names, legendary status, artifact/enchantment
types and single quoted abilities. Supported quoted abilities include parsed
triggers, cannot-block, the existing bounded P/T-per-permanent template and
sacrifice-for-one-mana. Sacrifice mana works while tapped or summoning sick, and
the joint payment planner prevents spending a token twice. Temporary haste expires
at cleanup instead of becoming a copiable keyword. Tapped creation is visible at
the entry-event boundary.

Library-size and controlled-permanent conditions join the shared intervening-if
helper. Counts use the controller's current library/permanents and effective types;
`other` excludes the original source. Conditions are checked at triggering and
again when the complete ability starts resolving.

Direct Oracle fixtures include The Hive, Sliversmith, Pest Summoning, Edgewall
Pack, Nest Invader, Dragonmaster Outcast and Scute Mob. Synthetic Marit Lage
creation tests named legendary tokens; it does not establish support for Dark
Depths. Unknown/multiple quoted abilities, arbitrary activated abilities, delayed
token creation, complex count predicates and alternate-win effects remain gaps.
Quoted mana uses the existing automatic-payment model. Existing copy/layer and
general priority limitations still apply.

`validation.json` records the pinned database, source identities, suite, lint,
mapped scenarios and built-in smoke games. `coverage-delta.json` compares the
whole-database inventory against public main at
`c073b3cd562d3c1781c7658673a9aef6ac020fdf`, following the merge of PR #10.
The database has 34,922 entries; full template matching is distinct from complete
card rules support, which remains unmeasured. Rejecting previously discarded
quoted abilities can correct false full matches even as other cards gain support.

| Template status | Before | After |
| --- | ---: | ---: |
| Full | 8,614 | 8,671 |
| Simplified | 104 | 104 |
| Partial | 26,204 | 26,147 |
| Parse errors | 0 | 0 |

There are 67 promotions and 10 corrected false full matches, a net gain of 57.
Final validation passed 952 tests with one skip, all 136 mapped scenarios, lint,
and 80 built-in smoke games. Seven new direct Oracle fixtures bring the mapped
direct-fixture total to 21; shared capability evidence is not direct testing of
the remaining cards. The branch also merged cleanly with main `a1919d5`, including
the parser split and newer Forge results; 71 focused tests passed on that combined
tree. The full suite and inventory were measured on the batch's pinned base.

The long-running census imported the engine before the tapped-entry correction.
Its embedded scenario run therefore failed the new entry-timing assertion. The
independent fresh-process replay on final code passed all 136 scenarios and is the
scenario evidence used in validation. Parser/classifier inputs did not change
during the census. The compact card counts join direct fixture names to the
inventory and retain the base identity capability shared by remaining entries;
they do not regenerate a complete per-card requirements CSV.

Reproduce with the same database:

```sh
python3 -m unittest discover -s tests -t . -q
python3 scripts/lint.py
python3 scripts/parse_diff.py local --show 5
PYTHONPATH=. python3 results/costs_types_triggers_public/measure.py --out /tmp/named-token-evidence --behavior
python3 -m mtgsim.benchmark --engine builtin -n 20 --out /tmp/named-token-smoke
```

The unchanged measurement helper preloads full-name SQL rows without replacing
builtin/cache overrides and checks 100 definitions against ordinary CardDB lookup.
Full generated inventory CSVs and scenario traces stay local to avoid checking in
large duplicate inventories. The existing parse-diff tool compares name-only
`repr(CardDef)`: its exception check is useful, but its changed-parse count cannot
measure effect-field changes. The paired inventory delta records actual status,
ignored-text and simplification differences.

This work changes no AI policy, Forge measurement, CI workflow or private gauntlet
code and triggers no private gauntlet Actions.
