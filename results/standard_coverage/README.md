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

## Round 12: graveyard returns, granted flashback, graveyard statics, restricted removal

One general template for "Return [up to N] target <description> card(s) [with mana value N or less] from your / a
graveyard to your hand / the battlefield [tapped]" (descriptions like "noncreature, nonland permanent", "creature or
Vehicle", subtypes, "all land cards"). "Target instant or sorcery card in your graveyard gains flashback until end of
turn". Threshold / Descend statics that grant keywords or "can't be blocked", "~ costs {1} less for each <description>
card in your graveyard", and "whenever one or more <description> cards leave your graveyard" triggers (once per batch).
Restricted removal: "destroy / exile [up to one] target <artifact, enchantment, creature ...> [an opponent controls]
[with mana value / power / toughness N or less / greater]". Fully supported cards 1,669 → 1,755.
Not done: counter riders on returned cards ("with a finality counter", "with X additional +1/+1 counters"),
"cast from your graveyard" permissions, embalm / eternalize grants.

## Round 13: exile now, play later, "until ~ leaves" removal, behold

"Exile the top N cards of your library" followed by "You may play that card / those cards this turn" or "until the end of
your next turn": exiled cards go on a per-player playable-exile list with an expiry turn; spells show up in
`spell_options` (kind `impulse`) and lands are played through `play_land`. One general template for "exile [up to one]
[other] target [non-Subtype] <types> [an opponent controls] [with mana value N or greater] until ~ leaves the battlefield".
"As an additional cost to cast ~, behold a <type> or pay {N}" adds the tax unless you control or hold such a card.
Fully supported cards 1,755 → 1,776. Not done: exiling from an opponent's library, "choose one of them", behold-and-exile
costs (Champion cycle), "exiled with ~" cards (Suspend-style stores), cast-from-exile mana restrictions.

## Round 14: conditional sentences, tapped tokens, token anthems

A general "If <condition>, <effect>" sentence rewrite: the condition is looked up in a small table (you attacked this
turn, an opponent controls more lands than you, a creature died this turn / under an opponent's control, you control
another <Subtype or outlaw>, two or more tapped creatures, a creature with power N or greater, you sacrificed a permanent
this turn) and the rest of the sentence is parsed as usual with that condition attached. "Create [N] tapped <Treasure /
Food / ...> or N/N tokens", "target player creates ... tokens", "Creature tokens you control get +N/+N" and "Whenever you
cast an outlaw spell" triggers. Fully supported cards 1,776 → 1,802.
Not done: copies of a trigger's subject ("if it isn't a token, create a token that's a copy of it"), delayed
sacrifice of created tokens, tokens with quoted abilities that need parsing (Pilot, Spirit with X), Class levels.

## Round 15: forced blocks, waterbend and firebending lines

Combat restrictions: "~ must be blocked if able", "It must be blocked this turn if able", "Target creature blocks this
turn if able" (and "attacks or blocks"), "Creatures with power less than ~'s power can't block it", "[Up to N / one or
two] target creatures can't block this turn" (distinct targets are now chosen up front) and "It can't block this turn".
`Game.force_blocks` adds the demanded blocks to the AI's choice. "Waterbend {N}:" abilities are treated as {N}
activated abilities (the tap-artifacts-and-creatures payment is not modelled), "Ward—Waterbend {N}" as ward {N}, and
keyword lists that include "firebending N" are split so each keyword parses. Fully supported cards 1,802 → 1,810.
Not done: airbend, "waterbend" as an additional cost, granting firebending, "~ attacks each combat if able" granted to
tokens, Class levels.

## Round 16: milling and filtered recovery

General milling wording covers "you [may] mill", "target player/opponent mills", "that player mills",
"each opponent mills" and "each player mills", with word or numeric amounts. "Each opponent" is untargeted;
"target opponent" excludes the caster. Recovery selects one, up to N, all, or each matching card from the
cards just milled. Card types, subtypes, and unions such as "instant, sorcery, or Faerie" and
"creature and/or land" are supported. Destinations are hand, library top, or battlefield (optionally tapped).
Battlefield returns use the usual entry handling and triggers. Optional recovery uses the library-search policy.

