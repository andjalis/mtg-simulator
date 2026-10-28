"""Conservative graveyard-to-library targets using existing zone-reference rules.

Full clauses only: alternate destinations, multiple targets, subtypes, related
"other" targets and non-targeted selections stay unsupported by this module.
"""
from __future__ import annotations

_TYPES = ('permanent', 'creature', 'artifact', 'enchantment', 'land',
          'planeswalker', 'instant', 'sorcery', 'battle')
_TYPE = '|'.join(_TYPES)
_WHAT = rf'(?:card|(?:{_TYPE})(?: or (?:{_TYPE}))? card)'


def _library_top(match):
    from .cards.model import Effect
    what = match['what'].lower()
    # Every ordinary card is either a permanent, instant or sorcery. Keeping the
    # union explicit reuses the existing exact-type enumeration and reference
    # freezing instead of creating an unvalidated wildcard target category.
    kinds = 'permanent or instant or sorcery' if what == 'card' else what[:-5]
    return Effect('grave_library_top', target='graveyard_card', data={
        'grave_type': kinds, 'optional_target': bool(match['optional'])})


EFFECT_PATTERNS = [
    (rf'put (?P<optional>up to one )?target (?P<what>{_WHAT}) '
     r'from your graveyard on top of your library', _library_top),
]
SUBS = []
