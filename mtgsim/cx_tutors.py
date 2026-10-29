"""Bounded library searches and fixed-count library-top selections.

Descriptions are validated before using card_matches: card types, type unions,
plain subtypes, subtype permanents and basic lands are the supported subset.
Color, supertype, relationship, X and different-name restrictions stay visible.
"""
from __future__ import annotations

import re

_TYPES = {'artifact', 'battle', 'creature', 'enchantment', 'land', 'planeswalker', 'instant', 'sorcery'}
_PERMANENTS = sorted(_TYPES - {'instant', 'sorcery'})
_N = r'an?|(?:up to )?(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)'
_HEAD = (rf'(?:you may )?search your library for (?P<n>{_N}) '
         r'(?:(?P<what>[\w ,/-]+?) )?cards?'
         r'(?P<limit> with mana value \d+ or (?:less|greater))?'
         r'(?:, reveal (?:it|them|that card|those cards))?')


def _descriptions(what):
    if not what:
        return ['card']
    if what.lower() == 'basic land':
        return ['basic land card']
    parts = re.split(r',? (?:or|and/or) |, ', what)
    descriptions = []
    for part in parts:
        low = part.lower()
        if low in _TYPES:
            descriptions.append(low + ' card')
        elif low == 'permanent':
            descriptions.extend(t + ' card' for t in _PERMANENTS)
        else:
            m = re.fullmatch(r'([A-Z][a-z]+(?:-[A-Z][a-z]+)?)( permanent)?', part)
            if not m or m[1] in ('Basic', 'Legendary', 'Snow', 'World', 'Colorless'):
                return None
            if m[2]:
                descriptions.extend(m[1] + ' ' + t + ' card' for t in _PERMANENTS)
            else:
                descriptions.append(m[1] + ' card')
    return descriptions


def _search(match, *, top=False):
    from .cards.model import Effect, NO_MATCH, _num
    parts = _descriptions(match['what'])
    if parts is None:
        return NO_MATCH
    n = match['n'].lower().split()[-1]
    if top and _num(n) <= 1:
        return NO_MATCH  # single-card top searches belong to cx_library
    limit = match['limit'] or ''
    # Repeat the bound in each alternative: card_matches applies it per branch.
    desc = ' or '.join('a ' + part + limit for part in parts)
    dest = 'top' if top else 'hand' if 'hand' in match['dest'] else 'battlefield'
    return Effect('search', data={'what': desc, 'n': _num(n), 'dest': dest,
                                  'tapped': False if top else match['dest'].endswith('tapped')})


EFFECT_PATTERNS = [
    (_HEAD + r', put (?:it|them|that card|those cards) '
     r'(?P<dest>into your hand|onto the battlefield(?: tapped)?), then shuffle', _search),
    (_HEAD + r', then shuffle and put (?:it|them|that card|the card|those cards) '
     r'on top(?: of your library)?(?: in any order)?', lambda m: _search(m, top=True)),
]
SUBS = []
