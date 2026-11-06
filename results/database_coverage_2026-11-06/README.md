# Entire local card database coverage

Measured 2026-11-06 against the current working tree.

| Status | Cards | Share |
| --- | ---: | ---: |
| Fully template-matched | 17,612 | 49.92% |
| Matched with recorded simplifications | 393 | 1.11% |
| Partly supported | 17,272 | 48.96% |
| Could not parse | 0 | 0.00% |
| Total | 35,277 | 100% |

Counts include every distinct database entry, including basic lands and cards outside Standard. Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification match the deck coverage reports.

Fully template-matched means no rules text is reported as ignored or simplified. This measures template coverage; complete Magic rules correctness is not verified.

## Missing effects ranked by potential full matches

A potential full match has every ignored line in the listed gap and no recorded simplifications. These are upper bounds: an entire family may need many implementations. Families overlap, so counts must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not merge differently worded effects.

Unclassified wording affects 8,167 cards; 5,458 have all their remaining gaps unclassified. This bucket is separate from the effect-family ranking.

### Effect families

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| counters | 1,672 | 2,382 | Aang, Airbending Master; Aboroth; Abzan Charm |
| activated abilities | 1,484 | 1,895 | A Container of Booster Packs; A-Town; Abuna Acolyte |
| triggered (whenever/when) | 1,418 | 2,249 | A Girl and Her Dogs; A Good Day to Die; A Good Day to Pie |
| graveyard | 1,243 | 2,120 | "Rumors of My Death . . ."; A Good Day to Pie; Aatchik, Emerald Radian |
| tokens | 1,056 | 1,770 | A Girl and Her Dogs; Aatchik, Emerald Radian; Abhorrent Overlord |
| exile | 960 | 1,761 | "Rumors of My Death . . ."; A Container of Booster Packs; Abdel Adrian, Gorion's Ward |
| sacrifice | 918 | 1,497 | Abjure; Abzan Advantage; Ace, Fearless Rebel |
| X costs | 656 | 1,073 | Abaddon the Despoiler; Accessories to Murder; Aether Burst |
| auras/enchant | 652 | 757 | Absorbing Man; Academy Researchers; Aerial Modification |
| can't restrictions | 585 | 971 | Abyssal Persecutor; Academic Probation; Agatha of the Vile Cauldron |
| equipment | 355 | 460 | Ace's Baseball Bat; Aegis of the Legion; Aettir and Priwen |
| copy effects | 352 | 637 | Aboleth Spawn; Absorb Identity; Absorbing Man |
| cost reduction | 212 | 367 | Absorb Energy; Acolyte of Bahamut; Alisaie Leveilleur |
| library search | 206 | 390 | 70,000 Light-Years from Home; Angel's Herald; Angrath's Fury |
| +1/+1 static (anthems) | 125 | 195 | Aardwolf's Advantage; Akoum Battlesinger; Alistair, the Brigadier |
| mana restrictions | 90 | 145 | Abstract Paintmage; Adarkar Unicorn; Altar of the Lost |
| transform | 61 | 107 | Aang, at the Crossroads // Aang, Destined Savior; Afflicted Deserter // Werewolf Ransacker; Archangel Avacyn // Avacyn, the Purifier |
| set: food | 56 | 93 | All-You-Can-Eat Buffet; Ant-Man's Army; Astrid Peth |
| set: threshold | 34 | 40 | Battlefield Scrounger; Bloodcurdler; Boneshard Slasher |
| modal (choose) | 26 | 253 | Beamsplitter Mage; Cabal Interrogator; Cauldron of Souls |
| set: exhaust | 16 | 24 | Afterburner Expert; Audacious Knuckleblade; Boom Scholar |
| set: role | 12 | 16 | Asinine Antics; Dunbarrow Revivalist; Ellivere of the Wild Court |
| set: gift | 12 | 15 | Bilbo's Gambit; Coiling Rebirth; Cruelclaw's Heist |
| set: collect evidence | 9 | 18 | Axebane Ferox; Conspiracy Unraveler; Cryptex |
| set: room | 8 | 16 | Devoted Mardu; Dungeon Delver; Ghostly Dancers |
| set: craft | 8 | 15 | Altar of the Wretched // Wretched Bonemass; Market Gnome; Ore-Rich Stalactite // Cosmium Catalyst |
| set: behold | 7 | 10 | Champion of the Clachan; Champion of the Path; Champions of the Perfect |
| set: cloak | 6 | 11 | Cryptic Coat; Hide in Plain Sight; Roalesk, Prime Specimen |
| set: discover | 6 | 9 | Aloy, Savior of Meridian; Curator of Sun's Creation; Ellie and Alan, Paleontologists |
| set: warp | 5 | 9 | Blade of the Swarm; Cantor of the Refrain; Full Bore |
| set: manifest dread | 4 | 9 | Disturbing Mirth; Glitch Interpreter; Ticket Booth // Tunnel of Hate |
| set: earthbend | 4 | 8 | Avatar Kyoshi, Earthbender; Bumi's Feast Lecture; The Boulder, Ready to Rumble |
| set: forage | 4 | 5 | Camellia, the Seedmiser; Corpseberry Cultivator; Feed the Cycle |
| set: crime | 4 | 4 | Nimble Brigand; Overzealous Muscle; Patrolling Peacemaker |
| set: renew | 4 | 4 | Naga Fleshcrafter; Pampered Loamfrill; Rot-Curse Rakshasa |
| set: waterbend | 3 | 7 | Benevolent River Spirit; Katara, Water Tribe's Hope; Water Whip |
| set: airbend | 3 | 6 | Appa, Loyal Sky Bison; Appa, Steadfast Guardian; Monk Gyatso |
| set: suspect | 3 | 6 | Frantic Scapegoat; Investigator's Journal; Presumed Dead |
| set: map | 3 | 5 | Brackish Blunder; Worldwalker Helm; Wowzer, the Aspirational |
| set: mobilize | 3 | 4 | Avenger of the Fallen; Devoted Mardu; Infantry Shield |

