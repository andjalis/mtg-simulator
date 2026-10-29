Base: 688e8541087b
Card parsing: 130 of 34129 cards parse differently from the base branch.

Changed cards (first 100):

- a-druidic ritual
- accumulate wisdom
- aethergeode miner
- against all odds
- amrou scout
- another chance
- archival whorl
- archive trap
- arzakon
- behold the beyond
- biblioplex assistant
- blessed respite
- blightspeaker
- blur
- bog glider
- bond of insight
- boseiju reaches skyward // branch of boseiju
- bramble familiar // fetch quest
- brightglass gearhulk
- bringer of the black dawn
- captain america, liberator
- cateran brute
- cateran enforcer
- cateran kidnappers
- cateran overlord
- cateran persuader
- cateran slaver
- clear the mind
- commit // memory
- congregation at dawn
- court hussar
- cranial archive
- cruel tutor
- day's undoing
- defiant falcon
- defiant vanguard
- diminishing returns
- distinguished conjurer
- dread summons
- dukhara scavenger
- echo of eons
- elder pine of jukai
- emergency powers
- emiel the blessed
- enhanced surveillance
- enlistment officer
- enshrined memories
- experimental augury
- false mourning
- fascination
- feldon's cane
- felidar guardian
- flash of insight
- flicker
- flicker of fate
- flickering hound
- flickering spirit
- fractured sanity
- game plan
- garruk, caller of beasts
- gix's command
- goblin ringleader
- grave defiler
- hallowed respite
- immortus, master of eternity
- imperial seal
- increasing confusion
- jace beleren
- jace, the living guildpact
- kairi, the swirling sky
- kavu howler
- kimoyo beads
- lair delve
- learn from the past
- liliana vess
- liliana's indignation
- marina vendrell
- meldweb curator
- merfolk wayfinder
- mine, mine, mine!
- mnemonic nexus
- oji, the exquisite blade
- paradigm shift
- photon, lady of light
- planar engineering
- primal command
- prophetic bolt
- psychic drain
- ramosian captain
- ramosian commander
- ramosian lieutenant
- ramosian sergeant
- ramosian sky marshal
- ranger of eos
- rathi assassin
- rathi fiend
- rathi intimidator
- reclaim
- reminisce
- reshape the earth

a-druidic ritual:
  -amount=3)]
  -unsupported=['Then return up to two creature and/or land cards from your graveyard to your hand.']
  +amount=3)
  +Effect(kind='gy_move'
  +amount=2
  +data={'what': 'creature or land'
  +'dest': 'hand'
  +'tapped': False
  +'zone': 'mine'
  +'x_n': False
  +'cmc': None})]

accumulate wisdom:
  -unsupported=['Look at the top three cards of your library.'
  -'Put one of those cards into your hand and the rest on the bottom of your library in any order.'
  -'Put each of those cards into your hand instead if there are three or more Lesson cards in your graveyard.']
  +spell_effects=[Effect(kind='dig'
  +amount=3
  +amount2=1)]
  +unsupported=['Put each of those cards into your hand instead if there are three or more Lesson cards in your graveyard.']

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

amrou scout:
  -unsupported=['{4}
  -{T}: Search your library for a Rebel permanent card with mana value 3 or less
  -put it onto the battlefield
  -then shuffle.']
  +activated=[Activated(kind='ability'
  +cost={'generic': 4}
  +effects=[Effect(kind='search'
  +data={'what': 'a Rebel artifact card with mana value 3 or less or a Rebel battle card with mana value 3 or less or a Rebel creature card with mana value 3 or less or a Rebel enchantment card with mana value 3 or less or a Rebel land card with mana value 3 or less or a Rebel planeswalker card with mana value 3 or less'
  +'n': 1
  +'dest': 'battlefield'
  +'tapped': False})]
  +extra_costs={'tap': True}
  +text='{4}
  +{T}: Search your library for a Rebel permanent card with mana value 3 or less
  +put it onto the battlefield
  +then shuffle.')]
