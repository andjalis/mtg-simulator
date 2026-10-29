"""Non-targeted bounded graveyard returns through the existing gy_move effect.

Known type/subtype filters and mana-value bounds are supported. Targeted,
related-card, supertype, chosen-type and ownership variants remain unsupported
by these templates, so their target requirements are never silently discarded.
"""
from __future__ import annotations

import re

_TYPES = {'artifact', 'creature', 'enchantment', 'land', 'planeswalker', 'instant', 'sorcery'}
_N = r'one|two|three|four|five|six|seven|eight|nine|ten|X|\d+'


def _descriptor(what):
    alternatives = re.split(r',? (?:or|and/or) |, ', what)
    for part in alternatives:
        if part.lower() in _TYPES:
            continue
        match = re.fullmatch(r'([A-Z][a-z]+(?:-[A-Z][a-z]+)?)(?: (creature|artifact|enchantment|land|planeswalker))?', part)
        if not match or match[1].lower() in ('basic', 'legendary', 'snow', 'world', 'colorless',
                                                  'permanent', 'nonlegendary', 'nonland', 'noncreature', 'nonartifact'):
            return None
    return ' or '.join(alternatives)


def _return(match):
    from .cards.model import Effect, NO_MATCH, _num
    what = _descriptor(match['what'])
    if what is None:
        return NO_MATCH
    variable = bool(match['n'] and match['n'].upper() == 'X')
    all_cards = match['count'].lower() == 'all'
    n = 99 if all_cards else 0 if variable else _num(match['n'])
    if n == 99 and not all_cards:
        return NO_MATCH  # gy_move reserves 99 as its unbounded-selection sentinel
    cmc = None
    if match['mv']:
        cmc = ('x' if match['mv'].upper() == 'X' else int(match['mv']), match['cmp'].lower())
    return Effect('gy_move', n, data={'what': what, 'dest': 'hand', 'tapped': False,
                                     'zone': 'mine', 'x_n': variable, 'cmc': cmc})


EFFECT_PATTERNS = [
    (rf'(?:then )?return (?P<count>up to (?P<n>{_N})|all) (?P<what>[\w ,/-]+?) cards?'
     r'(?: with mana value (?P<mv>X|\d+) or (?P<cmp>less|greater))? '
     r'from your graveyard to your hand', _return),
]
SUBS = []
