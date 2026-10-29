# Remaining card-capability backlog

Reviewed 2026-10-29. **The next thirty requested effects are complete.** All thirty recorded ignored clauses now match, and all 25 associated cards are full template matches. This includes the nine residual clauses from the previous batch.

See the [completion report](results/residual_batch/README.md), [closed tasks](results/residual_batch/completed-backlog.json), and [clause proof](results/residual_batch/completed-clauses.json). Earlier batches and backlog snapshots are historical records, not open work.

Only exact residual ignored text on partial cards appears below. Fully matched cards, matched effects and simplification-only cards are excluded. `~` denotes the source card.

## Current findings

The full offline census (2026-10-29, [results/database_coverage_2026-10-29](results/database_coverage_2026-10-29/README.md)) covers 34,130 entries: **13,087 full** (38.34%), 258 with recorded simplifications, 20,785 partial and zero parser errors. Unclassified wording still affects 9,874 cards (6,544 would be full if only that wording were matched). The card database was rebuilt from Forge's card scripts because Scryfall was unreachable, so totals differ slightly from the 2026-10-28 census (12,054 full of 34,129).

Existing foundations now include filtered mass moves, graveyard exile, Miracle, Adapt and next-Adapt exceptions, other-land entry predicates, ownership and cast-payment trigger checks, Aura-host end steps, graveyard access restrictions, creature entry/death trigger suppression, mana/nonmana activation restrictions, life and counter locks, layered keyword removal, broader static anthems, opponents entering tapped, and Overload. The remaining scopes extend these foundations.

Parser coverage remains separate from complete rules correctness; no pilot-strength claim is made. Earlier batches and their reports are historical records, not open work.

## Measured remaining broad families

These overlapping counts are upper bounds, not disjoint gain forecasts or wholly missing systems. Do not sum them.

| Family | Partial cards affected | Potential new full matches |
| --- | ---: | ---: |
| activated abilities | 2,508 | 1,934 |
| triggered (whenever/when) | 3,052 | 1,911 |
| counters | 2,741 | 1,905 |
| graveyard | 2,638 | 1,508 |
| tokens | 2,126 | 1,241 |
| sacrifice | 1,805 | 1,104 |
| exile | 2,028 | 1,043 |
| auras/enchant | 945 | 814 |
| X costs | 1,193 | 696 |
| can't restrictions | 1,183 | 681 |
| equipment | 557 | 421 |
| copy effects | 668 | 355 |
| library search | 467 | 250 |
| cost reduction | 364 | 192 |
| +1/+1 static (anthems) | 216 | 122 |

## Verified residual scopes

The order below is an engineering suggestion. The [machine-readable backlog](results/residual_batch/backlog.json) from the previous batch lists five scopes; Overload (Cyclonic Rift) has since been resolved, leaving the four below, re-checked against the 2026-10-29 census.

### 1. Scoped keyword removal and gain prohibitions

**Archetype of Imagination** (partial):

> Creatures your opponents control lose flying and can't have or gain flying.

### 2. Shared creature-type counts for dynamic anthems

**Coat of Arms** (partial):

> Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it.

### 3. Color choice bound to team protection

**Brave the Elements** (partial):

> Choose a color.

**Brave the Elements** (partial):

> White creatures you control gain protection from the chosen color until end of turn.

### 4. Linked temporary exile and owner compensation tokens

**Skyclave Apparition** (partial):

> exile up to one target nonland, nontoken permanent you don't control with mana value 4 or less.

**Skyclave Apparition** (partial):

> the exiled card's owner creates an X/X blue Illusion creature token, where X is the mana value of the exiled card.

## Other work classes

Recorded simplifications remain in the census, outside the parser backlog. Verified behavioral defects belong in a separate record with a reproducible scenario. The source-exclusion anthem bug exposed by this batch is fixed and recorded in its completion report.
