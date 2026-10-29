Base: 688e8541087b
Card parsing: 29 of 34129 cards parse differently from the base branch.

Changed cards:

- archival whorl
- arzakon
- blessed respite
- clear the mind
- commit // memory
- cranial archive
- day's undoing
- diminishing returns
- echo of eons
- emergency powers
- enhanced surveillance
- feldon's cane
- game plan
- immortus, master of eternity
- jace, the living guildpact
- learn from the past
- mine, mine, mine!
- mnemonic nexus
- paradigm shift
- primal command
- reminisce
- struggle // survive
- temporal cascade
- the mending of dominaria
- thran foundry
- time reversal
- time spiral
- timetwister
- weftwalking

archival whorl:
  +spell_effects=[Effect(kind='cx_recycle'
  +amount=7
  +data={'scope': 'you'
  +'hand': True
  +'draw': True})]
  -'Shuffle your hand and graveyard into your library
  -then draw seven cards.'

arzakon:
  -'[−7]: Each player shuffles their hand and graveyard into their library
  -then draws seven cards.'
  +loyalty_abilities=[(-7
  +[Effect(kind='cx_recycle'
  +amount=7
  +data={'scope': 'each'
  +'hand': True
  +'draw': True})])]

blessed respite:
  -spell_effects=[Effect(kind='fog')]
  -unsupported=['Target player shuffles their graveyard into their library.']
  +spell_effects=[Effect(kind='cx_recycle'
  +target='player'
  +data={'scope': 'target'
  +'hand': False
  +'draw': False})
  +Effect(kind='fog')]

clear the mind:
  -spell_effects=[Effect(kind='draw'
  +spell_effects=[Effect(kind='cx_recycle'
  +target='player'
  +data={'scope': 'target'
  +'hand': False
  +'draw': False})
  +Effect(kind='draw'
  -unsupported=['Target player shuffles their graveyard into their library.']

commit // memory:
  -unsupported=["Put target spell or nonland permanent into its owner's library second from the top."
  -'Memory: Each player shuffles their hand and graveyard into their library
  -then draws seven cards.']
  +unsupported=["Put target spell or nonland permanent into its owner's library second from the top."]
  -unsupported=['Each player shuffles their hand and graveyard into their library
  -then draws seven cards.']
  +spell_effects=[Effect(kind='cx_recycle'
  +amount=7
  +data={'scope': 'each'
  +'hand': True
  +'draw': True})]