Measured 2026-10-18 with the existing offline database: fully template-matched Standard cards
1,807 → 1,821 of 4,902; handled rules sentences 7,640 → 7,676 of 12,926. These before/after figures use the
same database and do not replace the historical measurements above. Examples newly fully matched include
Bramble Familiar, Picklock Prankster, Dredger's Insight, and Vastlands Scavenger.

Still unsupported: recovering an opponent's milled cards, "cards that have an Adventure", conditional
rewards based on what was milled, and counter riders on battlefield returns.

## Round 17: counters on graveyard returns

Battlefield returns can carry "with a finality counter on it" or "with N additional +1/+1 counters on it",
including X paid for the spell and plural returns. The base effect must also parse. "Put target ... card
from a graveyard onto the battlefield under your control" uses the same return handling. Counters and
tapped status apply before entry triggers and state checks, so counters can keep a returned 0/0 alive.
Finality redirects a move to the graveyard to exile, without death triggers or creature-death flags;
bouncing the permanent clears its counters as usual. Milled-card battlefield returns also accept these riders.

Still unsupported: activated abilities that return themselves from the graveyard, shield counter riders,
and return chains whose base effects remain unsupported. Existing graveyard returns continue to select
cards at resolution using the engine's return policy.

## Round 18: conditional milling rewards

"If a <type/subtype> card was milled this way, <effect>" and "<effect> if a <type/subtype> card is milled
this way" parse the reward normally and apply the condition to each effect in it. Conditions also support
"you milled a ... card this way", "one or more", and "N or more" matching cards, including unions of types.
A multitype card counts once. Each resolving stack item stores its own last mill for each player: rewards
still see recovered cards, and cannot use a previous resolution's mill. Unknown conditions and rewards
remain reported as unsupported. This adds the Lesson-card reward on Sparring Dummy.

Still unsupported: comparisons between milled cards (shared types or different names), "repeat this process",
and rewards that refer to a different player's mill.

## Round 19: recovery of cards with Adventures

"Put all cards that have an Adventure from among the milled cards into your hand" uses the actual Adventure
face on the card definition. Single-card and up-to-N variants use the same selection handling. Creature and
noncreature Adventure cards qualify; unrelated back faces do not. Returned cards retain both playable faces.
This matches Beluna Grandsquall's Seek Thrills recovery text, while her separate cost-reduction line remains
unsupported, so she remains partly supported in the card-level report.

Measured 2026-10-18 against the same existing offline database as round 16:

| Batch | Fully template-matched cards | Handled rules sentences |
| --- | ---: | ---: |
| Before these three batches | 1,821 | 7,676 |
| Round 17: return counters | 1,830 | 7,693 |
| Round 18: milling rewards | 1,831 | 7,696 |
| Round 19: Adventure recovery | 1,831 | 7,697 |

Totals remain 4,902 Standard cards and 12,926 rules sentences. These are parser coverage measurements,
not a claim that every game interaction on these cards is implemented.

## Round 20: activated returns from the graveyard

"COST: Return this card from your graveyard to the battlefield [tapped] [with a finality counter on it]"
is stored separately from battlefield abilities. Supported costs are mana, discarding cards, and paying life;
normal return counter riders also apply. Activation checks the source zone, costs, sorcery timing, max speed,
and explicit delirium or descend-8 restrictions. The source stays in the graveyard while its ability is on
the stack and returns only if it is still there when the ability resolves. The default main-phase policy
uses these abilities with available mana. They are abilities rather than spells, so spell casting triggers
and spell counterspells do not apply.

Still unsupported: exiling other graveyard cards as a cost, transformed or attached returns, once-per-turn
limits on these graveyard abilities, and activation conditions that require untracked events (such as
noncombat damage or scrying earlier in the turn). These lines remain visible in coverage.

## Round 21: shared card types and repeating mill processes

"If N cards that share a card type were milled this way, EFFECT" checks for one type common to at least N
of the cards. Multitype cards may match any of their card types, while supertypes and subtypes do not count.
Kindred is recognised as a card type; legacy Tribal wording is normalised to Kindred.

