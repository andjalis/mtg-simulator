# Entire local card database coverage

Measured 2026-10-28 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 8,647 | 24.76% |
| Matched with recorded simplifications | 104 | 0.30% |
| Partly supported | 26,171 | 74.94% |
| Could not parse | 0 | 0.00% |
| Total | 34,922 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 13,602 cards; 8,598 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| triggered (whenever/when) | 2,485 | 4,508 | A Good Day to Die; A Good Day to Pie; Aang and Katara |
| activated abilities | 2,287 | 3,239 | A Container of Booster Packs; A-Town; Aang's Iceberg |
| counters | 2,069 | 3,387 | Abomination, Irradiated Brute; Aboroth; Academy Elite |
| graveyard | 1,506 | 2,934 | "Rumors of My Death . . ."; A Good Day to Pie; Aang, A Lot to Learn |
| sacrifice | 1,343 | 2,427 | Aang's Iceberg; Abjure; Abyssal Gatekeeper |
| tokens | 1,167 | 2,379 | Aang and Katara; Aatchik, Emerald Radian; Abyssal Harvester |
| exile | 1,084 | 2,414 | "Rumors of My Death . . ."; A Container of Booster Packs; Abstergo Entertainment |
| auras/enchant | 995 | 1,252 | Abduction; Aboshan's Desire; Absorbing Man |
| can't restrictions | 757 | 1,480 | Abeyance; Abyssal Persecutor; Academic Probation |
| X costs | 669 | 1,279 | Aang and Katara; Abaddon the Despoiler; Aberrant Manawurm |
| equipment | 486 | 683 | Ace's Baseball Bat; Acid Web Spider; Adaptive Omnitool |
| copy effects | 340 | 709 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| library search | 273 | 539 | Aerial Surveyor; Amrou Scout; Angel's Herald |
| cost reduction | 209 | 421 | Absorb Energy; Acolyte of Bahamut; Ancient Stone Idol |
| +1/+1 static (anthems) | 133 | 276 | Aardwolf's Advantage; Akoum Battlesinger; Always Watching |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| the ring tempts you. | 18 | 31 | Bilbo, Retired Burglar; Birthday Escape; Bombadil's Song |
| you may draw a card. | 15 | 46 | Aesi, Tyrant of Gyre Strait; Aven Fisher; Drumhunter |
| protection from black | 15 | 28 | Cemetery Gate; Chameleon Colossus; Darkwatch Elves |
| return a land you control to its owner's hand. | 14 | 15 | Azorius Chancery; Boros Garrison; Dimir Aqueduct |
| protection from white | 13 | 21 | Black Knight; Defender of Chaos; Disciple of Malice |
| when ~ becomes the target of a spell or ability, sacrifice it. | 13 | 15 | Frost Walker; Gossamer Phantasm; Illusionary Servant |
| exile ~. | 12 | 100 | Ascend from Avernus; Divergent Equation; Flood of Recollection |
| ~ can't attack unless defending player controls an island. | 12 | 26 | Armored Galleon; Deep-Sea Serpent; Ethereal Whiskergill |
| backup 1 | 12 | 20 | Boon-Bringer Valkyrie; Chomping Kavu; Consuming Aetherborn |
| it has "sacrifice ~: add {c}." | 12 | 17 | Blisterpod; Brood Butcher; Carrier Thrall |
| target creature gains flying until end of turn. | 12 | 16 | Cloak of Feathers; Defy Gravity; Gale Swooper |
| you may put a +1/+1 counter on ~. | 12 | 16 | Bojuka Brigand; Graypelt Hunter; Hada Freeblade |
| flanking | 11 | 27 | Benalish Cavalry; Burning Shield Askari; Cadaverous Knight |
| myriad | 11 | 19 | Caller of the Pack; Chittering Dispatcher; Conclave Evangelist |
| ~ doesn't untap during your untap step. | 10 | 38 | Basalt Monolith; Brass Gnat; Brass Man |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
