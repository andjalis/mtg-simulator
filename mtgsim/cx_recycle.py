"""Whole-zone recycling into libraries, optionally followed by drawing.

Movements preserve physical cards. Every affected library is shuffled before any
follow-up draw; players draw in active-player order. Shuffling is not searching,
milling or discarding. Spell sources on the stack are naturally excluded.
"""
from __future__ import annotations

KINDS = {'cx_recycle'}
MINOR_VALUES = {'cx_recycle': 1.5}
_COUNT = r'a|one|two|three|four|five|six|seven|eight|nine|ten|\d+'


def _effect(scope, *, hand=False, draw=None):
    from .cards.model import Effect, _num
    return Effect('cx_recycle', _num(draw) if draw else 0,
                  target='player' if scope == 'target' else 'none',
                  data={'scope': scope, 'hand': hand, 'draw': draw is not None})


EFFECT_PATTERNS = [
    (r'target player shuffles their graveyard into their library', lambda m: _effect('target')),
    (r'each player shuffles their graveyard into their library', lambda m: _effect('each')),
    (r'shuffle your graveyard into your library', lambda m: _effect('you')),
    (rf'each player shuffles their hand and graveyard into their library(?:, then draws (?P<n>{_COUNT}) cards?)?',
     lambda m: _effect('each', hand=True, draw=m['n'])),
    (rf'shuffle your hand and graveyard into your library(?:, then draw (?P<n>{_COUNT}) cards?)?',
     lambda m: _effect('you', hand=True, draw=m['n'])),
]
SUBS = []


def choose_target(game, player, effect):
    """Default to a legal self target; explicit targets can recycle either player."""
    legal = game.legal_targets(player, effect)
    return player if player in legal else next(iter(legal), None)


def resolve(game, player, effect, target, item):
    scope = effect.data['scope']
    if scope == 'target':
        players = [target] if target in game.players else []
    elif scope == 'you':
        players = [player]
    else:
        players = [game.active] + [p for p in game.players if p is not game.active]
    for who in players:
        zones = [who.hand, who.graveyard] if effect.data['hand'] else [who.graveyard]
        for zone in zones:
            for card in list(zone):
                game.move_card(card, zone, who.library, reason='recycle')
        who.library.shuffle(game.rng)
        game.log('shuffles cards into their library', who)
    if effect.data['draw']:
        for who in players:
            game.draw(who, effect.amount)