The Tale of Tamiyo's first three chapters now run "mill two; if they share a type, draw and repeat" in order.
Each iteration uses the new mill, draws before milling again, and stops on a failed match or a loss from
drawing an empty library. Only a preceding unconditional self-mill followed by fixed card draws supports
"repeat this process"; other repeating chains remain unsupported. Tamiyo's fourth chapter still has ignored
exile/copy/cast-permission text, so the card remains partly supported.

## Round 22: discounts for spells that have Adventures

"Permanent spells you cast that have an Adventure cost {N} less to cast" (Beluna Grandsquall), and corresponding
creature/artifact/enchantment or unqualified spell wording, reduce generic mana for the cast face. The
permanent face qualifies in hand and after its Adventure; its Adventure spell does not inherit that face's
characteristics. Discounts stack with other applicable reductions, preserve coloured costs, and apply only
while the provider is on its controller's battlefield. Beluna is now fully template-matched, including
the Adventure recovery implemented in round 19. Conditional discount wording remains unsupported.

Measured 2026-10-18 against the same existing offline database:

| Batch | Fully template-matched cards | Handled rules sentences |
| --- | ---: | ---: |
| Before these three batches | 1,831 | 7,697 |
| Round 20: graveyard activations | 1,837 | 7,709 |
| Round 21: shared-type mill rewards | 1,837 | 7,710 |
| Round 22: Adventure discounts | 1,838 | 7,711 |

Totals remain 4,902 Standard cards and 12,926 rules sentences.

## Rounds 23–25: land destruction, swampwalk, proliferate

Targeted land destruction has its own land target class, with optional nonbasic and opponent-control
restrictions. Target selection, resolution checks, hexproof, ward, indestructible, and subsequent
"its controller" effects use the existing removal handling. The default and heuristic policies select
legal opponent lands. Type unions and additional restrictions outside these templates remain unsupported.

Swampwalk uses the shared blocking check: no creature can block the attacker if the defending player
controls a land with the Swamp subtype. Dual lands and snow-covered Swamps qualify; a land's name or
ability to make black mana alone does not. Both combat resolution and AI combat decisions use this check.
Other landwalk keywords remain unsupported.

Proliferate chooses any number of counter-bearing permanents and players at resolution and adds one
counter of every existing kind on each chosen object. It does not target, introduce absent counter types,
or allow selecting only some counter kinds on a chosen object. All counters change before Saga chapter
triggers are queued. "Proliferate twice" and "whenever you proliferate" triggers are supported. Player
counters are stored explicitly, with poison loss at ten counters. Keyword counters are tracked as counters,
and opposing +1/+1 and -1/-1 counters cancel during state checks. Other mechanics that create or use player
counters still require their own templates and continue to appear as gaps.

The default proliferate policy scores known counter types on each whole object and skips choices whose
net score is not positive. An optional `choose_proliferate(game, me)` hook, or an explicit selection passed
to `Game.proliferate`, can choose other legal objects, including objects with unfamiliar counter types.
These choices are policy decisions; the counter additions handle every stored counter kind.

Measured 2026-10-18 against the same offline database, with before/after full-match lists saved in
[`../card_effect_batches/rounds23-25-coverage.json`](../card_effect_batches/rounds23-25-coverage.json):

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 7,922 / 34,922 | 8,043 / 34,922 |
| Standard: fully template-matched | 1,838 / 4,902 | 1,841 / 4,902 |
| Standard: handled rules sentences | 7,711 / 12,926 | 7,716 / 12,926 |

The 121 newly fully matched database entries break down as 53 land-destruction cards, 24 swampwalk cards,
and 44 proliferate cards, classified by their previously ignored text. This includes more than the earlier
exact-wording estimates because the implementations also cover variants and abilities with those effects.
No parser errors were found across the entire database. The current full report is
[`../database_coverage/README.md`](../database_coverage/README.md).

Two 40-game synthetic mirrors against BaselineAI exercised 210 land destructions and 325 proliferations;
outcomes and confidence intervals are recorded in `AI_RESULTS.md`.


