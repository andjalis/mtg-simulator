"""Library-top selections with a hand destination and a bottomed remainder.

Known card types and plain capitalized subtypes are supported filters. Unknown
qualifiers, graveyard/exile remainders and battlefield destinations stay ignored.
"""
from __future__ import annotations

import re

_COUNT = r'X|one|two|three|four|five|six|seven|eight|nine|ten|\d+'
_TYPES = {'artifact', 'battle', 'creature', 'enchantment', 'land', 'planeswalker', 'instant', 'sorcery'}
_BOTTOM = r'(?:the )?rest on the bottom of your library(?: in (?:a random|any|any random) order)?\.'
_ALL = re.compile(
    rf'(?:you )?(?:look at|reveal) the top (?P<n>{_COUNT}) cards? of your library(?:\.\s+|, (?:then )?)'
    r'put all (?P<what>[\w ,/-]+?) cards? (?:revealed this way|from among them) into your hand and ' + _BOTTOM,
    re.I)
_FIXED = re.compile(
    rf'(?:you )?look at the top (?P<n>{_COUNT}) cards? of your library(?:\.\s+|, (?:then )?)'
    rf'put (?P<keep>{_COUNT}) (?:of them|of those cards) into your hand and ' + _BOTTOM,
    re.I)


def _description(what):
    if not what:
        return None
    parts = re.split(r',? (?:or|and/or|and) |, ', what)
    for part in parts:
        if part.lower() not in _TYPES and not re.fullmatch(r'[A-Z][a-z]+(?:-[A-Z][a-z]+)?', part):
            return None
        if part in ('Basic', 'Legendary', 'Snow', 'World', 'Colorless'):
            return None
    return 'a ' + ' or '.join(part.lower() if part.lower() in _TYPES else part for part in parts) + ' card'


def _encode(match, *, only_x=False):
    from .cards.model import _num
    if only_x and match['n'].upper() != 'X':
        return match[0]
    what = match.groupdict().get('what')
    if what and _description(what) is None:
        return match[0]
    keep = 'ALL' if what else str(_num(match['keep']))
    if not what and match['keep'].upper() == 'X':
        return match[0]  # no independent X-valued keep count in this subset
    n = 'X' if match['n'].upper() == 'X' else str(_num(match['n']))
    return f"CXSELECTION {n} {keep}" + (' ' + what if what else '') + '.'


def preserve_x(text):
    """Protect supported paid-X sequences from the legacy printed-MV fallback."""
    text = _ALL.sub(lambda m: _encode(m, only_x=True), text)
    return _FIXED.sub(lambda m: _encode(m, only_x=True), text)


def _selection(match):
    from .cards.model import Effect, NO_MATCH
    what = match['what']
    desc = _description(what)
    if what and desc is None:
        return NO_MATCH
    variable = match['n'].upper() == 'X'
    all_matching = match['keep'] == 'ALL'
    amount = 0 if variable else int(match['n'])
    keep = amount if all_matching else int(match['keep'])
    data = {'filter': desc} if desc else {}
    if variable:
        data.update(x=True, x2=all_matching)
    return Effect('dig', amount, keep, data=data)


EFFECT_PATTERNS = [
    (r'CXSELECTION (?P<n>X|\d+) (?P<keep>ALL|\d+)(?: (?P<what>.+))?', _selection),
]
SUBS = [(_ALL, _encode), (_FIXED, _encode)]
