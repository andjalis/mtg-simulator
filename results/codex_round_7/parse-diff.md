Base: b8d12a61482b
Card parsing: 5 of 34129 cards parse differently from the base branch.

Changed cards:

- a-druidic ritual
- another chance
- bond of insight
- gix's command
- kairi, the swirling sky

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

another chance:
  -amount=2)]
  -unsupported=['Then return up to two creature cards from your graveyard to your hand.']
  +amount=2)
  +Effect(kind='gy_move'
  +amount=2
  +data={'what': 'creature'
  +'dest': 'hand'
  +'tapped': False
  +'zone': 'mine'
  +'x_n': False
  +'cmc': None})]

bond of insight:
  +Effect(kind='gy_move'
  +amount=2
  +data={'what': 'instant or sorcery'
  +'dest': 'hand'
  +'tapped': False
  +'zone': 'mine'
  +'x_n': False
  +'cmc': None})
  -unsupported=['Return up to two instant and/or sorcery cards from your graveyard to your hand.']

gix's command:
  -'• Return up to two creature cards from your graveyard to your hand.'
  +modes=[[Effect(kind='gy_move'
  +amount=2
  +data={'what': 'creature'
  +'dest': 'hand'
  +'tapped': False
  +'zone': 'mine'
  +'x_n': False
  +'cmc': None})]]

kairi, the swirling sky:
  -unsupported=["• Return any number of target nonland permanents with total mana value 6 or less to their owners' hands."
  -'• Mill six cards
  -then return up to two instant and/or sorcery cards from your graveyard to your hand.']
  +unsupported=["• Return any number of target nonland permanents with total mana value 6 or less to their owners' hands."]
  +triggers=[Trigger(event='dies'
  +effects=[]
  +modes=[[Effect(kind='mill'
  +amount=6)
  +Effect(kind='gy_move'
  +amount=2
  +data={'what': 'instant or sorcery'
  +'dest': 'hand'
  +'tapped': False
  +'zone': 'mine'
  +'x_n': False
  +'cmc': None})]])]
