"""Turn Scryfall card JSON into the simplified CardDef the engine understands.

Oracle text is matched sentence by sentence against a small set of templates.
Anything that does not match is recorded in CardDef.unsupported so reports can
say which cards are only partially simulated.

Modules: model (data classes), patterns (effect templates), clauses (substitutions, trigger templates
and clause helpers), parse and face_lines (card parsing) and tokens. Mechanic modules such as removal.py
and copies.py add their templates through a registration file in cards/registry/ (see its __init__).
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
    _parse_mana_ability, _token, _distinct_cant_block, _TENS, _tapped, _SRC, _EFFECT_PATTERNS, _N_WORDS, _gy_move,
    _kw_target,
)
from .clauses import _SUBS, _TRIGGERS, _OPT_RIDER, _opt_rider, _xq, _IF_CONDS, _if_cond
from .parse import (
    _parse_effects, _split_compound, _apply_speed_gate, _face_types, card_from_scryfall, _cost_line, _parse_face,
    _mana_restriction, _SACRIFICE_KINDS, _parse_ability_cost, _parse_ability, _parse_trigger, _parse_trigger_line,
)
from .tokens import TOKEN_ABILITIES, make_token, _JACE, jace_token, _ROLES, role_token

# Mechanic modules (copies.py, removal.py, ...) join the templates above through their registration file in
# cards/registry/ (NNNN_<module>.py, loaded in filename order): add a file there instead of a line here.
from . import parse as _parse_module  # noqa: E402
from .face_lines import LINE_HOOKS as _LINE_HOOKS  # noqa: E402
from . import registry as _registry  # noqa: E402
_registry.load_all(_EFFECT_PATTERNS, _SUBS, _TRIGGERS, KEYWORDS, _parse_module, _LINE_HOOKS)
# Transition only: lines an older branch still appends below this one keep working (the names above still exist);
# when resolving such a branch, move them into a registry file instead (CONTRIBUTING.md, "Adding a template module").
