Base: b8d12a61482b
Card parsing: 28 of 34129 cards parse differently from the base branch.

Changed cards:

- amrou scout
- behold the beyond
- blightspeaker
- bog glider
- brightglass gearhulk
- captain america, liberator
- cateran brute
- cateran enforcer
- cateran kidnappers
- cateran overlord
- cateran persuader
- cateran slaver
- congregation at dawn
- defiant falcon
- defiant vanguard
- planar engineering
- ramosian captain
- ramosian commander
- ramosian lieutenant
- ramosian sergeant
- ramosian sky marshal
- ranger of eos
- rathi assassin
- rathi fiend
- rathi intimidator
- reshape the earth
- soul of mirrodin
- zur the enchanter

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

behold the beyond:
  -unsupported=['Discard your hand.'
  -'Search your library for three cards
  -put them into your hand
  -then shuffle.']
  +spell_effects=[Effect(kind='search'
  +data={'what': 'a card'
  +'n': 3
  +'dest': 'hand'
  +'tapped': False})]
  +unsupported=['Discard your hand.']

blightspeaker:
  -unsupported=['{4}
  -{T}: Search your library for a Rebel permanent card with mana value 3 or less
  -put it onto the battlefield
  -then shuffle.']
  -text='{T}: Target player loses 1 life.')]
  +text='{T}: Target player loses 1 life.')
  +Activated(kind='ability'
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

bog glider:
  -unsupported=['{T}
  -Sacrifice a land: Search your library for a Mercenary permanent card with mana value 2 or less
  -put it onto the battlefield
  -then shuffle.']
  +activated=[Activated(kind='ability'
  +cost={'generic': 0}
  +effects=[Effect(kind='search'
  +data={'what': 'a Mercenary artifact card with mana value 2 or less or a Mercenary battle card with mana value 2 or less or a Mercenary creature card with mana value 2 or less or a Mercenary enchantment card with mana value 2 or less or a Mercenary land card with mana value 2 or less or a Mercenary planeswalker card with mana value 2 or less'
  +'n': 1
  +'dest': 'battlefield'
  +'tapped': False})]
  +extra_costs={'tap': True
  +'sacrifice': 'land'}
  +text='{T}
  +Sacrifice a land: Search your library for a Mercenary permanent card with mana value 2 or less
  +put it onto the battlefield
  +then shuffle.')]

brightglass gearhulk:
  -unsupported=['you may search your library for up to two artifact
  -creature
  -and/or enchantment cards with mana value 1 or less
  -reveal them
  -put them into your hand
  -then shuffle.']
  +etb_effects=[Effect(kind='pay_gate'
  +data={'gate': ('may'
  +'')})
  +Effect(kind='search'
  +data={'what': 'a artifact card with mana value 1 or less or a creature card with mana value 1 or less or a enchantment card with mana value 1 or less'
  +'n': 2
  +'dest': 'hand'
  +'tapped': False})]
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='pay_gate'
  +data={'gate': ('may'
  +'')})
  +Effect(kind='search'
  +data={'what': 'a artifact card with mana value 1 or less or a creature card with mana value 1 or less or a enchantment card with mana value 1 or less'
  +'n': 2
  +'dest': 'hand'
  +'tapped': False})])]
