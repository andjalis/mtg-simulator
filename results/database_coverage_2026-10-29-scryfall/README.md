# Entire local card database coverage

Measured 2026-10-29 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 13,429 | 38.12% |
| Matched with recorded simplifications | 284 | 0.81% |
| Partly supported | 21,512 | 61.07% |
| Could not parse | 0 | 0.00% |
| Total | 35,225 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 10,331 cards; 6,809 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| activated abilities | 1,989 | 2,596 | A Container of Booster Packs; A-Town; Aang's Iceberg |
| counters | 1,948 | 2,837 | Aang, Airbending Master; Aang, Swift Savior // Aang and La, Ocean's Fury; Abomination, Irradiated Brute |
| triggered (whenever/when) | 1,805 | 2,965 | A Good Day to Die; A Good Day to Pie; Aang and Katara |
| graveyard | 1,566 | 2,724 | "Rumors of My Death . . ."; A Good Day to Pie; Aang, A Lot to Learn |
| tokens | 1,270 | 2,217 | Aang and Katara; Aatchik, Emerald Radian; Abhorrent Overlord |
| sacrifice | 1,164 | 1,938 | Aang's Iceberg; Abjure; Abyssal Gatekeeper |
| exile | 1,073 | 2,096 | "Rumors of My Death . . ."; A Container of Booster Packs; Abdel Adrian, Gorion's Ward |
| auras/enchant | 828 | 969 | Aboshan's Desire; Absorbing Man; Abzan Runemark |
| X costs | 735 | 1,230 | Aang and Katara; Abaddon the Despoiler; Abzan Monument |
| can't restrictions | 693 | 1,229 | Abyssal Persecutor; Academic Probation; Aether Storm |
| equipment | 428 | 570 | Ace's Baseball Bat; Acquisition Octopus; Adaptive Omnitool |
| copy effects | 376 | 711 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| library search | 259 | 486 | Aerial Surveyor; Amrou Scout; Andromedan Automatons |
| cost reduction | 197 | 383 | Absorb Energy; Acolyte of Bahamut; Alisaie Leveilleur |
| +1/+1 static (anthems) | 135 | 221 | Aardwolf's Advantage; Akoum Battlesinger; Alistair, the Brigadier |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| venture into the dungeon. | 12 | 22 | Bar the Gate; Clattering Skeletons; Delver's Torch |
| banding | 10 | 14 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| cast ~ only during the declare attackers step and only if you've been attacked this step. | 10 | 14 | Assassin's Blade; Champion's Victory; Defiant Stand |
| you may return this card from your graveyard to your hand. | 10 | 11 | Aurora Eidolon; Enigma Eidolon; Entropic Eidolon |
| return the exiled card to the battlefield under its owner's control. | 8 | 13 | Faceless Butcher; Faceless Devourer; Fiend Hunter |
| open an attraction. | 7 | 17 | Coming Attraction; Deadbeat Attendant; Petting Zookeeper |
| draft a card from ~'s spellbook. | 7 | 13 | Boseiju Pathlighter; Cursebound Witch; Emmara, Voice of the Conclave |
| each player sacrifices a creature of their choice. | 7 | 10 | Abyssal Gatekeeper; Fleshbag Marauder; Innocent Blood |
| exile ~ with three time counters on it. | 7 | 10 | Arc Blade; Charnel Serenade; Cyclical Evolution |
| if you do, return this card from your graveyard to your hand. | 6 | 12 | Lingering Phantom; Masked Admirers; Redtooth Vanguard |
| phasing | 6 | 12 | Breezekeeper; Merfolk Raiders; Sandbar Crocodile |
| ~ costs {1} less to cast for each creature in your party. | 6 | 10 | Deadly Alliance; Journey to Oblivion; Sea Gate Colossus |
| as an additional cost to cast ~, exile a creature card from your graveyard. | 6 | 8 | Cobbled Lancer; Headless Skaab; Makeshift Mauler |
| return that card to the battlefield under your control. | 6 | 7 | False Demise; Fool's Demise; Minion's Return |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
