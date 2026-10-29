# Entire local card database coverage

Measured 2026-10-29 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 12,557 | 36.79% |
| Matched with recorded simplifications | 242 | 0.71% |
| Partly supported | 21,330 | 62.50% |
| Could not parse | 0 | 0.00% |
| Total | 34,129 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 10,299 cards; 6,767 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| triggered (whenever/when) | 2,009 | 3,222 | A Display of My Dark Power; A Good Day to Die; A Good Day to Pie |
| activated abilities | 1,920 | 2,527 | A-Baba Lysaga, Night Witch; A-Carnelian Orb of Dragonkind; A-Dungeon Descent |
| counters | 1,899 | 2,777 | A-Briar Hydra; A-Celebrity Fencer; A-Celestial Regulator |
| graveyard | 1,500 | 2,660 | A Good Day to Pie; A-Ardent Dustspeaker; A-Cobbled Lancer |
| tokens | 1,216 | 2,136 | A-Elderleaf Mentor; A-Elven Bow; A-Esika's Chariot |
| sacrifice | 1,111 | 1,854 | A-Baba Lysaga, Night Witch; A-Capenna Express; A-Forge Boss |
| exile | 1,038 | 2,055 | A-Ardent Dustspeaker; A-Cobbled Lancer; A-Elderfang Ritualist |
| auras/enchant | 825 | 997 | A-Public Enemy; Aboshan's Desire; Absorbing Man |
| can't restrictions | 695 | 1,226 | A-Goma Fada Vanguard; A-Ready to Rumble; A-Sewer Crocodile |
| X costs | 689 | 1,197 | A-Briar Hydra; A-Maelstrom Muse; A-Nael, Avizoa Aeronaut |
| equipment | 411 | 557 | A-Bruenor Battlehammer; A-Dwarfhold Champion; A-Goma Fada Vanguard |
| copy effects | 346 | 668 | A-Mentor's Guidance; A-Ocelot Pride; A-Symmetry Sage |
| library search | 247 | 467 | A-Navigation Orb; A-Phantom Carriage; A-Sprouting Goblin |
| cost reduction | 188 | 368 | A-Cosmos Charger; A-Knockout Blow; A-Llanowar Greenwidow |
| +1/+1 static (anthems) | 135 | 242 | A-Steadfast Unicorn; Akoum Battlesinger; Alistair, the Brigadier |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| venture into the dungeon. | 12 | 23 | A-Fates' Reversal; Clattering Skeletons; Delver's Torch |
| cast ~ only during the declare attackers step and only if you've been attacked this step. | 10 | 14 | Assassin's Blade; Champion's Victory; Defiant Stand |
| banding | 10 | 13 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| draft a card from ~'s spellbook. | 8 | 14 | Boseiju Pathlighter; Cursebound Witch; Emmara, Voice of the Conclave |
| double team | 7 | 18 | Amber-Plate Ainok; Giant Fire Beetles; Lizardfolk Librarians |
| open an attraction. | 7 | 17 | Coming Attraction; Deadbeat Attendant; Petting Zookeeper |
| return the exiled card to the battlefield under its owner's control. | 7 | 13 | Faceless Devourer; Fiend Hunter; Journey to Nowhere |
| conspire | 7 | 11 | Barkshell Blessing; Burn Trail; Ghastly Discovery |
| exile ~ with three time counters on it. | 7 | 10 | Arc Blade; Charnel Serenade; Cyclical Evolution |
| phasing | 6 | 12 | Breezekeeper; Merfolk Raiders; Sandbar Crocodile |
| ~ costs {1} less to cast for each creature in your party. | 6 | 10 | Deadly Alliance; Journey to Oblivion; Sea Gate Colossus |
| as an additional cost to cast ~, exile a creature card from your graveyard. | 6 | 9 | Cobbled Lancer; Headless Skaab; Makeshift Mauler |
| return that card to the battlefield under your control. | 6 | 7 | False Demise; Fool's Demise; Minion's Return |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| you take the initiative. | 5 | 20 | Aarakocra Sneak; Avenging Hunter; Explore the Underdark |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
