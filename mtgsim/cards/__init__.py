"""Turn Scryfall card JSON into the simplified CardDef the engine understands.

Oracle text is matched sentence by sentence against a small set of templates.
Anything that does not match is recorded in CardDef.unsupported so reports can
say which cards are only partially simulated.

Modules: model (data classes), patterns (oracle-text templates), parse (card parsing) and
tokens. Mechanic modules such as removal.py and copies.py add their templates at the end of this file.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from .. import graveyard, milling, modal, returns

from .model import (
    COLORS, KEYWORDS, BASIC_MANA, NUMBERS, COLOR_WORDS, NO_MATCH, _distinct_bounce, _distinct_pump, _num, Effect,
    Trigger, AltCost, Activated, CardDef, parse_mana_cost, add_mana,
)
from .patterns import (
    _parse_mana_ability, _token, _distinct_cant_block, _TENS, _tapped, _SRC, _EFFECT_PATTERNS, _SUBS, _TRIGGERS,
    _OPT_RIDER, _opt_rider, _N_WORDS, _gy_move, _kw_target, _xq, _IF_CONDS, _if_cond,
)
from .parse import (
    _parse_effects, _split_compound, _apply_speed_gate, _face_types, card_from_scryfall, _cost_line, _parse_face,
    _mana_restriction, _SACRIFICE_KINDS, _parse_ability_cost, _parse_ability, _parse_trigger, _parse_trigger_line,
)
from .tokens import TOKEN_ABILITIES, make_token, _JACE, jace_token, _ROLES, role_token

# Copy effects live in their own module; its templates join the ones above.
from .. import auras as _auras, copies as _copies, removal as _removal, search as _search, xspells as _xspells, counting as _counting, milling as _milling, distribute as _distribute  # noqa: E402
_EFFECT_PATTERNS += _copies.EFFECT_PATTERNS + _removal.EFFECT_PATTERNS + _auras.EFFECT_PATTERNS + _search.EFFECT_PATTERNS + _xspells.EFFECT_PATTERNS + _counting.EFFECT_PATTERNS
_EFFECT_PATTERNS += _milling.EFFECT_PATTERNS + _distribute.EFFECT_PATTERNS
_SUBS += _copies.SUBS + _counting.SUBS
