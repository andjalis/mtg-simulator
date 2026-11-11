# Entire local card database coverage

Measured 2026-11-11 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 20,142 | 57.68% |
| Matched with recorded simplifications | 207 | 0.59% |
| Partly supported | 14,573 | 41.73% |
| Could not parse | 0 | 0.00% |
| Total | 34,922 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 6,985 cards; 4,676 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| counters | 1,426 | 2,008 | Aang, Airbending Master; Aboroth; Ace, Fearless Rebel |
| triggered (whenever/when) | 1,337 | 2,027 | A Girl and Her Dogs; A Good Day to Pie; Aang, at the Crossroads // Aang, Destined Savior |
| activated abilities | 1,204 | 1,528 | A Container of Booster Packs; A-Town; Abuna Acolyte |
| graveyard | 1,092 | 1,818 | "Rumors of My Death . . ."; A Good Day to Pie; Aatchik, Emerald Radian |
| exile | 910 | 1,597 | "Rumors of My Death . . ."; A Container of Booster Packs; Abdel Adrian, Gorion's Ward |
| tokens | 828 | 1,352 | A Girl and Her Dogs; Aatchik, Emerald Radian; Abyssal Harvester |
| sacrifice | 763 | 1,222 | Abjure; Ace, Fearless Rebel; Acidic Dagger |
| auras/enchant | 597 | 694 | Absorbing Man; Academy Researchers; Aerial Modification |
| X costs | 508 | 856 | Abaddon the Despoiler; Accessories to Murder; Aether Burst |
| can't restrictions | 462 | 783 | Abyssal Persecutor; Academic Probation; Agatha of the Vile Cauldron |
| copy effects | 336 | 580 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| equipment | 333 | 422 | Ace's Baseball Bat; Aegis of the Legion; Aettir and Priwen |
| library search | 177 | 340 | 70,000 Light-Years from Home; Angel's Herald; Arachnus Spinner |
| cost reduction | 137 | 253 | Absorb Energy; Acolyte of Bahamut; Alisaie Leveilleur |
| transform | 67 | 106 | Aang, at the Crossroads // Aang, Destined Savior; Afflicted Deserter // Werewolf Ransacker; Archangel Avacyn // Avacyn, the Purifier |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| open an attraction. | 11 | 18 | Coming Attraction; Complaints Clerk; Deadbeat Attendant |
| banding | 10 | 14 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| draft a card from ~'s spellbook. | 9 | 13 | Bladehold Cleaver; Boseiju Pathlighter; Cursebound Witch |
| an "instead" effect without the effect it replaces. | 9 | 10 | Desolation Angel; Dispense Justice; Necra Sanctuary |
| if you do, ~ assigns no combat damage this turn. | 7 | 12 | Dwarven Vigilantes; Farrel's Zealot; Laccolith Grunt |
| double team | 6 | 16 | Amber-Plate Ainok; Dragonblood Twins; Lizardfolk Librarians |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| you may cast ~ as though it had flash. if you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step. | 5 | 10 | Lightning Reflexes; Mystic Veil; Parapet |
| spell commander | 5 | 5 | Clear, the Mind; Gather, the Townsfolk; Lava, Axe |
| when a creature with mana value 6 or greater enters, you may return this card from your graveyard to the battlefield attached to that creature. | 5 | 5 | Dragon Breath; Dragon Fangs; Dragon Scales |
| as an additional cost to cast ~, discard x cards. | 4 | 10 | Channeled Force; Nostalgic Dreams; Restless Dreams |
| copy it for each time you've cast your commander from the command zone this game. | 4 | 6 | Echo Storm; Empyrial Storm; Fury Storm |
| spells your opponents cast that target ~ cost {2} more to cast. | 4 | 6 | Boreal Elemental; Charix, the Raging Isle; Icefall Regent |
| if you control a commander, you may cast ~ without paying its mana cost. | 4 | 5 | Deadly Rollick; Fierce Guardianship; Flawless Maneuver |
| if you don't put the card into your hand, you may put it into your graveyard. | 4 | 5 | Archghoul of Thraben; Sarinth Steelseeker; Territory Culler |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
