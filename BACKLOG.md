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

Still open from that work: "until your next
turn" effects (about 120 cards, no common shape; needs a duration that ends at its controller's next turn), planeswalker
targets for "player or planeswalker" damage, Trickbind's "can't activate this turn" rider, and "cast only if an opponent cast
a creature spell this turn".

## Until-next-turn thread 2026-10-31 (cx_next_turn)

Landed in `mtgsim/cx_next_turn.py` (about 65 cards newly fully matched, about 230 change parse): "until your next
turn" durations (the end-of-turn reading, extended to the controller's next turn on resolution), can't
attack/block/activate locks, filtered group keyword grants, base P/T, player flags (hexproof, protection from
everything, life lock, damage prevention, can't be attacked, attack tax, no maximum hand size, spell tax, sorcery
flash), and real planeswalker targets for "target player/opponent or planeswalker" damage.

Still open from that work: copy effects until your next turn (Shapesharer, Volrath, Taskmaster), "whenever ..." delayed
triggers bounded by the duration (Don't Move, Vraska the Unseen, Jace), name locks (Reflector Mage), animations that last
until your next turn, "the player or planeswalker it's attacking" damage, and Archenemy schemes.

## 2026-10-31: ladder-pool cleanup, domain quantities, play weighting

Verge and Bastion/Lair lands now gate their second colour on a matching land type (or a basic / entering this turn);
"counter target spell with mana value N or greater/less"; "return target spell or permanent/creature to its owner's
hand"; "Domain —/Vivid —" prefixes; quantities for basic land types, colours among permanents/lands and differently
named lands. Census after: 15,038 full of 34,130 (44.06%). `mtgsim/play_weights.py` builds weights from MTGJSON
(`edhrecRank`, MIT licence; the host is blocked in cloud sessions, so download `AtomicCards.json.gz` locally) or from
the rank-pool decks, and `database_coverage --weights FILE...` ranks gaps by the play weight they unlock.

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

Second and third nights (2026-10-31 continuation, 2026-11-01): #105 (static maximum hand size modifiers), #106 (untap a
counted number of lands), #127 (lands that enter tapped unless you control a legendary creature). Census on 2026-11-01
after the daytime batches (`results/night_2026-11-01/`): 16,984 of 34,130 cards full, 385 simplified, 16,761 partial.
The largest single-sentence gap is 11 cards ("if it shares a creature type with ~, you may reveal it"), then banding,
attractions, spellbooks and double team at 8 to 10. The nightly lane now yields under 10 cards per PR; the remaining
gain is in the daytime multi-gap frames, so this lane should pick specific mechanics (flashback-cost-equals-mana-cost,
"cast as though it had flash if you pay {2} more", suspect) rather than wording sweeps.

Fourth night (2026-11-04): #130 (suspect), #133 (kinship), #134 (change the target of target spell with a single
target), #135 (Lair lands: sacrifice unless you return a non-Lair land), #136 (draw-step "that player draws an
additional card" and "return that card to the battlefield under your control" for dying and blinked creatures).
Census on 2026-11-04 (`results/night_2026-11-04/`): 17,113 of 34,130 full. Left from that census: banding, attractions,
spellbooks, double team, "you may flip it", commander free-cast, Divert-style "unless its controller pays {2}"
counters, and Lim-Dul / Athreos style death triggers whose context is a player or a counter marker.

Fifth night (2026-11-05): #140 (flip cards: "you may flip it"), #141 ("You control enchanted permanent" and goaded
Auras read as "attacks each combat if able"), #142 ("You gain life equal to that card's mana value" for returned and
revealed cards). Census on 2026-11-05 (`results/night_2026-11-05/`): 17,154 of 34,130 full, 385 simplified, 16,591
partial. The largest single-sentence gaps are still banding (13 cards), attractions (18), spellbooks (15), double team
(18) and prepared (12), each needing a new mechanic; "end the turn", "you have shroud" and the stand-alone "untap them"
need engine support first.