### Exact ignored wording

| Gap | Potential full matches | Cards affected | Examples |
| --- | ---: | ---: | --- |
| banding | 10 | 14 | Benalish Hero; Benalish Infantry; Icatian Phalanx |
| open an attraction. | 9 | 18 | Coming Attraction; Deadbeat Attendant; Discourtesy Clerk |
| draft a card from ~'s spellbook. | 8 | 13 | Bladehold Cleaver; Boseiju Pathlighter; Cursebound Witch |
| ~ becomes prepared. | 8 | 12 | Abigale, Poet Laureate // Heroic Stanza; Bloodline Recollector // Ancestral Craving; Eiganjo Dynastorian // Replenish |
| 7+ \| flying | 6 | 8 | Class-4 Tactical Cube; Larval Scoutlander; Pinnacle Kill-Ship |
| you get {tk}, then you may put a sticker on a nonland permanent you own. | 6 | 6 | Aerialephant; Carnival Carnivore; Chicken Troupe |
| double team | 5 | 16 | Amber-Plate Ainok; Lizardfolk Librarians; Moradin's Disciples |
| you may cast ~ as though it had flash. if you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step. | 5 | 10 | Lightning Reflexes; Mystic Veil; Parapet |
| when a creature with mana value 6 or greater enters, you may return this card from your graveyard to the battlefield attached to that creature. | 5 | 5 | Dragon Breath; Dragon Fangs; Dragon Scales |
| copy it for each time you've cast your commander from the command zone this game. | 4 | 6 | Echo Storm; Empyrial Storm; Fury Storm |
| if you control a commander, you may cast ~ without paying its mana cost. | 4 | 5 | Deadly Rollick; Fierce Guardianship; Flawless Maneuver |
| if you don't put the card into your hand, you may put it into your graveyard. | 4 | 5 | Archghoul of Thraben; Sarinth Steelseeker; Territory Culler |
| spell commander | 4 | 5 | Clear, the Mind; Lava, Axe; Rampant, Growth |
| it assembles a contraption. | 4 | 4 | Joyride Rigger; Overt Operative; Steady-Handed Mook |
| ~ can be your commander. | 3 | 42 | Commodore Guff; Freyalise, Llanowar's Fury; Quintorius, History Chaser |
| 8+ \| flying | 3 | 11 | Debris Field Crusher; U.S.S. Excelsior, Cutting Edge; Uthros Scanship |
| as an additional cost to cast ~, discard x cards. | 3 | 10 | Nostalgic Dreams; Restless Dreams; Sickening Dreams |
| 6+ \| flying | 3 | 6 | Oberth-Class Starship; U.S.S. Cerritos, Following Up; U.S.S. Discovery, at Black Alert |
| spells your opponents cast that target ~ cost {2} more to cast. | 3 | 6 | Boreal Elemental; Charix, the Raging Isle; Sphinx of New Prahv |
| enchanted creature has protection from the chosen color. this effect doesn't remove ~. | 3 | 5 | Cho-Manno's Blessing; Flickering Ward; Pentarch Ward |
| paradigm | 3 | 5 | Decorum Dissertation; Germination Practicum; Restoration Seminar |
| time travel. | 3 | 5 | All of History, All at Once; Time Beetle; Wibbly-wobbly, Timey-wimey |
| undaunted | 3 | 5 | Coastal Breach; Curtains' Call; Sublime Exhalation |
| ~ costs {x} less to cast, where x is the greatest power among creatures you control. | 3 | 5 | Ghalta the Unstoppable; Molten Monstrosity; The Great Henge |
| excess damage is dealt to that creature's controller instead. | 3 | 4 | Flame Spill; Gandalf's Sanction; Pigment Storm |
| freerunning {1}{b} | 3 | 4 | Chain Assassination; Merciless Harlequin; Restart Sequence |
| if a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead of putting it into your graveyard. | 3 | 4 | Loxodon Smiter; Obstinate Baloth; Wilt-Leaf Liege |
| mana restriction ignored: spend this mana only to cast an artifact spell or activate an ability of an artifact source. | 3 | 4 | Cargo Ship; Isolinear Processor; Oaken Siren |
| unsupported token keywords: changeling | 3 | 4 | Belonging; Irregular Cohort; Personify |
| unsupported token keywords: firebending 1 | 3 | 4 | Cruel Administrator; Fire Nation Attacks; Fire Nation Occupation |
| vehicles you control become artifact creatures until end of turn. | 3 | 4 | Push the Limit; Start Your Engines; The Thanos-Copter |
| you get {tk}{tk}, then you may put a sticker on a nonland permanent you own. | 3 | 4 | Bioluminary; Finishing Move; Stiltstrider |
| you may return another permanent you control to its owner's hand. | 3 | 4 | Ambrosia Whiteheart; Aviary Mechanic; Rescuer Chwinga |
| buyback—sacrifice a land. | 3 | 3 | Constant Mists; Pegasus Stampede; Reaping the Rewards |
| champion a creature | 3 | 3 | Changeling Berserker; Changeling Hero; Changeling Titan |
| change the text of target spell or permanent by replacing all instances of one color word with another. | 3 | 3 | Alter Reality; Glamerdye; Sleight of Mind |
| create a 1/1 colorless phyrexian mite artifact creature token with toxic 1 and "~ can't block." | 3 | 3 | Crawling Chorus; Infested Fleshcutter; Stinging Hivemaster |
| create a tapped planet land token named new planet with "{t}: add one mana of any color." | 3 | 3 | David and Carol Marcus, Creators; Genesis Effect; Stable Wormhole |
| gravestorm | 3 | 3 | Bitter Ordeal; Follow the Bodies; Ominous Harvest |
| if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on ~. | 3 | 3 | Insatiable Skittermaw; Interceptor Mechan; Kavaron Skywarden |

[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)