## Rounds 26–28: infect, devoid and exalted (2026-10-18)

Infect replaces damage results with poison counters on players and -1/-1 counters
on creatures, including combat, damage abilities and fights. Lifelink, deathtouch,
first/double strike and trample still apply. Devoid makes the card colorless without
changing its casting cost or devotion contribution. Colored tokens preserve their
colors. Exalted creates one stack trigger per instance when exactly one creature
attacks, including instances on nonattacking permanents. Combat predictions account
for infect counters, poison lethal and the lone attacker's exalted bonuses.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,043 / 34,922 (23.03%) | 8,112 / 34,922 (23.23%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,782 | 26,713 |
| Standard: fully template-matched | 1,841 / 4,902 | 1,841 / 4,902 |
| Standard: handled rules sentences | 7,716 / 12,926 | 7,716 / 12,926 |

All 69 newly fully matched entries had exactly one of the new keywords as their
remaining gap: infect 24, devoid 23, exalted 22. No database parse errors were found.
Examples include Glistener Elf, Blighted Agent, Viral Drake, Reality Hemorrhage,
Noble Hierarch, Qasali Pridemage and Rafiq of the Many. Full means every card-text
line matches the simulator's templates; it does not certify complete Magic rules
conformance. The current engine still has the limitations documented in the main README.

Exact additions are saved in
[`../card_effect_batches/rounds26-28-coverage.json`](../card_effect_batches/rounds26-28-coverage.json).
The complete sortable card inventory and remaining gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).
Two 40-game fixture mirrors against BaselineAI are recorded in `AI_RESULTS.md`.

## Rounds 29–31: flying-only blockers, forestwalk/mountainwalk and shroud (2026-10-18)

Permanents with "can block only creatures with flying" reject ground attackers;
the restriction does not grant flying or reach. The shared blocking check applies
this rule in combat and in the AI's block search. Forestwalk and mountainwalk use
the defending player's land subtypes, including tapped duals and snow lands. Names
and mana production alone do not qualify, and removing the matching land restores
normal blocking legality.

Shroud prevents either player from targeting the permanent. Spells recheck this
when resolving, so gaining shroud in response can invalidate their targets.
Equip and the default equip-target selection also enforce targetability. Existing
attachments, untargeted effects, self abilities and combat damage still work.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,112 / 34,922 (23.23%) | 8,183 / 34,922 (23.43%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,713 | 26,642 |
| Standard: fully template-matched | 1,841 / 4,902 | 1,841 / 4,902 |
| Standard: handled rules sentences | 7,716 / 12,926 | 7,716 / 12,926 |

The 71 new full matches comprise 22 flying-only blockers, 33 landwalk cards
(including mixed keyword lists), and 16 shroud cards (including Lightning Greaves).
Other additions include Brazen Borrower // Petty Theft, Wall of Denial, Simic Sky
Swallower, Mirri, Cat Warrior and Stalker Hag. No database parse errors were found.
Full matches measure text-template coverage, not complete Magic rules conformance.

Exact additions and before/after counts are in
[`../card_effect_batches/rounds29-31-coverage.json`](../card_effect_batches/rounds29-31-coverage.json).
The complete card inventory and remaining gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).

## Rounds 32–34: fear, horsemanship and delayed upkeep draws (2026-10-18)

Fear permits blocking only by artifact creatures or black creatures. This uses
actual card colors, so a black mana symbol on a nonartifact creature with devoid
does not qualify. Horsemanship permits blocking only by creatures with
horsemanship; flying and reach alone do not qualify. Both restrictions combine
with other blocking rules and feed the engine's combat and the AI's block search.

