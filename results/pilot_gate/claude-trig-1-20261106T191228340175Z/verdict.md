# Pilot gate: FAIL

Base `4a4b9c885a3e` → `6f537ac80001`; fast tests; 566.7s.

- lint failed
- tests failed
- 1 full-match regressions
- Suspicious sampled parses: Sigil of Myrkul

| Check | Exit | Seconds |
| --- | ---: | ---: |
| [lint](lint.log) | 1 | 1.8 |
| [tests](tests.log) | 1 | 404.4 |
| [coverage_base](coverage_base.log) | 0 | 25.5 |
| [coverage_head](coverage_head.log) | 0 | 24.9 |
| [parse_base](parse_base.log) | 0 | 26.0 |
| [parse_head](parse_head.log) | 0 | 26.5 |
| [parse_diff](parse_diff.log) | 0 | 0.2 |
| [sample](sample.log) | 0 | 0.4 |
| [decks](decks.log) | 0 | 0.1 |
| [exercise](exercise.log) | 0 | 0.5 |

Coverage deltas (same offline inputs; Standard = saved nonbasic set snapshot):
- all: full +7, partial -7, simplified +0, total +0
- standard: full +5, partial -5, simplified +0, total +0
- regressions (1): Ancient Bronze Dragon
- newly_full (8): Eastfarthing Farmer, Faebloom Trick, Lithobraking, Primal Witchstalker, Rubble Rouser, Sigil of Myrkul, The Royal Scions, Yathan Roadwatcher
- newly_raising (0): none
- Exercise: 8/8 newly-full cards resolved every effect once without raising.
- Smoke: 50/50; seed 1729+i; 20s/game; repository fallback (no newly-full cards in decks).

False-full sample (up to 10, seed 1729; Oracle beside parsed fields):

**Eastfarthing Farmer** — parse.etb_effects[0].target='none'; parse.etb_effects[1].target='none'; parse.etb_effects[2].target='none'

| Oracle | Parsed |
| --- | --- |
| When this creature enters, create a Food token. When you do, target creature you control gets +1/+1 until end of turn for each Food you control. (A Food token is an artifact with "{2}, {T}, Sacrifice this token: You gain 3 life.") | CardDef(name='Eastfarthing Farmer', mana_cost={'generic': 2, 'W': 1}, cmc=3, types={'Creature'}, subtypes={'Halfling', 'Peasant'}, power=2, toughness=3, etb_effects=[Effect(kind='link_start', data={'kinds': ('token'), 'forced': True}), Effect(kind='token', amount=1, cond='lib:["link_taken"]', data={'kind': 'food'}), Effect(kind='link_check'), Effect(kind='pump', amount=1, amount2=1, target='creature', cond='paid', data={'xq': ('count', 'Food')})], oracle='When this creature enters, create a Food token. When you do, target creature you control gets +1/+1 until end of turn for each Food you control. (A Food token is an artifact with "{2}, {T}, Sacrifice this token: You gain 3 life.")', triggers=[Trigger(event='etb', effects=[Effect(kind='link_start', data={'kinds': ('token'), 'forced': True}), Effect(kind='token', amount=1, cond='lib:["link_taken"]', data={'kind': 'food'}), Effect(kind='link_check'), Effect(kind='pump', amount=1, amount2=1, target='creature', cond='paid', data={'xq': ('count', 'Food')})])], color_override={'W'}) |

**Primal Witchstalker** — parse.etb_effects[0].target='none'; parse.etb_effects[1].target='none'; parse.etb_effects[2].target='none'; parse.etb_effects[3].target='none'

