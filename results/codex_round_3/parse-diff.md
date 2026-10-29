Base: b8d12a61482b
Card parsing: 13 of 34129 cards parse differently from the base branch.

Changed cards:

- archive trap
- bramble familiar // fetch quest
- dread summons
- fascination
- fractured sanity
- increasing confusion
- jace beleren
- liliana's indignation
- psychic drain
- startled awake // persistent nightmare
- summons of saruman
- the cyber-controller
- vivien on the hunt

archive trap:
  +spell_effects=[Effect(kind='mill'
  +amount=13
  +target='player'
  +filter='opp')]
  -you may pay {0} rather than pay ~'s mana cost."
  -'Target opponent mills thirteen cards.']
  +you may pay {0} rather than pay ~'s mana cost."]

bramble familiar // fetch quest:
  -unsupported=['Mill seven cards
  -then put a creature
  -enchantment
  -or land card from among cards milled this way onto the battlefield.']
  +spell_effects=[Effect(kind='mill'
  +amount=7)
  +Effect(kind='mill_pick'
  +amount=1
  +data={'types': ['creature'
  +'enchantment'
  +'land']
  +'adventure': False
  +'all': False
  +'dest': 'battlefield'
  +'tapped': False})]

dread summons:
  -unsupported=['Each player mills X cards.'
  -'For each creature card put into a graveyard this way
  +spell_effects=[Effect(kind='mill'
  +target='each_player'
  +data={'x': True})]
  +unsupported=['For each creature card put into a graveyard this way

fascination:
  -unsupported=['• Each player draws X cards.'
  -'• Each player mills X cards.']
  +unsupported=['• Each player draws X cards.']
  +modes=[[Effect(kind='mill'
  +target='each_player'
  +data={'x': True})]]

fractured sanity:
  -unsupported=['Each opponent mills fourteen cards.']
  +spell_effects=[Effect(kind='mill'
  +amount=14
  +target='each_opponent')]
