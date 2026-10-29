Base: 16f81326c34e
Card parsing: 6 of 34129 cards parse differently from the base branch.

Changed cards:

- bringer of the black dawn
- cruel tutor
- imperial seal
- liliana vess
- vampiric tutor
- worldly tutor

bringer of the black dawn:
  -unsupported=['If you do
  -search your library for a card
  -then shuffle and put that card on top.']
  -'2')})])]
  +'2')})
  +Effect(kind='search'
  +cond='paid'
  +data={'what': 'a card'
  +'n': 1
  +'dest': 'top'
  +'tapped': False})])]

cruel tutor:
  -spell_effects=[Effect(kind='lose_life'
  +spell_effects=[Effect(kind='search'
  +data={'what': 'a card'
  +'n': 1
  +'dest': 'top'
  +'tapped': False})
  +Effect(kind='lose_life'
  -unsupported=['Search your library for a card
  -then shuffle and put that card on top.']

imperial seal:
  -spell_effects=[Effect(kind='lose_life'
  +spell_effects=[Effect(kind='search'
  +data={'what': 'a card'
  +'n': 1
  +'dest': 'top'
  +'tapped': False})
  +Effect(kind='lose_life'
  -unsupported=['Search your library for a card
  -then shuffle and put that card on top.']

liliana vess:
  -unsupported=['[−2]: Search your library for a card
  -then shuffle and put that card on top.'
  -'[−8]: Put all creature cards from all graveyards onto the battlefield under your control.']
  +unsupported=['[−8]: Put all creature cards from all graveyards onto the battlefield under your control.']
  -target='player')])]
  +target='player')])
  +(-2
  +[Effect(kind='search'
  +data={'what': 'a card'
  +'n': 1
  +'dest': 'top'
  +'tapped': False})])]

vampiric tutor:
  -spell_effects=[Effect(kind='lose_life'
  +spell_effects=[Effect(kind='search'
  +data={'what': 'a card'
  +'n': 1
  +'dest': 'top'
  +'tapped': False})
  +Effect(kind='lose_life'
  -unsupported=['Search your library for a card
  -then shuffle and put that card on top.']
