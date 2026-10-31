# Remaining card-capability backlog

Reviewed 2026-10-29. **The next thirty requested effects are complete.** All thirty recorded ignored clauses now match, and all 25 associated cards are full template matches. This includes the nine residual clauses from the previous batch.

See the [completion report](results/residual_batch/README.md), [closed tasks](results/residual_batch/completed-backlog.json), and [clause proof](results/residual_batch/completed-clauses.json). Earlier batches and backlog snapshots are historical records, not open work.

Only exact residual ignored text on partial cards appears below. Fully matched cards, matched effects and simplification-only cards are excluded. `~` denotes the source card.

## Current findings

The full offline census (2026-10-30 Scryfall DB, [results/database_coverage_2026-10-30-morning](results/database_coverage_2026-10-30-morning/README.md)) covers 35,225 entries: **13,848 full** (39.31%), 327 with recorded simplifications, 21,050 partial and zero parser errors. That census predates the last chonk merge rounds of 2026-10-30 (see below), which promoted several hundred more cards; the next census will re-baseline.

## Chonk session 2026-10-30 — landed and remaining

Landed this session (review the PRs for detail): sac-stat X-quantities, any-player activated abilities, mass threaten, reveal-hand/discard clusters, Rebel-MV and opponent-library searches, dig-bottom and O-ring variants, Beacon shuffle-self, MAYSACSELF payoffs, venture/initiative/dungeons, die rolls (incl. multi-face), phasing, ripple, manifest, demonstrate/amplify, For Mirrodin!/Prepare, energy pay-gates, clash/coin, self-suspend, prevention shields, exact named-card matching, typed-discard filters, exile-from-graveyard costs (cast + activated, X counts), party, initiative/dungeon-complete conds, ETB die rolls, fail-closed `card_matches` vocabulary, AI stay-tapped wiring and a deterministic lethal-setup budget guard.

Remaining, in rough value order (counts from the morning census unless noted):

- **Parser templates whose engine halves have landed** (smol-lane, quick wins): gy-cast family (16 cards — engine kind `gy_cast` is on `chonk/mega-batch6`, pending review), Militia Bugler power-bound dig family (~5), `discard_all_filter` (~12 Amnesia/Persecute/Cabal Therapy), le-batch9's emitted shapes (exile-gy counts, tap-other costs, coven condition, enters-tapped/any-controller data, `spell:<kinds>&cmc>=N`, animate X/X, Shimmer's chosen-type phasing).
- **Engine/foundation work**: tap-lock link consumption (`data["lock"]` → frozen_by links in `kinds/stats.py` tap + untap-step honoring — 16 parser-ready cards); "still a land" permanent/counter/Zendikan animate shapes (~111 partials, `animate_templates.py`); reveal-until dig kind (~14); intensity (20) and specialize (~76) engine state machines; "choose not to untap" continuous-effect pairing for the stay-tapped flags; initiative-any cond; per-opponent sacrifice-choice riders (Acererak residual).
- **Bigger foundations** (out of current scope, need DB data or new engine systems): Attraction/Contraption decks + spellbook (light ranges/spellbook contents are not in `cards.sqlite3` — needs `build_carddb` changes first), Rooms (split permanents), banding (combat damage assignment), cleave and "first spell this game" alt-cost machinery.
- **Known issues**: pre-existing BaselineAI hang in lethal_setup search paths is now budget-guarded (deterministic 100k cap); Treasure Vault's historical `_num('X')` parse raise is fixed on main.

Existing foundations now include filtered mass moves, graveyard exile, Miracle, Adapt and next-Adapt exceptions, other-land entry predicates, ownership and cast-payment trigger checks, Aura-host end steps, graveyard access restrictions, creature entry/death trigger suppression, mana/nonmana activation restrictions, life and counter locks, layered keyword removal, broader static anthems, opponents entering tapped, and Overload. The remaining scopes extend these foundations.

Parser coverage remains separate from complete rules correctness; no pilot-strength claim is made. Earlier batches and their reports are historical records, not open work.

## Cards thread 2026-10-30 (cx_* modules)

Landed in `mtgsim/cx_triggers.py`, `cx_timing.py` and `cx_damage.py` (PRs #77, #79, #82, #84, #88; about 210 cards):
tap-up-to-N with stun counters, entered-this-turn hexproof, enchanted-creature damage links, Noble Purpose, two-card hand
discard, Crabomination, detain, "Cast this spell only ..." windows and "only if" conditions, divided damage (split on
resolution), two-target damage, graveyard-cast riders and non-targeting casts, Ring-bearer conditions, Tiered, attach
Equipment (picked on resolution), counter-an-ability spells and Land Cap-style depletion lands.

Still open from that work: the Peat Bog depletion lands (two-mana tap that sacrifices at zero counters), "until your next
turn" effects (about 120 cards, no common shape; needs a duration that ends at its controller's next turn), planeswalker
targets for "player or planeswalker" damage, Trickbind's "can't activate this turn" rider, and "cast only if an opponent cast
a creature spell this turn".

## Nightly cloud session 2026-10-31 (cx_night_* modules)

Landed in `mtgsim/cx_night_quantity.py`, `cx_night_buffs.py`, `cx_night_multi.py` and one selector tweak in
`permanent_templates.py` (PRs #94 to #99; about 215 cards change parse):
"... equal to <quantity>" damage, life, draw and mill; "<fixed effect> for each <thing>" for pump, damage, life,
draw and mill; Aura/Equipment "gets +A/+B and has <keywords / activated ability / granted host trigger>"; "each
opponent controls" and "target opponent controls" group scopes; "each of two target creatures" and "destroy
two target ..." (one copy per target, flagged `distinct`).

Still open from that work: counts with filters the quantity table does not know ("with flying", "attacking",
"blocking it", "defending player controls"); granted upkeep triggers on Auras; compound target nouns ("creatures
and/or planeswalkers") for multi-target spells; "up to N" is played as N. Per-wording gaps are now long-tail
(the largest single unmatched sentence affects 10 cards), so rounds add cards in tens, not hundreds.

Later PRs the same night: #100 (docs), #101 (damage to a group with "and each", "it deals N damage to each"), #102
(selector-counted quantities such as "the number of attacking creatures"), #103 (player effects sized by X).
Census before and after, full matches of 34,130 cards: 14,664 to 14,869 (+205, measured after #102; #103 adds
about 19 more). Remaining single-sentence gaps are keyword and flavor lines (banding, double team, spellbooks,
attractions), so the next gains need new mechanics or multi-gap frames, not wording entries.

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