"Draw ... at the beginning of the next turn's upkeep" and "... your next upkeep"
create one-shot delayed triggered abilities. Each uses the stack, retains its
original controller, and survives its source leaving play or changing controller.
A delayed draw created during an upkeep waits for a later upkeep. A spell that
fails to resolve does not create its delayed ability. Ordinary draw triggers and
empty-library losses still apply when the delayed ability resolves. Other delayed
actions and timings remain visible as coverage gaps.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,183 / 34,922 (23.43%) | 8,224 / 34,922 (23.55%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,642 | 26,601 |
| Standard: fully template-matched | 1,841 / 4,902 | 1,841 / 4,902 |
| Standard: handled rules sentences | 7,716 / 12,926 | 7,716 / 12,926 |

The 41 newly fully matched entries comprise 14 fear cards, 13 horsemanship cards,
and 14 delayed-draw cards. Examples include Shriekmaw, Dross Golem, Wort, Boggart
Auntie, Lu Meng, Wu General, Carrier Pigeons and Mystic Melting. No database parse
errors were found. Full matches measure text-template coverage, not complete Magic
rules conformance.

Exact additions and before/after counts are in
[`../card_effect_batches/rounds32-34-coverage.json`](../card_effect_batches/rounds32-34-coverage.json).
The complete card inventory and remaining gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).

## Rounds 35–37: improvise, delve and undying (2026-10-18)

Improvise taps untapped artifacts, including summoning-sick artifact creatures,
to help pay generic costs. Delve exiles graveyard cards for generic costs. Neither
pays colored or explicit {C} requirements. Planning does not spend resources;
casting commits the chosen taps and exiles, and countering the spell does not
refund them. Assistance includes X costs and follows ordinary cost reductions.
Artifact mana sources cannot also improvise the same payment; helpers needed by
colored mana abilities are reserved. Multi-mana artifacts can use their mana
abilities instead of contributing only one generic payment through improvise.

Undying checks the creature's +1/+1 counters when it dies, then uses the stack to
return its card under its owner's control with a +1/+1 counter already present
for entry triggers. Exile replacements and tokens do not return. Physical copies
are distinguished even when they share a CardDef name; leaving and reentering the
graveyard invalidates an earlier undying return. Deaths retain their last-known
counters, so lethal damage and counter cancellation do not grant an extra return.

Two 40-game synthetic mirrors against BaselineAI completed; outcomes and confidence
intervals are recorded in `AI_RESULTS.md`. They are fixture-specific integration
checks and do not establish a pilot-performance difference.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,224 / 34,922 (23.55%) | 8,268 / 34,922 (23.68%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,601 | 26,557 |
| Standard: fully template-matched | 1,841 / 4,902 | 1,842 / 4,902 |
| Standard: handled rules sentences | 7,716 / 12,926 | 7,718 / 12,926 |

The 44 new full matches comprise 16 improvise cards, 14 delve cards and 14 undying
cards. Examples include Metallic Rebuke, Reverse Engineer, Dig Through Time,
Treasure Cruise, Gurmag Angler, Young Wolf and Strangleroot Geist. No database
parse errors were found. Full matches measure text-template coverage, not complete
Magic rules conformance.

Exact additions and before/after counts are in
[`../card_effect_batches/rounds35-37-coverage.json`](../card_effect_batches/rounds35-37-coverage.json).
The complete card inventory and remaining gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).

## Rounds 38–45: death returns, cast triggers and evasion (2026-10-18)

Three further batches extend the shared rules infrastructure:

- Persist uses the same graveyard-incarnation tracking as undying, checking for
  -1/-1 counters at death and returning with a -1/-1 counter. Wither uses infect's
  counter-damage handling on creatures while dealing normal damage to players;
  combat predictions account for first-strike counter damage reducing later power.
- Rebound exiles a resolving spell cast from hand and creates a one-shot trigger
  for its controller's next upkeep. Its optional free recast uses fresh targets,
  obeys casting restrictions and does not rebound again. Countered or fizzled
  spells do not rebound; leaving exile invalidates that delayed permission.
- Storm snapshots earlier spells cast by both players that turn, including those
  countered, then copies its spell through a separate trigger. Copies are not cast,
  and permanent-spell copies enter as tokens. Cascade is a cast trigger that
  searches by strictly lower mana value, offers a free cast during resolution,
  and bottoms the other revealed cards in random order. Its free cast can trigger
  storm or cascade, and a legal Adventure face retains its Adventure destination.
