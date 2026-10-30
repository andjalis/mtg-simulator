# Entire local card database coverage

Measured 2026-10-30 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 13,685 | 38.85% |
| Matched with recorded simplifications | 286 | 0.81% |
| Partly supported | 21,254 | 60.34% |
| Could not parse | 0 | 0.00% |
| Total | 35,225 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 10,217 cards; 6,805 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| activated abilities | 1,983 | 2,577 | A Container of Booster Packs; A-Town; Aang's Iceberg |
| counters | 1,952 | 2,829 | Aang, Airbending Master; Aang, Swift Savior // Aang and La, Ocean's Fury; Abomination, Irradiated Brute |
| triggered (whenever/when) | 1,783 | 2,905 | A Good Day to Die; A Good Day to Pie; Aang and Katara |
| graveyard | 1,546 | 2,620 | "Rumors of My Death . . ."; A Good Day to Pie; Aang, A Lot to Learn |
| tokens | 1,266 | 2,191 | Aang and Katara; Aatchik, Emerald Radian; Abhorrent Overlord |
| sacrifice | 1,104 | 1,823 | Aang's Iceberg; Abjure; Abzan Advantage |
| exile | 1,072 | 2,059 | "Rumors of My Death . . ."; A Container of Booster Packs; Abdel Adrian, Gorion's Ward |
| auras/enchant | 814 | 953 | Aboshan's Desire; Absorbing Man; Abzan Runemark |
| X costs | 729 | 1,218 | Aang and Katara; Abaddon the Despoiler; Abzan Monument |
| can't restrictions | 690 | 1,220 | Abyssal Persecutor; Academic Probation; Aether Storm |
| equipment | 429 | 569 | Ace's Baseball Bat; Acquisition Octopus; Adaptive Omnitool |
| copy effects | 373 | 701 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| library search | 261 | 478 | Aerial Surveyor; Amrou Scout; Andromedan Automatons |
| cost reduction | 197 | 383 | Absorb Energy; Acolyte of Bahamut; Alisaie Leveilleur |
| +1/+1 static (anthems) | 136 | 221 | Aardwolf's Advantage; Akoum Battlesinger; Alistair, the Brigadier |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| venture into the dungeon. | 12 | 22 | Bar the Gate; Clattering Skeletons; Delver's Torch |
| banding | 10 | 14 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| cast ~ only during the declare attackers step and only if you've been attacked this step. | 10 | 14 | Assassin's Blade; Champion's Victory; Defiant Stand |
| open an attraction. | 7 | 17 | Coming Attraction; Deadbeat Attendant; Petting Zookeeper |
| draft a card from ~'s spellbook. | 7 | 13 | Boseiju Pathlighter; Cursebound Witch; Emmara, Voice of the Conclave |
| exile ~ with three time counters on it. | 7 | 10 | Arc Blade; Charnel Serenade; Cyclical Evolution |
| phasing | 6 | 12 | Breezekeeper; Merfolk Raiders; Sandbar Crocodile |
| ~ costs {1} less to cast for each creature in your party. | 6 | 10 | Deadly Alliance; Journey to Oblivion; Sea Gate Colossus |
| as an additional cost to cast ~, exile a creature card from your graveyard. | 6 | 8 | Cobbled Lancer; Headless Skaab; Makeshift Mauler |
| return that card to the battlefield under your control. | 6 | 7 | False Demise; Fool's Demise; Minion's Return |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| you take the initiative. | 5 | 21 | Aarakocra Sneak; Avenging Hunter; Explore the Underdark |
| until end of turn, you don't lose this mana as steps and phases end. | 5 | 16 | Brazen Collector; Colossal Plow; Qo'noS Quartermaster |
| for mirrodin! | 5 | 15 | Dragonwing Glider; Goldwarden's Helm; Mirran Bardiche |
| you may cast ~ as though it had flash. if you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step. | 5 | 10 | Lightning Reflexes; Mystic Veil; Parapet |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