Sixth night (2026-11-06): #144 ("You have shroud" as a player rule that also blocks your own targeting) and #145 ("End
the turn": exiles the rest of the stack, skips the remaining phases, 7 cards). Recorded simplification: Glorious End's
"at the beginning of your next end step, you lose the game" reuses the existing next-end-step delay, so it fires at the
next end step of either player, one turn early when cast on your own turn.
Also that night: #147 (Divert: redirect unless the spell's controller pays {N}), #148 ("Creatures you control ... Untap
them." rewritten to untap all your creatures; a global "untap them" wording was rejected because it changed nine cards,
including Great Oak Guardian and Leo's Guidance, where "them" means other creatures), #149 (counterspell taxes: nonartifact
and creature-or-planeswalker spell filters, and "{1} for each card in your graveyard / card in your hand / creature you
control / artifact you control" counted at resolution; 10 cards) and #150 (Gustcloak "untap it and remove it from combat"
and "you may have it deal N damage to any target"; 9 cards). Recorded simplification: Jund Sojourners' "When you cycle ~
or it dies" keeps only its "dies" half. Later the same night: #152 ("If ..., you may draw a card. If you do, discard a card." as
one conditional `loot`; the unconditional wording was left on the pay gate after a first version changed 26 cards),
#153 (static "You may cast sorcery spells as though they had flash"; 4 cards) and #154 (more tax counts: mana value,
"for each Wizard on the battlefield", "plus an additional {1} for each Faerie you control", blue permanents). #154 also
fixed a rules error in #149: a "for each" tax that totals zero means the controller pays nothing and keeps the spell,
not that it is countered. Then #156 ("deals damage equal to its power to each opponent"; "it" is the trigger's creature),
#157 (static "You may cast spells as though they had flash") and #158 ("deals damage to target player equal to the number
of cards in that player's hand"; 5 cards, Runeflare Trap's alternative cost and Toil // Trouble's Fuse stay unsupported).
Then #160 (choose-then-destroy edicts, 2 cards), #161 ("You can't lose the game and your opponents can't win the game"
as a `cant_lose` flag checked at the life/poison check, the empty-library draw and "you lose the game" effects; 3 cards)
and #162 ("All creatures attack each combat if able" and the opponents-only wording; 5 cards). Abyssal Persecutor ("you
can't win ... opponents can't lose") was left alone: with no way for the AI to get rid of it the game would stall.
Then #164 ("You gain life equal to the damage dealt this way": `deal_damage` records `game.last_dealt`, reset at every
stack resolution; Syphon Soul and Brightflame match the sentence but keep their damage clause unsupported), #165
("Counter target spell that targets a permanent you control", a `targets_mine` counter filter) and #166 ("Each player
may discard their hand and draw seven cards" as `wheel_all`, always taking the "may"; Ali from Cairo's "damage can't
reduce your life below 1" as a `life_floor` flag). Then #168 ("destroy target artifact or enchantment that player controls", 4 cards), #169 ("discard a card at random" as an
additional cost, 3 cards), #170 ("exile up to N target cards from a single graveyard" and "shuffle up to N target cards
from their graveyard into their library": two new kinds, `exile_gy_n` and `shuffle_gy_n`; 16 cards) and the doomed extra
turn ("Take an extra turn after this one. At the beginning of that turn's end step, you lose the game": `extra_turn`
with `doomed`, the loss is checked just after that turn instead of at its end step trigger; 4 cards).
Still open: "Spells your opponents cast that target ~ cost {2} more"
(needs a cost step after targets are chosen).
Still open from the census: counter taxes by devotion, basic land types and party size, and
"can't attack unless you pay ..." costs.

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

## Flash and flashback batch 2026-10-31 (`cx_night_flash.py`)

Landed: "gains flashback until end of turn" for every instant and sorcery in the graveyard (Past in Flames, Backdraft Hellkite), "cast as though it had flash if you pay {N} more" (14 cards), and Peat Bog-style depletion lands (five lands, two mana per tap, sacrificed at zero counters).

Still open: conditional flash ("if you control a Faerie"), "next spell can be cast as though it had flash", non-mana flashback costs ("Flashback—Pay 3 life"), static "has flashback" grants (Lier, Otaria).

## Flashback costs batch 2026-10-31 (`cx_night_flash.py`)

Landed: flashback with a single sacrifice (Lava Dart, Cabal Therapy's cost), Lier's static flashback grant, and the Tainted Adversary token wording (colour before size). The round was small (4 cards change parse).

Still open: flashback costs that tap or sacrifice several creatures (Dread Return, Battle Screech, Group Project), "Discard X cards" / "Sacrifice X Mountains", Otaria (any graveyard), Iroh's Lesson flashback, "Spells can't be countered" (Lier), Cabal Therapy's name choice.