- Islandwalk and plainswalk complete the basic landwalk set. Shadow restricts
  both attackers and blockers; intimidate uses actual shared colors or artifact
  creature status. These restrictions combine with flying, fear and other rules.

Regression tests cover overlapping restrictions, independent identical physical
cards, countered originals and triggers, free-cast timing, target changes, declined
casts, and source or zone changes. Two 40-game synthetic mirrors against BaselineAI
exercise counter damage/death returns and storm/cascade/rebound; results are saved
alongside the coverage additions and summarized in `AI_RESULTS.md`.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,268 / 34,922 (23.68%) | 8,385 / 34,922 (24.01%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,557 | 26,440 |
| Standard: fully template-matched | 1,842 / 4,902 | 1,843 / 4,902 |
| Standard: handled rules sentences | 7,718 / 12,926 | 7,721 / 12,926 |

The 117 new full matches include Kitchen Finks, Glen Elendra Archmage,
Puncture Blast, Staggershock, Grapeshot, Bloodbraid Elf, Apex Devastator,
Maelstrom Wanderer, Inkwell Leviathan and Bladetusk Boar. Multiple native storm
and cascade instances trigger independently; wither damage spells use their
own keyword abilities. No database parse errors were found. Full matches measure
text-template coverage, not complete Magic rules conformance.

Exact additions are in
[`../card_effect_batches/rounds38-45-coverage.json`](../card_effect_batches/rounds38-45-coverage.json).
The complete card inventory and ranked gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).

## Rounds 46–48: regeneration, learn and extended landwalk (2026-10-18)

Regeneration creates shields for self, targeted creatures/artifacts or a group of
creatures. Each shield replaces one destruction, including lethal marked damage
or deathtouch, by clearing damage, tapping the permanent and removing it from
combat. Sacrifice, zero toughness and zero loyalty bypass shields. Shields and
turn-long regeneration prohibitions expire at cleanup. Destruction and damage
riders that prevent regeneration retain their proper scope. Combat prediction
models shield consumption and removal from subsequent damage steps. Default
priority policies use regeneration in response to threats rather than spending
mana on pure regeneration actions in safe main phases.

Learn supports taking and revealing a Lesson from the player's sideboard,
discarding a card then drawing, or declining both. Single-game CLI runs, the
Python runner and best-of-three matches supply a fresh outside-game pool each
game. Post-board games use the sideboard left after the planned swaps, including
cards boarded out. The `choose_learn` hook exposes the three choices. Lessons in
exile, the library or an opponent's sideboard do not qualify. Both AI pilots value
the available Lesson or rummage option.

Nonbasic and legendary landwalk check the defending player's actual land
supertypes. Basic and legendary metadata survive card parsing and copying;
nonbasic snow duals remain nonbasic. Ordinary basic landwalk behavior is retained.

| Scope | Before | After |
| --- | ---: | ---: |
| Entire database: fully template-matched | 8,385 / 34,922 (24.01%) | 8,533 / 34,922 (24.43%) |
| Matched with recorded simplifications | 97 | 97 |
| Partly matched | 26,440 | 26,292 |
| Standard: fully template-matched | 1,843 / 4,902 | 1,843 / 4,902 |
| Standard: handled rules sentences | 7,721 / 12,926 | 7,721 / 12,926 |

The 148 new full matches comprise 131 regeneration/prevention cards, 14 learn
cards and three landwalk cards. Examples include Troll Ascetic, River Boa,
Damnation, Wrath of God, Welding Jar, Professor of Symbology, Field Trip,
Dryad Sophisticate, Trailblazer's Boots and Ayumi, the Last Visitor.
No database parse errors were found. Full matches measure text-template coverage,
not complete Magic rules conformance.

Validation: 848 tests ran successfully, one skipped. Two 40-game synthetic mirrors
resolved 688 regenerations and 612 learn choices; outcomes are in `AI_RESULTS.md`.
The fixture comparisons do not establish a pilot-performance difference.
Exact additions and before/after counts are in
[`../card_effect_batches/rounds46-48-coverage.json`](../card_effect_batches/rounds46-48-coverage.json).
The complete card inventory and ranked gaps are in
[`../database_coverage/README.md`](../database_coverage/README.md).

