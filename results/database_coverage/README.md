# Entire local card database coverage

Measured 2026-10-18 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 8,043 | 23.03% |
| Matched with recorded simplifications | 97 | 0.28% |
| Partly supported | 26,782 | 76.69% |
| Could not parse | 0 | 0.00% |
| Total | 34,922 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 14,290 cards; 8,973 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| triggered (whenever/when) | 2,406 | 4,537 | A Good Day to Die; A Good Day to Pie; Aang and Katara |
| activated abilities | 2,323 | 3,340 | A Container of Booster Packs; A-Town; Aang's Iceberg |
| counters | 2,082 | 3,463 | Abomination, Irradiated Brute; Aboroth; Abzan Charm |
| graveyard | 1,483 | 2,966 | "Rumors of My Death . . ."; A Good Day to Pie; Aang, A Lot to Learn |
| sacrifice | 1,318 | 2,469 | Aang's Iceberg; Abjure; Abyssal Gatekeeper |
| tokens | 1,139 | 2,391 | Aang and Katara; Aatchik, Emerald Radian; Abyssal Harvester |
| exile | 1,053 | 2,422 | "Rumors of My Death . . ."; A Container of Booster Packs; Abstergo Entertainment |
| auras/enchant | 994 | 1,258 | Abduction; Aboshan's Desire; Absorbing Man |
| can't restrictions | 761 | 1,532 | Abeyance; Abyssal Persecutor; Academic Probation |
| X costs | 662 | 1,281 | Aang and Katara; Abaddon the Despoiler; Aberrant Manawurm |
| equipment | 493 | 692 | Ace's Baseball Bat; Acid Web Spider; Adaptive Omnitool |
| copy effects | 334 | 710 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| library search | 264 | 542 | Aerial Surveyor; Amrou Scout; Angel's Herald |
| cost reduction | 201 | 422 | Absorb Energy; Acolyte of Bahamut; Ancient Stone Idol |
| +1/+1 static (anthems) | 133 | 279 | Aardwolf's Advantage; Akoum Battlesinger; Always Watching |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| infect | 24 | 45 | Blackcleave Goblin; Blighted Agent; Blightwidow |
| devoid | 23 | 134 | Blinding Drone; Complete Disregard; Consuming Sinkhole |
| exalted | 22 | 35 | Akrasan Squire; Aven Squire; Battlegrace Angel |
| ~ can block only creatures with flying. | 22 | 31 | Battlefield Percher; Belbe's Percher; Brazen Borrower // Petty Theft |
| storm | 21 | 40 | Astral Steel; Brain Freeze; Chatterstorm |
| it can't be regenerated. | 19 | 49 | Annihilate; Befoul; Cruel Revival |
| the ring tempts you. | 18 | 30 | Bilbo, Retired Burglar; Birthday Escape; Bombadil's Song |
| cascade | 17 | 34 | Annoyed Altisaur; Bituminous Blast; Bloodbraid Elf |
| forestwalk | 17 | 26 | Cat Warriors; Elite Cat Warrior; Emerald Oryx |
| improvise | 16 | 24 | Arc Reactor; Barricade Breaker; Bastion Inventor |
| shroud | 15 | 38 | Argothian Enchantress; Blurred Mongoose; Deadly Insect |
| rebound | 15 | 36 | Artful Maneuver; Faithless Salvaging; Fantastic Elasticity |
| {b}: regenerate ~. | 15 | 31 | Darkling Stalker; Drudge Reavers; Drudge Skeletons |
| draw a card at the beginning of the next turn's upkeep. | 14 | 47 | Blessed Wine; Carrier Pigeons; Feral Instinct |
| fear | 14 | 37 | Crowd of Cinders; Dross Golem; Dross Prowler |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
