Base: 57a1c523c5b0
Card parsing: 10 of 34129 cards parse differently from the base branch.

Changed cards:

- biblioplex assistant
- boseiju reaches skyward // branch of boseiju
- dukhara scavenger
- false mourning
- meldweb curator
- reclaim
- runo stromkirk // krothuss, lord of the deep
- salvage
- treason of isengard
- woodland acolyte // mend the wilds

biblioplex assistant:
  -unsupported=['put up to one target instant or sorcery card from your graveyard on top of your library.']
  +etb_effects=[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'instant or sorcery'
  +'optional_target': True})]
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'instant or sorcery'
  +'optional_target': True})])]

boseiju reaches skyward // branch of boseiju:
  -unsupported=['II — Put up to one target land card from your graveyard on top of your library.']
  -[]
  +[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'land'
  +'optional_target': True})]

dukhara scavenger:
  -unsupported=['you may put target artifact or creature card from your graveyard on top of your library.']
  +etb_effects=[Effect(kind='pay_gate'
  +data={'gate': ('may'
  +'')})
  +Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'artifact or creature'
  +'optional_target': False})]
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='pay_gate'
  +data={'gate': ('may'
  +'')})
  +Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'artifact or creature'
  +'optional_target': False})])]

false mourning:
  -unsupported=['Put target card from your graveyard on top of your library.']
  +spell_effects=[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'permanent or instant or sorcery'
  +'optional_target': False})]

meldweb curator:
  -unsupported=['put up to one target instant or sorcery card from your graveyard on top of your library.']
  +etb_effects=[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'instant or sorcery'
  +'optional_target': True})]
  +triggers=[Trigger(event='etb'
  +effects=[Effect(kind='grave_library_top'
  +target='graveyard_card'
  +data={'grave_type': 'instant or sorcery'
  +'optional_target': True})])]