## Round 17: Class levels, abilities-removing Auras, ability-word prefixes

- Class cards: `{cost}: Level N` is a sorcery-speed ability that is only legal at level N−1 and sets the `level` counter.
  "When this Class becomes level N, …" fires on the level-up; triggers and statics parsed after a level marker are gated
  by `Trigger.min_level`.
- "Enchanted creature loses all abilities" (optionally with −N/−N or "doesn't untap") removes keywords only; flagged as
  an approximation in `--coverage`.
- Equipment that grants a creature type, and the ability words Alliance, Void, Delirium, Hellbent, Metalcraft,
  Threshold and Ferocious are now recognised.

## Round 18: counters on filtered creature sets and end-step blink

- "Put N +1/+1 counters on each (other) tapped / legendary / <subtype> creature you control" (`only` filter on `p1_counters`).
- "Exile target creature you control. Return it to the battlefield under its owner's control at the beginning of the next
  end step" (`blink_end`, returned from `Game.blinked` after the end-step triggers).

## Round 19: "choose one of them" after exiling the top cards

- "Exile the top N cards of your library. Choose one of them. You may play that card this turn / until the end of your
  next turn / until end of turn" (`choose_one_exiled` keeps the best exiled card playable; the rest stay exiled).
- Not done: "Sacrifice that token at the beginning of the next end step" after token creation needs `create_token` to
  report the tokens it made; deferred until the `engine/play.py` split lands.

## Forge comparison cards: Demolition Field, Esper Origins, Uldaros Theorix

- Demolition Field: destroys a nonbasic land; both players fetch a basic land untapped (`land_swap` with `both`).
- Esper Origins: flashback now puts the card onto the battlefield as Summon: Esper Maduin with a finality counter
  (`flip_from_gy`, handled when the flashback spell finishes resolving); chapter I reveals the top card and takes it
  if it is a permanent (`reveal_top_to_hand`).
- Uldaros Theorix: exiles the best nonland card of each type from the graveyard and casts free spells totalling mana
  value 6 or less (`gy_type_spree`). Approximation, flagged in `--coverage`: the exiled cards themselves are cast,
  not token copies.

## Dimir Midrange: Wan Shi Tong, Librarian and Tishana's Tidebinder

- Wan Shi Tong: "put X +1/+1 counters on him" (`p1_counters` with `x: entered`), "draw half X cards, rounded down"
  (`draw` with `x_half`) and "whenever an opponent searches their library" (event `opp_searches`, fired by
  `Game.library_searched` from every search site: tutors, basic-land fetches, the search template, Deadly-style
  searches and Demolition Field).
- Tishana's Tidebinder: `counter_ability` removes the newest activated or triggered ability an opponent has on the
  stack; if its source is an artifact, creature or planeswalker still out, that permanent is `silenced_by` the
  Tidebinder (no keywords, triggers, activated or loyalty abilities while the Tidebinder stays). The AI flashes it in
  against a valuable permanent's ability or a planeswalker activation.
- Not done: Kaito, Bane of Nightmares (Ninjutsu, "during your turn he is a 3/4 Ninja", the Ninja emblem).

## Dimir Midrange: Kaito, Bane of Nightmares

- Ninjutsu: alt cost `ninjutsu`, played through the sneak hook (the AI returns its weakest unblocked attacker); the
  card enters tapped and attacking even when it is not a creature card.
- "During your turn, as long as ~ has loyalty counters on him, he's a 3/4 Ninja creature and has hexproof":
  `CardDef.turn_creature`, applied by `animate_turn_creatures` at the start of the controller's turn and when the
  card enters on that turn; the end-of-turn cleanup removes it.
- Emblems: `Player.emblems` holds (creature type, +power, +toughness); "you get an emblem with 'Ninjas you control get
  +1/+1'" is the `emblem` kind. Other emblem texts are not parsed.
- Not done: Kaito's -9 emblem, combat damage dealt to Kaito as a creature does not remove loyalty counters.
