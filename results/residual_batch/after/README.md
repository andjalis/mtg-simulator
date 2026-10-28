# Entire local card database coverage

Measured 2026-10-28 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 12,054 | 35.32% |
| Matched with recorded simplifications | 231 | 0.68% |
| Partly supported | 21,844 | 64.00% |
| Could not parse | 0 | 0.00% |
| Total | 34,129 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 10,602 cards; 6,935 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| triggered (whenever/when) | 2,072 | 3,364 | A Display of My Dark Power; A Good Day to Die; A Good Day to Pie |
| counters | 1,934 | 2,848 | A-Briar Hydra; A-Celebrity Fencer; A-Celestial Regulator |
| activated abilities | 1,931 | 2,566 | A-Baba Lysaga, Night Witch; A-Carnelian Orb of Dragonkind; A-Dungeon Descent |
| graveyard | 1,500 | 2,680 | A Good Day to Pie; A-Ardent Dustspeaker; A-Cobbled Lancer |
| tokens | 1,217 | 2,170 | A-Elderleaf Mentor; A-Elven Bow; A-Esika's Chariot |
| sacrifice | 1,143 | 1,921 | A-Baba Lysaga, Night Witch; A-Capenna Express; A-Forge Boss |
| exile | 1,041 | 2,070 | A-Ardent Dustspeaker; A-Cobbled Lancer; A-Elderfang Ritualist |
| auras/enchant | 865 | 1,042 | A-Public Enemy; Aboshan's Desire; Absorbing Man |
| can't restrictions | 716 | 1,283 | A-Goma Fada Vanguard; A-Ready to Rumble; A-Sewer Crocodile |
| X costs | 685 | 1,203 | A-Briar Hydra; A-Maelstrom Muse; A-Nael, Avizoa Aeronaut |
| equipment | 412 | 560 | A-Bruenor Battlehammer; A-Dwarfhold Champion; A-Goma Fada Vanguard |
| copy effects | 342 | 669 | A-Mentor's Guidance; A-Symmetry Sage; A-Thousand-Faced Shadow |
| library search | 244 | 469 | A-Navigation Orb; A-Phantom Carriage; A-Sprouting Goblin |
| cost reduction | 188 | 368 | A-Cosmos Charger; A-Knockout Blow; A-Llanowar Greenwidow |
| +1/+1 static (anthems) | 133 | 243 | A-Steadfast Unicorn; Akoum Battlesinger; Alistair, the Brigadier |
| mana restrictions | 73 | 137 | A-Base Camp; Abstract Paintmage; Adarkar Unicorn |
| set: threshold | 64 | 77 | Aboshan's Desire; Barbarian Ring; Battlefield Scrounger |
| transform | 59 | 123 | Afflicted Deserter // Werewolf Ransacker; Ambitious Farmhand // Seasoned Cathar; Archangel Avacyn // Avacyn, the Purifier |
| set: food | 59 | 96 | Ant-Man's Army; Astrid Peth; Bartered Cow |
| modal (choose) | 23 | 257 | Beamsplitter Mage; Cabal Interrogator; Cauldron of Souls |
| set: exhaust | 19 | 29 | Afterburner Expert; Audacious Knuckleblade; Boom Scholar |
| set: gift | 12 | 18 | Coiling Rebirth; Dark Apostle; Dawn's Truce |
| set: suspect | 10 | 21 | Caught Red-Handed; Convenient Target; Frantic Scapegoat |
| set: descend | 9 | 12 | Akawalli, the Seething Tower; Bygone Marvels; Coati Scavenger |
| set: discover | 8 | 13 | A-Geological Appraiser; Aloy, Savior of Meridian; Curator of Sun's Creation |
| set: role | 8 | 11 | Dunbarrow Revivalist; Embereth Veteran; Gadwick's First Duel |
| set: manifest dread | 7 | 15 | Disturbing Mirth; Paranormal Analyst; Stay Hidden, Stay Silent |
| set: room | 7 | 14 | Dungeon Delver; Ghostly Dancers; Ghostly Keybearer |
| set: crime | 7 | 10 | Nimble Brigand; Omenport Vigilante; Overzealous Muscle |
| set: collect evidence | 6 | 18 | Axebane Ferox; Conspiracy Unraveler; Evidence Examiner |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| venture into the dungeon. | 12 | 23 | A-Fates' Reversal; Clattering Skeletons; Delver's Torch |
| banding | 10 | 13 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| create a tapped powerstone token. | 9 | 16 | Argothian Opportunist; Excavation Explosion; Geology Enthusiast |
| cast ~ only during the declare attackers step and only if you've been attacked this step. | 9 | 14 | Assassin's Blade; Champion's Victory; Defiant Stand |
| enlist | 8 | 15 | Argivian Cavalier; Barkweave Crusher; Benalish Faithbonder |
| draft a card from ~'s spellbook. | 8 | 14 | Boseiju Pathlighter; Cursebound Witch; Emmara, Voice of the Conclave |
| if a creature dealt damage this way would die this turn, exile it instead. | 8 | 14 | Anger of the Gods; Annihilating Fire; Crush the Weak |
| you may have ~ assign its combat damage as though it weren't blocked. | 8 | 9 | Deathcoil Wurm; Imaryll, Elfhame Elite; Lone Wolf |
| double team | 7 | 18 | Amber-Plate Ainok; Giant Fire Beetles; Lizardfolk Librarians |
| open an attraction. | 7 | 17 | Coming Attraction; Deadbeat Attendant; Petting Zookeeper |
| conspire | 7 | 11 | Barkshell Blessing; Burn Trail; Ghastly Discovery |
| exile ~ with three time counters on it. | 7 | 10 | Arc Blade; Charnel Serenade; Cyclical Evolution |
| phasing | 6 | 12 | Breezekeeper; Merfolk Raiders; Sandbar Crocodile |
| if kicked: it enters with two +1/+1 counters on it. | 6 | 11 | Academy Drake; Aether Figment; Ghastly Gloomhunter |
| ~ costs {1} less to cast for each creature in your party. | 6 | 10 | Deadly Alliance; Journey to Oblivion; Sea Gate Colossus |
| as an additional cost to cast ~, exile a creature card from your graveyard. | 6 | 9 | Cobbled Lancer; Headless Skaab; Makeshift Mauler |
| those creatures don't untap during their controller's next untap step. | 6 | 9 | Adverse Conditions; Decision Paralysis; Frost Breath |
| you gain life equal to the life lost this way. | 6 | 8 | Agent of Masks; Blood Tithe; Exsanguinate |
| if damage would be dealt to ~, prevent that damage. remove a +1/+1 counter from ~. | 6 | 7 | Phantom Centaur; Phantom Flock; Phantom Nantuko |
| return that card to the battlefield under your control. | 6 | 7 | False Demise; Fool's Demise; Minion's Return |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| ~ can't attack or block alone. | 6 | 6 | Bonded Horncrest; Ember Beast; Jackal Familiar |
| you become the monarch. | 5 | 41 | Crimson Fleet Commodore; Feast of Succession; Palace Sentinels |
| you take the initiative. | 5 | 20 | Aarakocra Sneak; Avenging Hunter; Explore the Underdark |
| untap those creatures. | 5 | 14 | Gleam of Resistance; Jeskai Ascendancy; Tenacity |
| return the exiled card to the battlefield under its owner's control. | 5 | 13 | Faceless Devourer; Journey to Nowhere; Oblivion Ring |
| each creature you control with a +1/+1 counter on it has trample. | 5 | 10 | Crowned Ceratok; Drix Fatemaker; Duskshell Crawler |
| look at target opponent's hand. | 5 | 9 | Sorcerous Sight; Talas Explorer; Telepathic Spies |
| the flashback cost is equal to its mana cost. | 5 | 9 | Flashback; Katilda and Lier; Slickshot Lockpicker |
| draw that many cards. | 5 | 8 | Body of Knowledge; Fear of Failed Tests; Glint-Eye Nephilim |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
