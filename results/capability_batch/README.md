# Database-driven capability batch

This batch selects reusable capability families from the entire local card database,
instead of selecting a list of named cards. The baseline covers all 34,129 entries:
10,778 full template matches, 226 simplified, 23,125 partial, zero parser errors.

`before/` and `after/` contain the complete census, ranked gaps and per-card CSVs.
`selected-families.json` ranks the selected wording families by the number of cards
whose remaining ignored lines fit that family. These are overlapping upper bounds;
this batch implements conservative subsets, not every rule in those families.

## Database-wide result

All 34,129 entries were compared through the same offline CardDB path. Coverage
improves for 1,388 cards; 779 become fully template-matched and two become matched
with recorded simplifications. There are zero status regressions or parser errors.

| Classification | Before | After |
| --- | ---: | ---: |
| Full template match | 10,778 | 11,557 |
| Recorded simplifications | 226 | 228 |
| Partial | 23,125 | 22,344 |
| Parser error | 0 | 0 |

Examples of newly full matches include Acidic Slime, Aether Channeler, Akroma's
Memorial, Aether Shockwave, Aerial Maneuver, Mindless Automaton and Vorel of the
Hull Clade. Changes also reach cards that still have other unsupported text.

## Reusable capabilities

- Permanent selectors combine type intersections or unions with controller, subtype,
  color, tapped/attacking/blocking status, token or legendary status, counters,
  keyword presence, and fixed power/toughness/mana-value bounds. The same selectors
  serve targeting, group effects and static keyword grants. Existing protection,
  shroud, hexproof and resolution-time target checks remain active.
- Counter operations add, remove or double named counters on selected permanents,
  and double every existing counter kind. Group operations select recipients once
  and finish before state-based actions. Named entry counters are also recognized.
- Fixed self-counter costs accept quantities beyond one. Joint payment planning
  reserves these counters from storage mana and from shared counter payments;
  insufficient payments cannot make counters negative. A source can die from
  spending its last toughness counters while its stacked ability still resolves.
- Temporary keyword grants support lists and grouped recipients. Static keyword
  lists use the same selectors and end when their source leaves or loses abilities.
  A finite subtype vocabulary prevents unknown qualifiers and player/host phrases
  from being mistaken for permanent types. Changeling applies only to creature types.
- Quoted temporary triggered abilities reuse the normal trigger parser. Sentence
  splitting respects quotation marks, so a quoted multi-sentence ability stays
  intact. Recipients own the granted triggers; they expire during cleanup, while
  already triggered abilities survive source departure through existing last-known
  snapshots.
- Fully understood permanent-exile sentences use exile rather than the legacy
  destruction approximation. Optional-payment gates are preserved. Both pilots
  recognize the new removal effect and can target indestructible artifacts.

There are no card-name checks. Unknown predicates, quantities, quoted effects,
keyword dependencies, and unsupported group-removal semantics remain visible as
gaps. This does not add a complete natural-language parser or a full layer system.

## Measurements and validation

`coverage-delta.json` lists every changed classification/ignored-text record and
all newly full matches. These figures measure parser coverage, not complete Magic
rules correctness. Full matches can still inherit unrelated engine limitations.

`tests/test_permanent_templates.py` adds 45 regression tests and exercises selector conjunctions, changing
state, ownership, counter payment conflicts, group snapshots, optional exile
payments, granted triggers and both pilots. The former unsupported-land test now
checks actual mana-value-filtered removal because that restriction is implemented.

`smoke.json` records real-database functional checks with HeuristicAI and BaselineAI:
Mindless Automaton automatically spends counters to draw, Acidic Slime chooses a
land, Akroma's Memorial grants its complete keyword list, and Vorel doubles an
artifact's counters. These checks do not measure win rates or pilot strength.
`validation.json` records the complete suite and final source hashes.

The final full run discovered and executed all 1,345 tests across 115 modules:
1,344 passed, one optional skip, zero failures or errors. Test execution IDs exactly
match the discovery inventory. The module-isolated run used four workers and took
281.6 seconds. Lint reported zero findings, and `git diff --check` passed. All source
hashes captured before the final suite were verified unchanged after it finished.
The final integration subset also passed all 97 tests.

Reproduce measurements from the repository root:

```sh
python -m mtgsim.database_coverage --save results/capability_batch/after --progress
python results/capability_batch/measure.py
PYTHONPATH=. python results/capability_batch/smoke.py
python -m unittest discover -s tests -t . -v
python scripts/lint.py
git diff --check
```

The saved censuses use the same offline database and CardDB lookup path. Their
measurement processes only increase Python's regex compilation cache capacity;
they do not change the parser or hide errors. The before snapshot includes all
previous uncommitted card batches.
