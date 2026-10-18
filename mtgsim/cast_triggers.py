"""Cast-triggered keywords and free casts from exile during their resolution."""
from __future__ import annotations

import dataclasses

KINDS = {'storm_copy', 'cascade'}


def on_cast(game, p, item):
    from .cards import Effect
    for _ in range(item.card.storm or int('storm' in item.card.keywords)):
        game.queue_trigger(p, [Effect('storm_copy', getattr(item, 'storm_count', 0))],
                           name=f'{item.card.name}: storm', context=item)
    for _ in range(item.card.cascade or int('cascade' in item.card.keywords)):
        value = item.card.cmc + getattr(item, 'x', 0) * item.card.mana_cost.get('X', 0)
        game.queue_trigger(p, [Effect('cascade', value)], name=f'{item.card.name}: cascade')


def cast_exiled(game, p, card, kind, *, limit=None):
    """Cast a card (or its Adventure) without its mana cost, retaining its exile origin."""
    from .cards import AltCost
    from .engine import TARGETED
    faces = [card] + ([card.adventure] if card.adventure is not None else [])
    for face in faces:
        if face.is_land or limit is not None and face.cmc >= limit:
            continue
        free = dataclasses.replace(face, name=f'{face.name} ({kind})', mana_cost={'generic': 0}, hybrid=())
        origin_kind = f'{kind}_adventure' if face is not card else kind
        free.origin = (card, origin_kind, AltCost(origin_kind, {'generic': 0}))
        # The chosen spell face supplies its own effects and permanent characteristics.
        free.cast_face = face
        targets = game.auto_targets(p, free.spell_effects)
        if any(e.target in TARGETED and not game.legal_target(p, e, t)
               for e, t in zip(free.spell_effects, targets)):
            continue
        if game.can_cast_now(p, free, during_resolution=True) and game.cast(p, free, targets):
            return True
    return False


def resolve(game, p, eff, item):
    from . import copies
    if eff.kind == 'storm_copy':
        for _ in range(eff.amount):
            copies.copy_spell(game, p, item.context)
        return
    revealed = []
    found = None
    while p.library:
        card = dataclasses.replace(p.library.pop())
        p.exile.append(card)
        revealed.append(card)
        if not card.is_land and card.cmc < eff.amount:
            found = card
            break
    if found is not None and game.hook(p, 'choose_cascade')(game, p, found):
        cast_exiled(game, p, found, 'cascade', limit=eff.amount)
    bottom = []
    for card in revealed:
        index = next((i for i, c in enumerate(p.exile) if c is card), None)
        if index is not None:
            del p.exile[index]
            bottom.append(card)
    game.rng.shuffle(bottom)
    p.library[0:0] = bottom
