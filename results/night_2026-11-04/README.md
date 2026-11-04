# Entire local card database coverage

Measured 2026-11-04 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 17,113 | 50.14% |
| Matched with recorded simplifications | 385 | 1.13% |
| Partly supported | 16,632 | 48.73% |
| Could not parse | 0 | 0.00% |
| Total | 34,130 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 7,739 cards; 5,231 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| counters | 1,617 | 2,278 | A-Bretagard Stronghold; A-Dueling Coach; A-Iridescent Hornbeetle |
| triggered (whenever/when) | 1,476 | 2,264 | A Display of My Dark Power; A Good Day to Die; A Good Day to Pie |
| activated abilities | 1,423 | 1,797 | A-Baba Lysaga, Night Witch; A-Bretagard Stronghold; A-Carnelian Orb of Dragonkind |
| graveyard | 1,210 | 2,068 | A Good Day to Pie; A-Cauldron Familiar; A-Dragon's Rage Channeler |
| tokens | 1,013 | 1,666 | A-Alrund's Epiphany; A-Iridescent Hornbeetle; A-Ocelot Pride |
| exile | 940 | 1,700 | A-Fall of the Impostor; A-Glamorous Outlaw; A-Masked Bandits |
| sacrifice | 903 | 1,424 | A-Baba Lysaga, Night Witch; A-Baleful Beholder; A-Bretagard Stronghold |
| auras/enchant | 651 | 750 | A-Mightstone's Animation; A-Precipitous Drop; A-Public Enemy |
| X costs | 619 | 1,041 | A-Earthquake Dragon; A-Maelstrom Muse; A-Pyre-Sledge Arsonist |
| can't restrictions | 566 | 921 | A-Futurist Operative; A-Goma Fada Vanguard; Abyssal Persecutor |
| equipment | 351 | 448 | A-Ancestral Katana; A-Bruenor Battlehammer; A-Goma Fada Vanguard |
| copy effects | 332 | 594 | A-Leyline of Resonance; A-Mentor's Guidance; A-Ocelot Pride |
| cost reduction | 203 | 345 | A-Cosmos Charger; A-Knockout Blow; A-Peerless Samurai |
| library search | 200 | 376 | 70,000 Light-Years from Home; A-Navigation Orb; A-Phantom Carriage |
| +1/+1 static (anthems) | 117 | 187 | A-Narfi, Betrayer King; A-Saheeli, Filigree Master; Akoum Battlesinger |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| if it shares a creature type with ~, you may reveal it. | 11 | 12 | Ink Dissolver; Kithkin Zephyrnaut; Mudbutton Clanger |
| banding | 10 | 13 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| open an attraction. | 9 | 18 | Coming Attraction; Deadbeat Attendant; Discourtesy Clerk |
| draft a card from ~'s spellbook. | 9 | 15 | Boseiju Pathlighter; Cursebound Witch; Emmara, Voice of the Conclave |
| double team | 8 | 18 | Amber-Plate Ainok; Giant Fire Beetles; Lizardfolk Librarians |
| ~ becomes prepared. | 8 | 12 | Abigale, Poet Laureate // Heroic Stanza; Bloodline Recollector // Ancestral Craving; Eiganjo Dynastorian |
| return that card to the battlefield under your control. | 6 | 7 | False Demise; Fool's Demise; Minion's Return |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| you may cast ~ as though it had flash. if you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step. | 5 | 10 | Lightning Reflexes; Mystic Veil; Parapet |
| change the target of target spell with a single target. | 5 | 6 | Deflection; Imp's Mischief; Misdirection |
| sacrifice it unless you return a non-lair land you control to its owner's hand. | 5 | 5 | Crosis's Catacombs; Darigaaz's Caldera; Dromar's Cavern |
| when a creature with mana value 6 or greater enters, you may return ~ from your graveyard to the battlefield attached to that creature. | 5 | 5 | Dragon Breath; Dragon Fangs; Dragon Scales |
| you may flip it. | 5 | 5 | Budoka Pupil // Ichiga, Who Topples Oaks; Callow Jushi // Jaraku the Interloper; Cunning Bandit // Azamuki, Treachery Incarnate |
| copy it for each time you've cast your commander from the command zone this game. | 4 | 6 | Echo Storm; Empyrial Storm; Fury Storm |
| if you control a commander, you may cast ~ without paying its mana cost. | 4 | 5 | Deadly Rollick; Fierce Guardianship; Flawless Maneuver |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
