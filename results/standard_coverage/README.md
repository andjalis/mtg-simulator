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

## Re-measure after rounds 1–15 (2026-10-20)

Measured on `docs/standard-coverage-remeasure`, based on current `main` at `63aa2df`;
engine and card templates unchanged. This reproduces the **saved** 20-set WOE–FRA
snapshot (4,902 distinct non-basic cards), rather than refreshing format legality or
card text. Uses the existing local Forge-built database, bundled cards and local
cache in the normal `CardDB` lookup order, offline. Input SHA-256 hashes and Python
version are in [remeasure.json](remeasure.json); the database is generated and not
committed. Older reports did not record all these hashes, so exact input identity
with those runs cannot be established.

Reproduce from the repo root with the card database present:

```sh
python3 -m mtgsim.standard_coverage --top 20
python3 -m results.standard_coverage.remeasure
python3 -W ignore::ResourceWarning -m unittest tests.test_standard_coverage tests.test_coverage
```

The second command writes the summary and rankings to [remeasure.txt](remeasure.txt)
and their machine-readable counts, examples and input hashes to `remeasure.json`.
Checks: both commands exited 0; 22 coverage tests passed in 7.524 s. The CLI summary
matches the summary generated by the ranking script. No engine changes or games;
the full suite was not rerun for this measurement/documentation task.

| Metric | Earlier full report (`6cabebf`) | Now (`63aa2df`) |
| --- | ---: | ---: |
| Fully supported | 726 (14.8%) | 1,810 (36.9%) |
| Simplified | 38 (0.8%) | 42 (0.9%) |
| Partly supported | 4,138 (84.4%) | 3,050 (62.2%) |
| Unknown | 0 | 0 |
| Partly supported, missing exactly one line | 2,135 | 1,933 |
| Rules sentences handled (rough) | 4,908 / 12,933 (38%) | 7,661 / 12,933 (59%) |

The full-support count agrees with the round-15 note above (1,810); the progress
log's 14.8% figure was stale. These are template matches, including existing
approximations, rather than a gameplay correctness audit. Remaining leading ignored
families are counters (594 cards), triggers (521), graveyard (433), tokens (361),
exile (322) and activated abilities (316); families overlap.

### Top 20 unmatched rules sentences / lines

