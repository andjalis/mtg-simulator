# Standard coverage and the Forge script prototype (gap plan item I)

Measured 2026-10-16 on `main` at `272decd`, card database built from Forge (`build_carddb --forge`),
Forge files from commit `733a221e`. No games were played; both tools read card text only.

## How much of Standard the engine plays

```
python3 -m mtgsim.standard_coverage          # offline, from tests/fixtures/forge_scripts/standard
```

```
Standard: 4,902 distinct non-basic cards from 20 sets (WOE to FRA)

Status                                                Cards   Share
Fully supported (every line matched by a template)      381    7.8%
Simplified (all lines matched, some played loosely)      23    0.5%
Partly supported (at least one line ignored)          4,498   91.8%
Unknown to the card database                              0    0.0%

Partly supported cards that miss only one line: 1,962
Rules sentences handled (rough): 27% (3,483 of 12,933)

Most ignored families (cards with at least one ignored line in the family, top 20):
  triggered (whenever/when)          1,031
  counters                             821
  graveyard                            669
  tokens                               634
  activated abilities                  564
  sacrifice                            473
  exile                                467
  X costs                              304
  can't restrictions                   205
  equipment                            178
  library search                       147
  copy effects                         144
  cost reduction                       118
  modal (choose)                       114
  auras/enchant                        108
  +1/+1 static (anthems)                95
  set: food                             60
  mana restrictions                     56
  transform                             49
  set: exhaust                          38
```