| Oracle | Parsed |
| --- | --- |
| Menace (This creature can't be blocked except by two or more creatures.)<br>When this creature enters, mill four cards. When you do, return target land card from your graveyard to the battlefield tapped. (To mill four cards, put the top four cards of your library into your graveyard.) | CardDef(name='Primal Witchstalker', mana_cost={'generic': 1, 'B': 1, 'G': 1}, cmc=3, types={'Creature'}, subtypes={'Wolf'}, power=2, toughness=1, keywords={'menace'}, etb_effects=[Effect(kind='link_start', data={'kinds': ('mill'), 'forced': True}), Effect(kind='mill', amount=4, cond='lib:["link_taken"]'), Effect(kind='link_check'), Effect(kind='gy_move', amount=1, cond='paid', data={'what': 'land', 'dest': 'bf', 'tapped': True, 'zone': 'mine', 'x_n': False, 'cmc': None})], oracle="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, mill four cards. When you do, return target land card from your graveyard to the battlefield tapped. (To mill four cards, put the top four cards of your library into your graveyard.)", triggers=[Trigger(event='etb', effects=[Effect(kind='link_start', data={'kinds': ('mill'), 'forced': True}), Effect(kind='mill', amount=4, cond='lib:["link_taken"]'), Effect(kind='link_check'), Effect(kind='gy_move', amount=1, cond='paid', data={'what': 'land', 'dest': 'bf', 'tapped': True, 'zone': 'mine', 'x_n': False, 'cmc': None})])], color_override={'B', 'G'}) |

**Rubble Rouser** — parse.etb_effects[0].target='none'; parse.activated[0].effects[0].target='none'; parse.activated[0].effects[1].target='none'; parse.activated[0].effects[2].target='none'

| Oracle | Parsed |
| --- | --- |
| When this creature enters, you may discard a card. If you do, draw a card.<br>{T}, Exile a card from your graveyard: Add {R}. When you do, this creature deals 1 damage to each opponent. | CardDef(name='Rubble Rouser', mana_cost={'generic': 2, 'R': 1}, cmc=3, types={'Creature'}, subtypes={'Dwarf', 'Sorcerer'}, power=1, toughness=4, etb_effects=[Effect(kind='opt_cost_draw', amount=1, data={'cost': 'discard'})], oracle='When this creature enters, you may discard a card. If you do, draw a card.\n{T}, Exile a card from your graveyard: Add {R}. When you do, this creature deals 1 damage to each opponent.', triggers=[Trigger(event='etb', effects=[Effect(kind='opt_cost_draw', amount=1, data={'cost': 'discard'})])], activated=[Activated(kind='ability', cost={'generic': 0}, effects=[Effect(kind='link_start', data={'kinds': ('add_mana'), 'forced': True}), Effect(kind='add_mana', cond='lib:["link_taken"]', data={'colors': ['R']}), Effect(kind='link_check'), Effect(kind='damage', amount=1, target='player', cond='paid')], extra_costs={'tap': True, 'cx_costs': (('exile_gy', 1, {}))}, text='{T}, Exile a card from your graveyard: Add {R}. When you do, ~ deals 1 damage to each opponent.')], color_override={'R'}) |

**The Royal Scions** — parse.loyalty_abilities[0][1][0].target='none'; parse.loyalty_abilities[0][1][1].target='none'; parse.loyalty_abilities[2][1][0].target='none'; parse.loyalty_abilities[2][1][1].target='none'; parse.loyalty_abilities[2][1][2].target='none'

| Oracle | Parsed |
| --- | --- |
| +1: Draw a card, then discard a card.<br>+1: Target creature gets +2/+0 and gains first strike and trample until end of turn.<br>−8: Draw four cards. When you do, The Royal Scions deals damage to any target equal to the number of cards in your hand. | CardDef(name='The Royal Scions', mana_cost={'generic': 1, 'U': 1, 'R': 1}, cmc=3, types={'Planeswalker'}, subtypes={'Rowan', 'Will'}, oracle='+1: Draw a card, then discard a card.\n+1: Target creature gets +2/+0 and gains first strike and trample until end of turn.\n−8: Draw four cards. When you do, The Royal Scions deals damage to any target equal to the number of cards in your hand.', loyalty=5, loyalty_abilities=[(1, [Effect(kind='draw', amount=1), Effect(kind='discard', amount=1)]), (1, [Effect(kind='pump', amount=2, target='permanent', data={'selector': {'types_all': ['creature']}}), Effect(kind='grant', target='prev', data={'keyword': 'first strike'}), Effect(kind='grant', target='prev', data={'keyword': 'trample'})]), (-8, [Effect(kind='link_start', data={'kinds': ('draw'), 'forced': True}), Effect(kind='draw', amount=4, cond='lib:["link_taken"]'), Effect(kind='link_check'), Effect(kind='damage', amount=1, target='any', cond='paid', data={'xq': ('hand')})])], color_override={'R', 'U'}, legendary=True) |

**Faebloom Trick** — parse.spell_effects[0].target='none'; parse.spell_effects[1].target='none'; parse.spell_effects[2].target='none'

| Oracle | Parsed |
| --- | --- |
| Create two 1/1 blue Faerie creature tokens with flying. When you do, tap target creature an opponent controls. | CardDef(name='Faebloom Trick', mana_cost={'generic': 2, 'U': 1}, cmc=3, types={'Instant'}, spell_effects=[Effect(kind='link_start', data={'kinds': ('token'), 'forced': True}), Effect(kind='token', amount=2, cond='lib:["link_taken"]', data={'name': 'Faerie', 'power': 1, 'toughness': 1, 'keywords': {'flying'}, 'attacking': False, 'triggers': [], 'artifact': False, 'pt_per': '', 'colors': {'U'}}), Effect(kind='link_check'), Effect(kind='tap', amount=1, target='creature', cond='paid')], oracle='Create two 1/1 blue Faerie creature tokens with flying. When you do, tap target creature an opponent controls.', color_override={'U'}) |

**Lithobraking** — parse.spell_effects[0].target='none'; parse.spell_effects[1].target='none'; parse.spell_effects[2].target='none'; parse.spell_effects[3].target='none'

| Oracle | Parsed |
| --- | --- |
| Create a Lander token. Then you may sacrifice an artifact. When you do, Lithobraking deals 2 damage to each creature. (A Lander token is an artifact with "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.") | CardDef(name='Lithobraking', mana_cost={'generic': 2, 'R': 1}, cmc=3, types={'Instant'}, spell_effects=[Effect(kind='token', amount=1, data={'kind': 'lander'}), Effect(kind='link_start', data={'kinds': ('sac_filtered'), 'forced': False}), Effect(kind='sac_filtered', cond='lib:["link_taken"]', data={'spec': {'types': ['artifact']}}), Effect(kind='link_check'), Effect(kind='damage', amount=2, target='each_creature', cond='paid')], oracle='Create a Lander token. Then you may sacrifice an artifact. When you do, Lithobraking deals 2 damage to each creature. (A Lander token is an artifact with "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.")', color_override={'R'}) |

**Yathan Roadwatcher** — parse.etb_effects[0].target='none'; parse.etb_effects[1].target='none'; parse.etb_effects[2].target='none'; parse.etb_effects[3].target='none'

| Oracle | Parsed |
| --- | --- |
| When this creature enters, if you cast it, mill four cards. When you do, return target creature card with mana value 3 or less from your graveyard to the battlefield. | CardDef(name='Yathan Roadwatcher', mana_cost={'generic': 1, 'W': 1, 'B': 1, 'G': 1}, cmc=4, types={'Creature'}, subtypes={'Human', 'Scout'}, power=3, toughness=3, etb_effects=[Effect(kind='link_start', cond='cast', data={'kinds': ('mill'), 'forced': True}), Effect(kind='mill', amount=4, cond='cast'), Effect(kind='link_check', cond='cast'), Effect(kind='gy_move', amount=1, cond='cast', data={'what': 'creature', 'dest': 'bf', 'tapped': False, 'zone': 'mine', 'x_n': False, 'cmc': (3, 'less')})], oracle='When this creature enters, if you cast it, mill four cards. When you do, return target creature card with mana value 3 or less from your graveyard to the battlefield.', triggers=[Trigger(event='etb', effects=[Effect(kind='link_start', cond='cast', data={'kinds': ('mill'), 'forced': True}), Effect(kind='mill', amount=4, cond='cast'), Effect(kind='link_check', cond='cast'), Effect(kind='gy_move', amount=1, cond='cast', data={'what': 'creature', 'dest': 'bf', 'tapped': False, 'zone': 'mine', 'x_n': False, 'cmc': (3, 'less')})], intervening_if='cast')], color_override={'B', 'G', 'W'}) |

**Sigil of Myrkul** — parse.triggers[0].effects[0].target='none'; parse.triggers[0].effects[1].target='none'; parse.triggers[0].effects[2].target='none'; parse.triggers[0].effects[3].cond: unknown placeholder 'lib:["gy","you",{"types":["creature","card"]},">=",4]'

| Oracle | Parsed |
| --- | --- |
| At the beginning of combat on your turn, mill a card. When you do, if there are four or more creature cards in your graveyard, put a +1/+1 counter on target creature you control and it gains deathtouch until end of turn. (To mill a card, put the top card of your library into your graveyard.) | CardDef(name='Sigil of Myrkul', mana_cost={'generic': 2, 'B': 1}, cmc=3, types={'Enchantment'}, oracle='At the beginning of combat on your turn, mill a card. When you do, if there are four or more creature cards in your graveyard, put a +1/+1 counter on target creature you control and it gains deathtouch until end of turn. (To mill a card, put the top card of your library into your graveyard.)', triggers=[Trigger(event='begin_combat', effects=[Effect(kind='link_start', data={'kinds': ('mill'), 'forced': True}), Effect(kind='mill', amount=1, cond='lib:["link_taken"]'), Effect(kind='link_check'), Effect(kind='p1_counters', amount=1, target='creature_mine', cond='lib:["gy","you",{"types":["creature","card"]},">=",4]'), Effect(kind='grant', target='prev', cond='paid', data={'keyword': 'deathtouch'})])], color_override={'B'}) |


Template matching and smoke games do not establish rules correctness. Full evidence: verdict.json and linked logs.
