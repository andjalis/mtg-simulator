# Remaining card-capability backlog

Reviewed 2026-10-28. **The next thirty requested effects are complete.** All thirty recorded ignored clauses now match, and all 25 associated cards are full template matches. This includes the nine residual clauses from the previous batch.

See the [completion report](results/residual_batch/README.md), [closed tasks](results/residual_batch/completed-backlog.json), and [clause proof](results/residual_batch/completed-clauses.json). Earlier batches and backlog snapshots are historical records, not open work.

Only exact residual ignored text on partial cards appears below. Fully matched cards, matched effects and simplification-only cards are excluded. `~` denotes the source card.

## Current findings

The full offline census covers 34,129 entries: **12,054 full**, 231 with recorded simplifications, 21,844 partial and zero parser errors. This batch improves **137 cards**, including **85 newly full matches**, with zero status regressions. See [every changed card](results/residual_batch/coverage-delta.json) and the [complete census](results/residual_batch/after/README.md).

Existing foundations now include filtered mass moves, graveyard exile, Miracle, Adapt and next-Adapt exceptions, other-land entry predicates, ownership and cast-payment trigger checks, Aura-host end steps, graveyard access restrictions, creature entry/death trigger suppression, mana/nonmana activation restrictions, life and counter locks, layered keyword removal, broader static anthems, and opponents entering tapped. The remaining scopes extend these foundations.

The batch adds 73 behavior tests, retains the previous 67, and records a four-game functional comparison with both pilot assignments. See [validation evidence](results/residual_batch/validation.json). Parser coverage remains separate from complete rules correctness; no pilot-strength claim is made.

## Measured remaining broad families

These overlapping counts are upper bounds, not disjoint gain forecasts or wholly missing systems. Do not sum them.

| Family | Partial cards affected | Potential new full matches |
| --- | ---: | ---: |
| triggered (whenever/when) | 3,364 | 2,072 |
| counters | 2,848 | 1,934 |
| activated abilities | 2,566 | 1,931 |
| graveyard | 2,680 | 1,500 |
| tokens | 2,170 | 1,217 |
| sacrifice | 1,921 | 1,143 |
| exile | 2,070 | 1,041 |
| auras/enchant | 1,042 | 865 |
| can't restrictions | 1,283 | 716 |
| X costs | 1,203 | 685 |
| equipment | 560 | 412 |
| copy effects | 669 | 342 |
| library search | 469 | 244 |
| cost reduction | 368 | 188 |
| +1/+1 static (anthems) | 243 | 133 |

## Verified residual scopes

The order below is an engineering suggestion. The [machine-readable backlog](results/residual_batch/backlog.json) contains the same five scopes and seven exact clauses, re-parsed against the latest database.

### 1. Overload target rewriting and alternative costs

**Cyclonic Rift** (partial):

> Overload {6}{U}

### 2. Scoped keyword removal and gain prohibitions

**Archetype of Imagination** (partial):

> Creatures your opponents control lose flying and can't have or gain flying.

### 3. Shared creature-type counts for dynamic anthems

**Coat of Arms** (partial):

> Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it.

### 4. Color choice bound to team protection

**Brave the Elements** (partial):

> Choose a color.

**Brave the Elements** (partial):

> White creatures you control gain protection from the chosen color until end of turn.

### 5. Linked temporary exile and owner compensation tokens

**Skyclave Apparition** (partial):

> exile up to one target nonland, nontoken permanent you don't control with mana value 4 or less.

**Skyclave Apparition** (partial):

> the exiled card's owner creates an X/X blue Illusion creature token, where X is the mana value of the exiled card.

## Other work classes

Recorded simplifications remain in the census, outside the parser backlog. Verified behavioral defects belong in a separate record with a reproducible scenario. The source-exclusion anthem bug exposed by this batch is fixed and recorded in its completion report.
