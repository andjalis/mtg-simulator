"""Single-card library-top searches using the existing search resolution.

Only known type filters are accepted. Unknown qualifiers, multiple selections,
other players' libraries and special search destinations remain unsupported.
"""
from __future__ import annotations

_TYPE = r'(?:creature|artifact|enchantment|land|planeswalker|instant|sorcery|battle)'
_WHAT = rf'(?:card|{_TYPE}(?: or {_TYPE})? card|basic land card)'


def _top(match):
    from .cards.model import Effect
    return Effect('search', data={
        'what': 'a ' + match['what'], 'n': 1, 'dest': 'top', 'tapped': False})


EFFECT_PATTERNS = [
    (rf'(?:you may )?search your library for an? (?P<what>{_WHAT})'
     r'(?:, reveal (?:it|that card))?, then shuffle and put '
     r'(?:the card|that card|it) on top(?: of your library)?', _top),
]
SUBS = []