The card table and the one-line count reproduce the gap plan exactly. Two numbers differ from the
plan: the share of rules sentences handled is 27% here, not "about 40%" (the plan's figure was a
rough split whose method isn't recorded; counting by lines or characters gives 20% to 27% too),
and the family counts use this tool's own regexes (`FAMILIES` in `standard_coverage.py`), so they
are close to but not the plan's. Every template PR can now quote the before/after of this report.

## Re-measure after PRs 32 to 37 (2026-10-16)

Same command on `main` at `6cabebf`, card database rebuilt from Forge `21f55608`:

| | Before (`272decd`) | Now (`6cabebf`) |
| --- | --- | --- |
| Fully supported | 381 (7.8%) | 726 (14.8%) |
| Simplified | 23 (0.5%) | 38 (0.8%) |
| Partly supported | 4,498 (91.8%) | 4,138 (84.4%) |
| Partly supported, missing only one line | 1,962 | 2,135 |
| Rules sentences handled (rough) | 27% (3,483) | 38% (4,908) |

Fully supported cards nearly doubled. Biggest family drops (cards with an ignored line):
triggered 1,031 → 816, sacrifice 473 → 358, activated abilities 564 → 400, tokens 634 → 536,
X costs 304 → 233, anthems 95 → 49, food 60 → 29. Copy effects (144) and modal spells (114) did not
move and are now the largest families with no progress.

## Can Forge's card scripts be translated into engine effects?

```
python3 -m mtgsim.forge_script --forge FORGE_DIR              # report
python3 -m mtgsim.forge_script --forge FORGE_DIR --card "Cut Down"   # one card's translation
```

`mtgsim/forge_script.py` parses Forge scripts (`A:`, `T:`, `S:`, `R:`, `K:`, `SVar:` chains, charms,
saga chapters, loyalty abilities, faces) and maps 22 Forge APIs (Draw, DealDamage, Destroy,
ChangeZone, Token, PutCounter, Pump, Dig, Counter ...) to the engine's `Effect` and `Trigger`
objects, but only for parameter values the engine can represent. Anything else is reported with
the reason, never guessed.

```
Forge script translation prototype (Standard, partly supported cards)

Partly supported cards with a Forge script: 4,498 of 4,498
Ignored lines: 8,397
  matched to a Forge ability:   7,067 (84.2%)
  translatable with the mapping: 200 (2.4%)
  upper bound if every parameter of the mapped APIs were supported: 2,748 (32.7%)
Cards that would become fully supported: 77 (1.7%)
Agreement with the templates on fully supported cards: 250 of 276 (90.6%)

```

What blocks the ignored lines that don't translate (8,197 lines):

| Blocker | Lines |
| --- | --- |
| A mapped API with parameters outside the engine's vocabulary (conditions, "exiled this way", choices, optional steps, more zones) | 1,914 |
| Trigger conditions the engine has no event for (beginning of combat, "whenever you attack", life gained, intervening ifs) | 1,351 |
| No matching Forge ability (keyword-only lines, X costs, notes the templates add) | 1,330 |
| Static abilities (anthems with conditions, cost changes, "can't block", granted abilities) | 991 |
| Keywords the engine lacks (equip, enchant, cycling, disguise, warp, plot, saddle, station ...) | 792 |
| Activated abilities other than mana and loyalty (the engine has no general activated ability) | 774 |
| APIs with no engine effect at all (Effect, Animate, ImmediateTrigger, PutCounterAll, Sacrifice, Untap, Attach, CopyPermanent ...) | 718 |
| Variable amounts (X, "for each") | 199 |
| Replacement effects | 128 |

The check of the mapping itself: on the 276 single-faced cards the templates already play fully,
the translation gives the same effects for 250 (90.6%). Of the 26 differences, 24 are cards the
prototype refuses to translate (optional costs, conditions, "non-outlaw" style restrictions). The
other two are real differences: Eriette's Lullaby is played by the templates as "destroy target
creature" (the "tapped" restriction is dropped, a template bug for item B), and Thor Odinson has
prowess twice in its Forge script but once in the templates.

## Recommendation

Don't wire the translation into card loading yet. Forge's scripts are easy to read (84% of the
ignored lines match a Forge ability by description, and the structure is regular), but the
engine's effect vocabulary is the bottleneck, not parsing: only 2.4% of the ignored lines
translate into effects the engine already has, and only 77 more cards (1.7%) would become fully
supported. Even if every parameter of the 22 mapped APIs were supported, the ceiling is 33% of
the ignored lines.

What would scale it: the engine needs a general ability model rather than more templates:
activated abilities with costs (774 lines), continuous statics with conditions (991), more
trigger events (1,351), remembered objects and conditions inside a chain ("exiled this way",
"if you do"), and the most common missing APIs (Effect, Animate, ImmediateTrigger,
PutCounterAll, Sacrifice, Untap, Attach, CopyPermanent). That is a rewrite of the engine's card
model toward Forge's, larger than item B. Until then, the prototype is most useful as:

1. a ranked to-do list for item B (the "unmapped APIs" and "blocks" lists above, by card count);
2. a cross-check of the templates against Forge (90.6% agreement; the rest are listed with
   `--disagreements`);
3. a second parser for wording variants of effects the engine already has, worth wiring in only
   after B's templates land, when the "translatable" share should be re-measured.

## Copy effects (mtgsim/copies.py)

Token copies ("create a token that's a copy of target creature you control, except ..."), clones
("you may have ~ enter as a copy of ..."), "for each ... create a token that's a copy", and copies of
spells ("when you next cast an instant or sorcery spell this turn, copy that spell", "when you cast ~,
copy it") now have templates. Fully supported cards 726 → 745 (14.8% → 15.2%); the copy-effects family
144 → 100 cards. Not modelled: becoming a copy until end of turn, copying abilities, "may cast the copy",
the legend rule. Targets for copies are chosen when the effect resolves.

## Restricted removal and fights (mtgsim/removal.py)

Destroy/exile with a restriction (enchantment, noncreature artifact, Vehicle, power 4 or greater, flying/reach),
"fights", "deals damage equal to its power", "untap target creature" and "target creature you control gains
KEYWORD". Many of these were the lines that kept modal spells partly supported. Fully supported cards
754 → 779 (15.4% → 15.9%) on top of copy effects (726 → 754 together with modal spells). Not done: the
"choose both instead" upgrades (teamwork, 5 cards; descend, delirium and the 8-permanent graveyard check, 3 cards)
are still played without the upgrade and reported as simplified.

## Auras (mtgsim/auras.py)

Auras are permanents attached to a host: "Enchant creature / creature you control / land ...", "Enchanted creature
gets +N/+N and has KEYWORD" (also negative), "doesn't untap", "can't attack or block", "when this Aura enters, tap
enchanted creature", and Equipment that attaches itself when it enters. The host is chosen when the Aura resolves
(friendly Auras on the caster's best creature, hostile ones on the opponent's best) and an Aura with no legal host
isn't cast. Fully supported cards 779 → 796 (15.9% → 16.2%). Not done: "you control enchanted creature", "loses all
abilities", Auras that count things ("for each Forest").

## Library search and X spells (mtgsim/search.py, mtgsim/xspells.py)

`search` covers "search your library for a/up to N <description> cards, [reveal,] put onto the battlefield (tapped) /
into your hand / on top, then shuffle", including "you may" and "its controller may". X spells take the X paid
when cast: "deals X damage to target creature", "-X/-X", "you lose X life", "each opponent loses X life (and you gain
X)", "draw X cards", "counter unless its controller pays {X}"; the AI plans them with the largest X it can pay.
Fully supported cards 796 → 813 (16.2% → 16.6%). The rest of the X family is mostly "where X is the number of ..."
and cost-reduction text, which needs counting templates of its own.

## Counting lines (mtgsim/counting.py)

"~ gets +N/+N for each [other] X you control" (X may be a type or a subtype such as Mountain), "~'s power and
toughness / power / toughness are equal to the number of X you control", "draw a card for each X you control (or
card in your graveyard)", "you gain/lose N life for each X", "put a +1/+1 counter on ~ for each X", and "discard up to
N cards, then draw that many". Effects carry ``data["per"]`` and multiply their amount by the count when they resolve.
Fully supported cards 813 → 827 (16.6% → 16.9%). The remaining counting lines are one-offs ("greatest power among",
"number of colors of mana spent", "number of differently named ...").

## Become a copy and copy abilities (mtgsim/copies.py)

"~ becomes a copy of target creature you control until end of turn" (the permanent swaps its card and reverts in the
cleanup step; the legend-rule sentence is ignored on purpose) and "Copy target activated or triggered ability you
control [from a creature source] [X times]" (pushes copies of the top matching ability on the stack).
Fully supported cards 827 → 830. Variants that pick a different target ("it becomes a copy of ... until your next
turn", copies of cards in graveyards) are still ignored.

## Choose-both upgrades (mtgsim/modal.py)

"If X, choose both / one or more / two instead" is now applied when the spell is cast. Conditions modelled: teamwork
(new `Teamwork N` line; creatures with total power N are tapped when they are summoning sick or it is after combat),
no cards in hand, delirium (four card types in the graveyard), eight permanent cards in the graveyard, a creature
subtype you control, six lands. "You control a commander" can never hold here, so it needs no note. Still unmodelled:
descend, kicked / additional cost paid, max speed, nonland permanent you don't own.
Fully supported cards 830 → 832 (the other cards with these lines are held back by other ignored lines).

## More triggered abilities (mtgsim/cards.py `_TRIGGERS`, engine events)

New events: beginning of combat on your turn, your second draw / second spell each turn, casting a spell with mana
value N or greater, "enters or dies", and "is put into a graveyard from the battlefield" (read as dies).
Fully supported cards 832 → 865. The long tail (becomes tapped, saddled, expend, commit a crime, counters leaving
or entering) is each only a handful of cards.

## Becomes tapped, saddle and expend (mtgsim/cards.py, engine)

"Whenever ~ becomes tapped" (fired when it attacks, crews or saddles; mana and cost taps are not tracked),
"Saddle N" (the AI taps creatures with total power N, summoning-sick ones first, before attacks) with
"Whenever ~ attacks while saddled", and "Whenever you expend N" (counts mana sources tapped this turn).
Fully supported cards 865 → 894.

## Creature and permanent death triggers (mtgsim/cards.py, engine)

"Whenever a/another creature you control [with a counter on it] dies" and "Whenever an artifact/enchantment/Food you
control is put into a graveyard from the battlefield". Not modelled: cards leaving a graveyard, "counter is put on ~"
thresholds (plan counters). Fully supported cards 894 → 905.

## Descend (mtgsim/engine.py `Graveyard`)

Graveyards count the permanent cards put into them this turn, so "if you descended this turn, ..." works as a trigger
condition and as a "choose both instead" upgrade. Kicker and additional-cost upgrades (two cards) are still unmodelled.
Fully supported cards 905 → 911.

## Cheapest single-line misses

Taken from the cards missing exactly one line, most common first: "enters tapped unless you control a planeswalker /
unless a player has 13 or less life" (20 cards), Cycling and the landcycling family (about 30; the AI cycles with
spare mana after its main phase: a landcycler while land drops are short, a card it can't reach soon, or when the hand
is full), Changeling (counts as every creature type), "Investigate", "untap ~", "gets +X/+Y and gains KEYWORD until
end of turn" and "each opponent discards a card". Fully supported cards 911 → 1,020 (20.8% of 4,902).
Next cheapest: Convoke (8), "enters prepared" (17, a new mechanic), Mobilize, Disguise, manifest dread, endure,
"exile up to N target cards from a graveyard".

## Convoke and enters prepared (mtgsim/engine.py)

Convoke taps summoning-sick creatures (or any untapped creature once combat is over) to pay generic mana.
"Enters prepared": the creature may cast a copy of its spell face once (`Permanent.prepared`, cast as a `prepared`
spell variant that goes nowhere afterwards). Fully supported cards 1,020 → 1,047.

## Mobilize, endure, manifest dread and disguise (mtgsim/cards.py, engine)

Mobilize N / X: an attack trigger makes tapped and attacking 1/1 Warriors that are sacrificed at the end step.
Endure N: counters on the source if it is still on the battlefield, otherwise an N/N Spirit. Manifest dread: of the top
two cards the cheaper becomes a face-down 2/2 and the other goes to the graveyard; manifests are never turned face up.
Disguise: cast face down for {3} (2/2 with ward 2) only when the full cost can't be paid, and turned up with leftover
mana after the main phase. Fully supported cards 1,047 → 1,075.

## Graveyard exile, mill and target pronouns

"Exile up to N target cards from a graveyard" (the opponent's best cards first), "Put target card from a graveyard on
the bottom of a library", "You may mill N cards", and "Untap it." / "It explores." after a targeted spell effect
(the previous target). Fully supported cards 1,075 → 1,110.

## Cheap single-line misses (flagged-deck cards first)

Mutagen tokens, "Amass <Type> N" (grows the one Army or makes it), "Creatures you control have haste/trample",
"Red / Instant and sorcery spells you cast cost {1} less", "Your opponents can't cast spells during your turn",
"During your turn, ~ has first strike", conditional "~ gets +N/+N as long as there are four permanent / seven cards
in your graveyard" (descend, threshold), "~ enters with a +1/+1 counter if a creature died / an opponent lost life /
you attacked this turn", plus small effect lines (drain with "defending player", "draw a card and lose N life",
opponent discards, opponent sacrifices a creature, another target creature gains a keyword or a counter, "1 damage
to each of one or two targets" read as one target). Fully supported cards 1,110 → 1,162.

## Flagged-deck cards and mana abilities with costs

Magmatic Hellkite (destroys the opponent's best nonbasic land, which fetches a tapped basic with a stun counter; the land
is chosen, not targeted), Sapling Nursery ("Treefolk and Forests you control gain indestructible"). Mana abilities:
filter lands and Prophetic Prism ("{1}, {T}: Add one mana of any color" adds no mana of its own, it recolours one other
source and taps), once-per-turn converters ("{1}: Add {W}, {B}, or {G}", no tap needed), "{T}, Tap an untapped creature
you control: Add one mana of any color", "{T}, Sacrifice ~: Add ...", and "Activate only if you control a Dragon".
Fully supported cards 1,162 → 1,184.

## Empower, Discover, Mayhem and Sneak

Empower Jace N (a Jace planeswalker token with "-1: Surveil 1" and "-3: Draw a card"; one token grows), Discover N (the
first nonland card of mana value N or less is cast for free, otherwise it stays in hand, the rest go to the bottom),
Mayhem (cast from the graveyard for its cost if it was discarded this turn) and Sneak (after blockers, return an
unblocked attacker and pay the sneak cost; a creature enters tapped and attacking, without going on the stack). The AI
sneaks when the new creature beats the cheapest unblocked attacker. Not yet: "Empower Jace X", "Discover X". Fully
supported cards 1,184 → 1,219.

## Valiant, Opus, Repartee and Eerie

Four ability-word triggers. Valiant fires once per turn when a permanent is targeted by its controller's spell or
ability (trigger abilities that target are not counted yet). Opus compares the mana spent on the instant or sorcery
(five or more) and supports both the "also" and "instead" forms. Repartee needs a creature among the spell's targets.
Eerie fires when an enchantment enters (Room unlocking does not exist in the engine). Fully supported cards
1,219 → 1,246.

## Roles, Connive and follow-up bites

Role tokens are Auras on the creature (Royal +1/+1 and ward 1, Monster +1/+1 trample, Wicked +1/+1 and drains when it
leaves, Cursed base 1/1, Sorcerer scry on attack, Young Hero counter on attack at toughness 3 or less; a new Role
replaces the old one). Connive draws, discards (the AI's choice) and adds a +1/+1 counter for a nonland discard.
"It deals damage equal to its power to ..." and "it fights ..." after a first target, and bite spells that can hit a
planeswalker. Not yet: Virtuous Role, bites at two targets, "if it would die, exile it instead". Fully supported cards
1,246 → 1,281.

## X Mutagen tokens, Empower X and granted mana abilities

"Create X Mutagen tokens" reads the X the permanent was cast with; "activated abilities of artifact tokens cost {1}
less" applies to ability costs. "Empower Jace X, where X is the number of creatures/Islands you control" is counted
on resolution. Static lines that give other permanents a mana ability (creatures, lands, creature tokens, Foods, other
permanents, lands and Allies) make those permanents tap for the granted colours; summoning-sick creatures still
cannot. Restricted-mana grants (Clement, Mm'menon) are not done. Fully supported cards 1,281 → 1,286.

## Exile-instead, Virtuous Role and the cheapest single-line misses

"If that creature would die this turn, exile it instead" marks the target before the damage so the state-based
death exiles it. Virtuous Role gives +1/+1 per enchantment you control. New templates: Recruit, Increment (compares
the mana spent on the spell with power and toughness), "discard a card" additional costs (with the "or pay {2}"
form), "costs {N} less if it targets a tapped creature" (the spell is aimed at a tapped opposing creature),
destroy artifact/enchantment/flying creature, return up to two creature cards from the graveyard, return another
permanent you control (only chosen to replay an enters ability), Dragonstorm "return ~ when a Dragon enters", lands
that choose a color, "untap during each other player's untap step" and "enchanted creatures you control get +N/+N".
Not yet: Firebending (needs a combat mana pool), bites at two targets. Fully supported cards 1,286 → 1,339.

## Forge-flagged cards, Firebending, Discover X follow-ups

Cards the third Forge cross-check named: Izzet Spellementals (Hearth Elemental and Sunderflock cost reductions,
Sunderflock's mass bounce, Stoke Genius, Get Out's modes, Flow State's two-card clause), Dimir Control (The Theorist's
opponent draw-step trigger and bounce, Deadly Cover-Up with real "collect evidence 6", graveyard exile), Jund Sacrifice
(Azog, Obsessive Pursuit, The Sackville-Bagginses) and Azorius Artifact Control (Repurposing Bay, Pinnacle Starcage,
Petrified Hamlet, The Irencrag, The Mind Stone). Also Hurl into History, Hit the Mother Lode, Overwrite the Multiverse,
Firebending (red mana that lasts until end of combat), "deals damage to each of two other target creatures" and
"counter on each of up to two target creatures". Still ignored on flagged decks: Uldaros Theorix (free casting of
copies), Lively Dirge's Spree modes parse but Spree itself needs checking, Perilous Snare (speed), Braided Net.
Fully supported cards 1,339 → 1,364.

## Round 7: cheap generic lines

Keyword pumps on the card itself ("~ gets +2/+0 and gains lifelink"), Aura "enchanted creature gains X",
"destroy target creature or enchantment", "tap target permanent", "each player draws", "can't block this turn",
"exile a card from their hand", reanimate/regrow variants, subtype and keyword lords ("Other Elves get +1/+1", "Rhinos
have menace", "creatures with flying get +1/+1"), counter-based trample, second-spell and "if you control a Wizard"
discounts, seven-lands bonus, counter-spell filters, -1/-1 counters, damage to each player, graveyard exile,
"one or two target creatures" (distinct targets). Fully supported cards 1,364 → 1,455.

## Round 8: speed, threaten, Mercenary tokens, optional-cost draws

Speed: "Start your engines!" sets speed to 1 when the permanent enters; speed rises once per turn when an opponent loses
life on your turn (max 4); "Max speed —" lines are gated on speed 4 (keywords, +N/+N, triggers, activated abilities).
"Gain control of target creature until end of turn, untap, haste" (control returns in cleanup). Mercenary tokens with
their sorcery-speed pump ability and X Mercenary tokens. Job select (Hero token, equipment attaches). "~ can't be
blocked", "no maximum hand size", "attacks each combat if able", "enters with N -1/-1 counters". "You may discard a
card / sacrifice a permanent. If you do, draw" and the general "you may pay {N}. If you do / When you do, ..." gate
(the AI pays whenever it can). Fully supported cards 1,455 → 1,509.

## Round 9: graveyard abilities, token doubling, blocker-power evasion

"{cost}: Return this card from your graveyard to your hand" and "{cost}, Exile this card from your graveyard: Draw a
card" (the latter gated on max speed where printed), "twice that many tokens", chosen-type anthems, "can't be blocked by
creatures with power N or greater", noncreature and subtype cost discounts. Gift riders were left out: they need a
cast-time promise to the opponent. Fully supported cards 1,509 → 1,519.

## Round 10: Bargain, Gift and ", where X is ..." amounts

Bargain (the AI sacrifices a spare token, artifact or enchantment) and Gift (the opponent gets a card, Food, Treasure,
tapped Fish or Octopus; the AI always promises it) are decided at cast time. "If ~ was bargained / the gift was
promised / wasn't promised, ..." riders (with "instead" replacing the matching base effect) work on instants, sorceries
and on "When ~ enters, if ..." triggers. Any "..., where X is <quantity>" sentence is parsed with X as 1 and scaled at
resolution by a counted quantity (permanents you control, graveyard cards, a creature's power or toughness, life total,
speed, life gained this turn, counters on ~, the greatest power or toughness). Pronoun riders ("that creature gets
-5/-5", "destroy that creature", "it also gains flying and lifelink"). Fully supported cards 1,519 → 1,565.
Left out: "costs {N} less if bargained" (the cost is needed before the choice).

## Round 11: Power-up, Exhaust, Renew, keyword counters, pay gates, new trigger events

Power-up and Exhaust abilities (each only once; Power-up costs its mana cost less on the turn the creature entered),
Renew (exile from the graveyard at sorcery speed), keyword counters (flying, trample, lifelink ... as permanent
keywords), Braided Net locks, "put a +1/+1 counter on target creature or Vehicle". "You may sacrifice / discard a
card / forage / blight N. If you do ..." gates (the AI pays when it is cheap: a token, a land it can spare, three
graveyard cards). New trigger events: first and second main phase (with Survival, "if ~ is tapped", and "This ability
triggers only once"), a creature attacking alone, committing a crime (targeting an opponent, their permanent or
their graveyard), scrying or surveilling, discarding. "Add {R}{R}" effects. Fully supported cards 1,565 → 1,669.
Not done: Level up and Class levels, "When you do" reflexive triggers with their own targets, cards leaving the graveyard.
