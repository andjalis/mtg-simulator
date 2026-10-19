# Decayed, token keyword lists and bounded phase conditions

Base: public main `d846ddf8599c7c302eb07d8e39b6b723686c18d3`, after PR #5
passed GitHub Actions and was merged. This batch adds:

- Decayed's blocking restriction and attack-triggered, one-shot end-of-combat
  sacrifice. Both triggered abilities use the existing stack. Losing the keyword
  afterward, changing control, and leaving/reentry respect the original trigger
  controller and permanent. Entering attacking does not trigger decayed.
- Token keyword lists with commas and a final conjunction. Unknown keywords remain
  visible instead of being silently dropped.
- A small shared helper for hand-size/life-total comparisons, a tapped/untapped
  source, and the absence of creatures with a supported keyword.
- Intervening-if checks that gate the complete ability once when resolution starts.
  Later effects still resolve when an earlier effect changes the condition's state.
  Ordinary conditional effect sentences retain their own checks.

The implementation leaves `cards/parse.py`, AI heuristics, parse-diff tooling, CI
configuration and Forge measurements untouched. The parser integration is a small
hook in `_if_cond`, and the condition implementation lives in `phase_conditions.py`
so it can move with a parser refactor. No private gauntlet workflow was triggered;
its Actions allowance is exhausted until 1 November 2026.

The branch subsequently incorporates public main `14e6b92`, which contains
Claude's local parse-diff command, PR-comment workflow and Node action updates.
Those upstream changes contain no engine or test-source changes; the current
scenario identity is verified again after the merge. The new local preflight was
run before publication and its output is retained as `parse-diff-local.txt`.

`validation.json` records test results, identities and coverage totals.
`coverage-delta.json` records changed inventory statuses and ignored text against
the base. Full generated inventory CSVs and scenario traces are kept locally
instead of checking large duplicate files into the repository. Reproduce with:

```sh
python3 -m unittest discover -s tests -t . -q
python3 scripts/lint.py  # CI-only pyflakes dependency
python3 results/costs_types_triggers_public/measure.py --out /tmp/token-phase-evidence --behavior
```

The measurement helper preloads SQL full-name entries while preserving builtin
and cached overrides, and checks 100 lookups against ordinary CardDB behavior.
The existing parse-diff script is run separately; its name-only `repr(CardDef)`
comparison does not count actual parsed-field changes, so use the inventory delta
for this batch's template changes. Claude owns the separate parse-diff improvements.

The behavior catalog has 116 scenarios across 14 declared capability subsets.
Falcon Abomination, Convalescent Care, Hollowborn Barghest, Jadar and Imaginary Pet are new direct
Oracle fixtures. Synthetic timing and condition cases remain capability evidence.
Full template matching does not establish complete rules support, which remains
unmeasured. A freshly downloaded database may give different totals.

This is not an arbitrary keyword, delayed-trigger or condition language. Devour,
changeling tokens, multiple instances of decayed on one permanent, arbitrary
Boolean predicates, library-size gates and alternate-win effects remain outside
the supported subset. Stack behavior does not add Stifle card templates. Other
combat and ability-layer limitations described by the capability catalog remain.

## Measured result

Final validation: 927 tests passed, one skipped; 116/116 mapped scenarios passed;
80 builtin smoke games completed with verified result/log/source hashes; clean
pyflakes; no parse errors across 34,922 database entries.

Full template matches increased from 8,592 to 8,608 (24.65% of the database).
There are 103 simplified entries and 26,211 partial entries. No previously full
entry was downgraded. The inventory has 23 changed rows, including these 16 new
full template matches:

Convalescence, Convalescent Care, Falcon Abomination, Flip the Switch, Hobbling
Zombie, Hollowborn Barghest, Imaginary Pet, Ivory Crane Netsuke, Jadar, Ghoulcaller
of Nephalia, Nim Abomination, Rotten Reunion, Scalding Tongs, Slaughterhouse Bouncer,
Startle, Thran Quarry and Thumbscrews.

Fourteen database cards now have direct mapped scenario evidence; the other
34,908 rows have shared capability evidence only. These are distinct from the
template-match counts, and complete card rules support remains unmeasured.