Rank exact ignored text across all partly supported cards, counting each card once
per line. The coverage tool emits ignored parser units: these can be a sentence,
keyword, multi-sentence clause or leftover fragment. Keep those units intact so
this ranking points back to actual template misses. Remove only the face-name
prefix that coverage adds to back/adventure faces; retain `~` self-name placeholders,
case and punctuation. Ties sort alphabetically. Examples are card names from the
snapshot; the rankings do not imply standalone implementation is safe (for example,
“Put the rest…” requires the preceding selection's context).

| Cards | Unmatched text | Example cards |
| ---: | --- | --- |
| 18 | Put the rest on the bottom of your library in a random order. | Aang, at the Crossroads; Break Out; Cosmic Cube |
| 10 | Exile ~. | Avatar's Wrath; Divergent Equation; Morningtide's Light |
| 10 | You may look at the top card of your library any time. | Assemble the Players; Fblthp, Lost on the Range; Glarb, Calamity's Augur |
| 9 | Storied | Balin, Loremaster; Bifur, Melodic Rider; Bombur, Gentle Dreamer |
| 7 | Target opponent reveals their hand. | Aggressive Negotiations; Binding Negotiation; Cruelclaw's Heist |
| 7 | look at the top five cards of your library. | Aang, at the Crossroads; Freestrider Lookout; Living Phone |
| 6 | Put the rest into your graveyard. | Earth's Mightiest Heroes; Gurmag Nightwatch; Gutless Plunderer |
| 6 | Tiered | Fire Magic; Ice Magic; Restoration Magic |
| 5 | A deck can have any number of cards named ~. | Cid, Timeless Artificer; Hare Apparent; Slime Against Humanity |
| 5 | If you do, draw two cards. | Byway Barterer; Highway Robbery; Stormshriek Feral |
| 5 | Paradigm | Decorum Dissertation; Echocasting Symposium; Germination Practicum |
| 5 | Untap that creature. | Evil's Thrall; Fleeting Reflection; Restless Ridgeline |
| 5 | look at the top card of your library. | Gathering Stone; Mobile Homestead; Planetarium of Wan Shi Tong |
| 5 | return the exiled card to its owner's hand. | Champion of the Clachan; Champion of the Path; Champion of the Weird |
| 5 | ~ enters tapped unless you control a Mount or Vehicle. | Country Roads; Foul Roads; Reef Roads |
| 4 | Exile that card. | Cruelclaw's Heist; Intimidation Tactics; Null Summoner |
| 4 | Put one of them into your hand and the other into your graveyard. | Codecracker Hound; Marchesa, Dealer of Death; Sibsig Appraiser |
| 4 | Return that card to the battlefield under its owner's control at the beginning of the next end step. | Conciliator's Duelist; Ennis, Debate Moderator; S.H.I.E.L.D. Flying Car |
| 4 | Sacrifice them at the beginning of the next end step. | Devastating Onslaught; Push // Pull; Push the Limit |
| 4 | Target creature's owner puts it on their choice of the top or bottom of their library. | Return to the Sewers; Run Behind; Uncharted Voyage |

### Top 20 misses on cards missing exactly one line

Same ranking method restricted to the 1,933 one-line-miss cards. The highest exact
frequency is now only three cards, so template selection should also group related
wording variants and weigh implementation cost. Matching the last line can produce
either fully supported or simplified status, depending on existing approximations.

| Cards | Unmatched text | Example cards |
| ---: | --- | --- |
| 3 | Paradigm | Decorum Dissertation; Germination Practicum; Restoration Seminar |
| 3 | The flashback cost is equal to its mana cost. | Flashback; Slickshot Lockpicker; Stingcaster Mage |
| 3 | Void — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on ~. | Insatiable Skittermaw; Interceptor Mechan; Kavaron Skywarden |
| 3 | manifest dread, then attach ~ to that creature. | Conductive Machete; Cursed Windbreaker; Killer's Mask |
| 3 | put its counters on target creature you control. | Broodguard Elite; Dockworker Drone; Hei Bai, Spirit of Balance |
| 3 | ~ becomes prepared. | Abigale, Poet Laureate; Kirol, History Buff; Scathing Shadelock |
| 2 | Alliance — Whenever another creature you control enters, ~ gets +1/+0 until end of turn. | East Wind Avatar; Mutant Town Musicians |
| 2 | As long as an artifact entered the battlefield under your control this turn, ~ can attack as though it didn't have defender. | Mechan Shieldmate; Shipwreck Sentry |
| 2 | Choose one of them. | Riverwheel Sweep; Strongbox Raider |
| 2 | Each player may discard their hand and draw seven cards. | Raphael's Technique; Variable Chaser |
| 2 | Enchanted permanent loses all abilities and doesn't untap during its controller's untap step. | Flood the Engine; Stop Cold |
| 2 | Exile ~. | Divergent Equation; Spirit Water Revival |
| 2 | If that spell is countered this way, exile it instead of putting it into its owner's graveyard. | No More Lies; Syncopate |
| 2 | Its controller manifests dread. | Fear of Impostors; Unwanted Remake |
| 2 | Raid — ~ enters with a +1/+1 counter on it if you attacked this turn. | Cruel Administrator; Goblin Boarders |
| 2 | Return it to the battlefield under its owner's control at the beginning of the next end step. | Explosive Getaway; Twining Twins |
| 2 | Sacrifice it at the beginning of the next end step. | Molten Duplication; War Effort |
| 2 | Suspect it. | Caught Red-Handed; It Doesn't Add Up |
| 2 | Whenever another creature you control enters while ~ has a -1/-1 counter on it, remove a -1/-1 counter from ~. | Bristlebane Battler; Reluctant Dounguard |
| 2 | Whenever equipped creature attacks, tap target creature defending player controls. | Captain America's Shield; Thunder Lasso |

Suggested next round: inspect becomes-prepared, flashback-cost and Raid wording
variants first, then assess manifest-and-attach and delayed sacrifice/return effects.
Paradigm and Void need mechanic/event support; they are not necessarily cheap merely
because they occur on several otherwise matched cards. Deck-construction text and
library-selection remnants in the overall ranking need separate review before being
counted as engine gains.

## Round 16: prepared rearming, granted-flashback costs and Raid (2026-10-20)

Added three bounded general patterns, after inspecting the round-15 single-line
misses above:

- `~ becomes prepared` now prepares the live source permanent. Casting its spell
  copy consumes preparation; a later matched trigger can prepare it again.
  Multiple triggers do not accumulate extra copies, and a departed source cannot
  prepare a newly entered object. Unmatched conditions and pronoun variants remain
  visible in coverage.
- The flashback grant plus `The flashback cost is equal to its mana cost.` is
  parsed as one effect using the existing mana-cost flashback variant. The
  continuation is consumed only with that grant, not as a standalone sentence.
  Tests verify payment, exile after casting, and cleanup expiry. Existing
  approximation: the engine picks the highest-mana-value eligible spell when the
  grant resolves, rather than selecting a normal graveyard target at cast time.
- `Raid — ~ enters with a +1/+1 counter on it if you attacked this turn.` uses
  the existing entry-counter condition, checking the controller's attack history.

Same offline 4,902-card snapshot and input hashes as the dated baseline:

| Metric | Before (`remeasure.json`) | After (`round16.json`) |
| --- | ---: | ---: |
| Fully template-matched | 1,810 (36.9%) | 1,818 (37.1%) |
| Simplified | 42 | 42 |
| Partly supported | 3,050 | 3,042 |
| Unknown | 0 | 0 |
| Missing exactly one line | 1,933 | 1,927 |
| Rules sentences handled (rough) | 7,661 / 12,933 | 7,671 / 12,933 |

The eight newly fully matched cards are Abigale, Poet Laureate; Kirol, History
Buff; Scathing Shadelock; Flashback; Slickshot Lockpicker; Stingcaster Mage;
Cruel Administrator; and Goblin Boarders. The small coverage fixture in
`decks/coverage/round16.txt` improves from 0/8 to 8/8 fully matched; it is not a
playable deck. Reports are saved in [round16-deck-before.txt](round16-deck-before.txt)
and [round16-deck-after.txt](round16-deck-after.txt).

Reproduce the after measurement without overwriting the dated baseline:

```sh
python3 -m results.standard_coverage.round16
python3 -m mtgsim decks/coverage/round16.txt --offline --coverage
python3 -W ignore::ResourceWarning -m unittest tests.test_round16 tests.test_prepared_convoke tests.test_round12
```

The first command writes [round16.txt](round16.txt) and `round16.json`, retaining
the baseline's counting and ranking method. The focused mechanic check passed
28 tests; an independent review ran 73 tests across the new fixtures, prepared
spells and existing templates. Full-suite results are recorded in the project
progress log. Matching text still does not establish complete rules correctness.

## Three engine follow-ups (2026-10-20)

The same offline snapshot and identical card DB, builtin, cache and snapshot hashes
were measured immediately before and after these changes. Distinct reports preserve
the earlier baseline and round-16 artifacts:
[before](three-followups-before.txt), [after](three-followups-after.txt), and the
corresponding `three-followups-before.json` / `three-followups-after.json` rankings.

| Metric | Before | After |
| --- | ---: | ---: |
| Fully template-matched | 1,818 (37.1%) | 1,833 (37.4%) |
| Simplified | 42 | 42 |
| Partly supported | 3,042 | 3,027 |
| Unknown | 0 | 0 |
| Missing exactly one line | 1,927 | 1,920 |
| Rules sentences handled (rough) | 7,671 / 12,933 | 7,700 / 12,933 |

- Manifest dread plus attachment binds the source Equipment to the exact new 2/2,
  with no attachment when the library is empty. It also matches Dissection Tools;
  that card's two unrelated Equipment lines remain unsupported.
- Exact single-target exile/return pairs use a shared one-time end-step scheduler.
  Returns track the exiled zone object, survive source departure, and return a new
  permanent under its owner's control. The matched flying-counter variant grants
  flying. Conditional, plural, return-to-hand and unbound pronoun variants stay visible.
- Token/copy creation binds directly following haste and delayed sacrifice clauses
  to its created objects. Both `the next` and `your next` end-step scopes are tested.
  Copy tokens created on the opponent's turn no longer wait for their controller's
  end step. Quoted granted end-step abilities remain ordinary triggered abilities.
- Aura hosts are spell targets chosen when casting, with ward, responses, legality
  checks and failure without retargeting. This improves fidelity without changing
  template coverage. Friendly/hostile default selection and non-spell Role/Equipment
  attachments are preserved.

The diagnostic fixture `decks/coverage/three_followups.txt` improves from 0/12 to
11/12 fully matched; it is not a playable deck. Saved CLI output:
[before](three-followups-deck-before.txt), [after](three-followups-deck-after.txt).
Its before output was run using a temporary copy of the package reconstructed from
`63aa2df` plus the saved pre-task uncommitted card/engine diff (round 16), rather
than temporarily changing the shared workspace.

Reproduce the after reports from the repo root:

```sh
python3 -c 'from results.standard_coverage.remeasure import main; main("three-followups-after")'
python3 -m mtgsim decks/coverage/three_followups.txt --offline --coverage
python3 -W ignore::ResourceWarning -m unittest tests.test_three_followups tests.test_three_auras tests.test_auras tests.test_copies
```

These counts measure text recognition, not rules correctness or matchup accuracy.
No Forge games were run.

## Equipment sacrifice costs (2026-10-20)

General `Equip—Sacrifice a creature` and `Equipped creature has +N/+N`
wording now match, completing Dissection Tools. Demonmail Hauberk also matches
in the local database, but is outside this saved Standard snapshot. Restricted
sacrifice costs, mixed mana/sacrifice costs and conditional bonuses remain visible.

Equip now uses the ability stack, with payment before responses and a stored
target rechecked on resolution. Equipment keeps its previous attachment if
the new target becomes illegal. Cross-controller bonuses and attachment cleanup
follow [the Comprehensive Rules](https://media.wizards.com/2026/downloads/MagicCompRules%2020260619.pdf)
301.5b–d. These execution changes do not themselves increase template counts.

Identical offline input hashes; earlier reports are preserved:

| Metric | Before | After |
| --- | ---: | ---: |
| Fully template-matched | 1,833 | 1,834 |
| Simplified | 42 | 42 |
| Partly supported | 3,027 | 3,026 |
| Unknown | 0 | 0 |
| Missing exactly one line | 1,920 | 1,920 |
| Rules sentences handled (rough) | 7,700 / 12,933 | 7,702 / 12,933 |

Reports: [before](equipment-sacrifice-before.txt),
[after](equipment-sacrifice-after.txt), with matching `.json` files. The existing
`decks/coverage/three_followups.txt` diagnostic fixture improves from 11/12 to
12/12 fully matched; CLI output is saved separately as
[before](equipment-sacrifice-deck-before.txt) and
[after](equipment-sacrifice-deck-after.txt).

```sh
python3 -c 'from results.standard_coverage.remeasure import main; main("equipment-sacrifice-after")'
python3 -m mtgsim decks/coverage/three_followups.txt --offline --coverage
python3 -W ignore::ResourceWarning -m unittest tests.test_equipment_sacrifice tests.test_templates.EquipmentTests
```

Counts measure text recognition, including the existing simplified manifest dread
execution; they do not establish complete rules correctness or matchup accuracy.
