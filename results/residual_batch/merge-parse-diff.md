Base: 9d6eb8ca9187
Card parsing: 2585 of 34129 cards parse differently from the base branch.

Changed cards (first 100):

- "ach! hans, run!"
- a realm reborn
- a-buy your silence
- a-dueling coach
- a-kargan intimidator
- a-phylath, world sculptor
- a-rowan, scholar of sparks // a-will, scholar of frost
- a-sigardian paladin
- a-sorcerer class
- a-sorin, imperious bloodlord
- a-tatyova, steward of tides
- a-teferi, time raveler
- a-tyvar kell
- a-urza's command
- aang's defense
- aang, air nomad
- aang, at the crossroads // aang, destined savior
- abduction
- aberrant manawurm
- abeyance
- abiding grace
- aboshan, cephalid emperor
- absolute grace
- absolute law
- abstergo entertainment
- abstruse appropriation
- abuelo, ancestral echo
- abundant growth
- abzan charm
- academy elite
- academy manufactor
- academy ruins
- accelerated mutation
- accursed horde
- acid-spewer dragon
- acidic slime
- acidic sliver
- active volcano
- adaptive training post
- adept watershaper
- adventuring gear
- advocate of the beast
- aegis automaton
- aerial guide
- aerial maneuver
- aerie mystics
- aerith gainsborough
- aeromunculus
- aeronaut admiral
- aeronaut cavalry
- aether channeler
- aether chaser
- aether herder
- aether hub
- aether inspector
- aether meltdown
- aether poisoner
- aether shockwave
- aether swooper
- aether theorist
- aetherflux car
- aethergeode miner
- aetheric amplifier
- aetherjacket
- aetherling
- aethershield artificer
- aethersphere harvester
- aethersquall ancient
- aetherstorm roc
- aetherstream leopard
- aethertide whale
- aethertorch renegade
- aetherwind basker
- aftershock
- agate assault
- agatha of the vile cauldron
- agent of treachery
- aggression
- aggressive mammoth
- aim for the head
- air marshal
- air servant
- airtight alibi
- ajani fells the godsire
- ajani resolute
- ajani unyielding
- ajani's anguish
- ajani, inspiring leader
- ajani, strength of the pride
- ajani, the greathearted
- ajani, valiant protector
- ajani, wise counselor
- akki scrapchomper
- akroan line breaker
- akroma's devoted
- akroma's memorial
- alesha's legacy
- ali baba
- aliban's tower
- alibou, ancient witness

"ach! hans, run!":
  -run! It\'s the .'
  -'." and the name of a creature card.'
  +run! It\'s the . . ." and the name of a creature card.'

a realm reborn:
  -grant_mana=(('other'
  -{'B'
  +ability_grants=(({'other': True
  +'controller': 'mine'
  +'types_all': ['permanent']}
  +Activated(kind='granted_mana'
  +cost={}
  +keywords={'B'
  -'W'}))
  +'W'}
  +text='{T}: Add one mana of any color.')))

a-buy your silence:
  -spell_effects=[Effect(kind='destroy'
  -target='nonland_perm')
  +spell_effects=[Effect(kind='exile_permanent'
  +target='permanent'
  +data={'selector': {'traits': ['nonland']
  +'types_all': ['permanent']}})

a-dueling coach:
  -distribute two +1/+1 counters among one or two target creatures you control.'
  -'{W}
  -{T}: Put a +1/+1 counter on each creature you control with a +1/+1 counter on it.']
  +distribute two +1/+1 counters among one or two target creatures you control.']
  +activated=[Activated(kind='ability'
  +cost={'generic': 0
  +'W': 1}
  +effects=[Effect(kind='permanent_group'
  +data={'selector': {'controller': 'mine'
  +'counter': ['+1/+1'
  +True]
  +'types_all': ['creature']}
  +'effect': Effect(kind='add_counter'
  +amount=1
  +target='self'
  +data={'counter': '+1/+1'})})]
  +extra_costs={'tap': True}
  +text='{W}
  +{T}: Put a +1/+1 counter on each creature you control with a +1/+1 counter on it.')]

a-kargan intimidator:
  -'• Target Warrior gets +1/+1 and gains trample until end of turn.'
  -text="{1}: Choose one that hasn't been chosen this turn —")]
  +text="{1}: Choose one that hasn't been chosen this turn —"
  +modes=[[Effect(kind='pump'
  +amount=1
  +amount2=1
  +target='permanent'
  +data={'selector': {'subtypes': ['warrior']
  +'types_any': ['permanent']}})
  +Effect(kind='grant'
  +target='prev'
  +data={'keyword': 'trample'})]])]
