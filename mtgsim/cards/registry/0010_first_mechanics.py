"""Registers the first mechanic modules: copies, removal, auras, search, xspells, counting, milling, protection, ..."""
from ... import (auras as _auras, copies as _copies, removal as _removal, search as _search, xspells as _xspells,
                 counting as _counting, milling as _milling, protection as _protection,
                 combat_triggers as _combat_triggers, ring as _ring)

EFFECT_PATTERNS = [
    *_copies.EFFECT_PATTERNS,
    *_removal.EFFECT_PATTERNS,
    *_auras.EFFECT_PATTERNS,
    *_search.EFFECT_PATTERNS,
    *_xspells.EFFECT_PATTERNS,
    *_counting.EFFECT_PATTERNS,
    *_milling.EFFECT_PATTERNS,
    *_protection.EFFECT_PATTERNS,
    *_combat_triggers.EFFECT_PATTERNS,
    *_ring.EFFECT_PATTERNS,
]
SUBS = [
    *_copies.SUBS,
    *_counting.SUBS,
]
