Base: b8d12a61482b
Card parsing: 19 of 34129 cards parse differently from the base branch.

Changed cards:

- accumulate wisdom
- court hussar
- elder pine of jukai
- enlistment officer
- enshrined memories
- experimental augury
- flash of insight
- garruk, caller of beasts
- goblin ringleader
- grave defiler
- kavu howler
- lair delve
- marina vendrell
- merfolk wayfinder
- prophetic bolt
- see the truth
- sylvan messenger
- tidal courier
- witness the future

accumulate wisdom:
  -unsupported=['Look at the top three cards of your library.'
  -'Put one of those cards into your hand and the rest on the bottom of your library in any order.'
  -'Put each of those cards into your hand instead if there are three or more Lesson cards in your graveyard.']
  +spell_effects=[Effect(kind='dig'
  +amount=3
  +amount2=1)]
  +unsupported=['Put each of those cards into your hand instead if there are three or more Lesson cards in your graveyard.']

court hussar:
  -unsupported=['look at the top three cards of your library
  -then put one of them into your hand and the rest on the bottom of your library in any order.'
  -'sacrifice it unless {W} was spent to cast it.']
  +etb_effects=[Effect(kind='dig'
  +amount=3
  +amount2=1)]
  +unsupported=['sacrifice it unless {W} was spent to cast it.']
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='dig'
  +amount=3
  +amount2=1)])]

elder pine of jukai:
  -unsupported=['reveal the top three cards of your library.'
  -'Put all land cards revealed this way into your hand and the rest on the bottom of your library in any order.']
  -triggers=[Trigger(event='dies'
  +triggers=[Trigger(event='cast_spell'
  +effects=[Effect(kind='dig'
  +amount=3
  +amount2=3
  +data={'filter': 'a land card'})]
  +filter='spell:Spirit|Arcane')
  +Trigger(event='dies'

enlistment officer:
  -unsupported=['reveal the top four cards of your library.'
  -'Put all Soldier cards revealed this way into your hand and the rest on the bottom of your library in any order.']
  +etb_effects=[Effect(kind='dig'
  +amount=4
  +amount2=4
  +data={'filter': 'a Soldier card'})]
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='dig'
  +amount=4
  +amount2=4
  +data={'filter': 'a Soldier card'})])]

enshrined memories:
  -unsupported=['Reveal the top 1 cards of your library.'
  -'Put all creature cards revealed this way into your hand and the rest on the bottom of your library in any order.']
  +spell_effects=[Effect(kind='dig'
  +data={'filter': 'a creature card'
  +'x': True
  +'x2': True})]
