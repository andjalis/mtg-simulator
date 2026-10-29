Base: b8d12a61482b
Card parsing: 20 of 34129 cards parse differently from the base branch.

Changed cards:

- aethergeode miner
- against all odds
- blur
- distinguished conjurer
- emiel the blessed
- felidar guardian
- flicker
- flicker of fate
- flickering hound
- flickering spirit
- hallowed respite
- kimoyo beads
- oji, the exquisite blade
- photon, lady of light
- scrollshift
- skycoach conductor // all aboard
- soulherder
- teleportation circle
- wispweaver angel
- xho cai, flickering talon

aethergeode miner:
  -unsupported=["Pay {E}{E}: Exile ~
  -then return it to the battlefield under its owner's control."]
  +activated=[Activated(kind='ability'
  +cost={'generic': 0}
  +effects=[Effect(kind='flicker'
  +target='self')]
  +extra_costs={'energy': 2}
  +text="Pay {E}{E}: Exile ~
  +then return it to the battlefield under its owner's control.")]

against all odds:
  -unsupported=["• Exile target artifact or creature you control
  -then return it to the battlefield under its owner's control."]
  -modes=[[Effect(kind='gy_move'
  +modes=[[Effect(kind='flicker'
  +target='permanent'
  +data={'selector': {'controller': 'mine'
  +'types_any': ['artifact'
  +'creature']}})]
  +[Effect(kind='gy_move'

blur:
  -spell_effects=[Effect(kind='draw'
  +spell_effects=[Effect(kind='flicker'
  +target='permanent'
  +data={'selector': {'controller': 'mine'
  +'types_all': ['creature']}})
  +Effect(kind='draw'
  -unsupported=["Exile target creature you control
  -then return that card to the battlefield under their owner's control."]

distinguished conjurer:
  -unsupported=["{4}{W}
  -{T}: Exile another target creature you control
  -then return it to the battlefield under its owner's control."]
  +activated=[Activated(kind='ability'
  +cost={'generic': 4
  +'W': 1}
  +effects=[Effect(kind='flicker'
  +target='permanent'
  +data={'selector': {'controller': 'mine'
  +'types_all': ['creature']
  +'other': True}})]
  +extra_costs={'tap': True}
  +text="{4}{W}
  +{T}: Exile another target creature you control
  +then return it to the battlefield under its owner's control.")]

emiel the blessed:
  -unsupported=["{3}: Exile another target creature you control
  -then return it to the battlefield under its owner's control."
  -'you may pay {G/W}.'
  +unsupported=['you may pay {G/W}.'
  +activated=[Activated(kind='ability'
  +cost={'generic': 3}
  +effects=[Effect(kind='flicker'
  +target='permanent'
  +data={'selector': {'controller': 'mine'
  +'types_all': ['creature']
  +'other': True}})]
  +text="{3}: Exile another target creature you control
  +then return it to the battlefield under its owner's control.")]
