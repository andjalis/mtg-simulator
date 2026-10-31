"""Turn Scryfall card JSON into the simplified CardDef the engine understands.

Oracle text is matched sentence by sentence against a small set of templates.
Anything that does not match is recorded in CardDef.unsupported so reports can
say which cards are only partially simulated.

Modules: model (data classes), patterns (effect templates), clauses (substitutions, trigger templates
and clause helpers), parse and face_lines (card parsing) and tokens. Mechanic modules such as removal.py
and copies.py add their templates at the end of this file.
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

# Copy effects live in their own module; its templates join the ones above.
from .. import auras as _auras, copies as _copies, removal as _removal, search as _search, xspells as _xspells, counting as _counting, milling as _milling, protection as _protection, combat_triggers as _combat_triggers, ring as _ring  # noqa: E402
_EFFECT_PATTERNS += _copies.EFFECT_PATTERNS + _removal.EFFECT_PATTERNS + _auras.EFFECT_PATTERNS + _search.EFFECT_PATTERNS + _xspells.EFFECT_PATTERNS + _counting.EFFECT_PATTERNS
_EFFECT_PATTERNS += _milling.EFFECT_PATTERNS + _protection.EFFECT_PATTERNS + _combat_triggers.EFFECT_PATTERNS + _ring.EFFECT_PATTERNS
_SUBS += _copies.SUBS + _counting.SUBS
from .. import counter_mechanics as _counter_mechanics
_EFFECT_PATTERNS += _counter_mechanics.EFFECT_PATTERNS
_SUBS += _counter_mechanics.SUBS
from .. import permanent_templates as _permanent_templates
_EFFECT_PATTERNS[:0] = _permanent_templates.PRIORITY_PATTERNS
_EFFECT_PATTERNS += _permanent_templates.EFFECT_PATTERNS
from .. import backlog_templates as _backlog_templates
_EFFECT_PATTERNS += _backlog_templates.EFFECT_PATTERNS
_SUBS += _backlog_templates.SUBS
from .. import advanced_templates as _advanced_templates
_EFFECT_PATTERNS += _advanced_templates.EFFECT_PATTERNS
_SUBS += _advanced_templates.SUBS
from .. import batch1_templates as _batch1_templates
_EFFECT_PATTERNS += _batch1_templates.EFFECT_PATTERNS
from .. import batch2_templates as _batch2_templates
_EFFECT_PATTERNS += _batch2_templates.EFFECT_PATTERNS
from .. import residual_templates as _residual_templates
_EFFECT_PATTERNS += _residual_templates.EFFECT_PATTERNS
_SUBS += _residual_templates.SUBS
from .. import that_much as _that_much
_EFFECT_PATTERNS += _that_much.EFFECT_PATTERNS
_TRIGGERS += _that_much.TRIGGERS
from .. import graveyard_templates as _graveyard_templates
_EFFECT_PATTERNS += _graveyard_templates.EFFECT_PATTERNS
_SUBS += _graveyard_templates.SUBS
_TRIGGERS += _graveyard_templates.TRIGGERS
from .. import exile_templates as _exile_templates
_EFFECT_PATTERNS += _exile_templates.EFFECT_PATTERNS
_SUBS += _exile_templates.SUBS
from .. import sacrifice_templates as _sacrifice_templates
_EFFECT_PATTERNS += _sacrifice_templates.EFFECT_PATTERNS
_SUBS += _sacrifice_templates.SUBS
from .. import token_templates as _token_templates
_EFFECT_PATTERNS += _token_templates.EFFECT_PATTERNS
_SUBS += _token_templates.SUBS
from .. import threaten_templates as _threaten_templates
_EFFECT_PATTERNS += _threaten_templates.EFFECT_PATTERNS
_SUBS += _threaten_templates.SUBS
from .. import life_templates as _life_templates
_EFFECT_PATTERNS += _life_templates.EFFECT_PATTERNS
_TRIGGERS += _life_templates.TRIGGERS
from .. import hand_templates as _hand_templates
_EFFECT_PATTERNS += _hand_templates.EFFECT_PATTERNS
_SUBS += _hand_templates.SUBS
_SUBS += _search.SUBS
from .. import mega2_templates as _mega2_templates
_EFFECT_PATTERNS += _mega2_templates.EFFECT_PATTERNS
_SUBS += _mega2_templates.SUBS
from .. import dungeon_mechanics as _dungeon_mechanics
_EFFECT_PATTERNS += _dungeon_mechanics.EFFECT_PATTERNS
_SUBS += _dungeon_mechanics.SUBS
_TRIGGERS += _dungeon_mechanics.TRIGGERS
from .. import phasing as _phasing
_EFFECT_PATTERNS += _phasing.EFFECT_PATTERNS
_SUBS += _phasing.SUBS
_TRIGGERS += _phasing.TRIGGERS
from .. import ripple as _ripple
_EFFECT_PATTERNS += _ripple.EFFECT_PATTERNS
_TRIGGERS += _ripple.TRIGGERS
from .. import manifest as _manifest
_EFFECT_PATTERNS += _manifest.EFFECT_PATTERNS
_TRIGGERS += _manifest.TRIGGERS
from .. import demonstrate as _demonstrate
_EFFECT_PATTERNS += _demonstrate.EFFECT_PATTERNS
_TRIGGERS += _demonstrate.TRIGGERS
from .. import amplify as _amplify
_EFFECT_PATTERNS += _amplify.EFFECT_PATTERNS
_TRIGGERS += _amplify.TRIGGERS

from .. import prevent_templates as _prevent_templates
_EFFECT_PATTERNS += _prevent_templates.EFFECT_PATTERNS
_SUBS += _prevent_templates.SUBS
from .. import energy_templates as _energy_templates
_EFFECT_PATTERNS += _energy_templates.EFFECT_PATTERNS
_SUBS += _energy_templates.SUBS
from .. import animate_templates as _animate_templates
_EFFECT_PATTERNS += _animate_templates.EFFECT_PATTERNS
_SUBS += _animate_templates.SUBS
from .. import chance_templates as _chance_templates
_EFFECT_PATTERNS += _chance_templates.EFFECT_PATTERNS
_SUBS += _chance_templates.SUBS
_TRIGGERS += _chance_templates.TRIGGERS
from .. import for_mirrodin as _for_mirrodin
_EFFECT_PATTERNS += _for_mirrodin.EFFECT_PATTERNS
_TRIGGERS += _for_mirrodin.TRIGGERS
from .. import prepare as _prepare
_EFFECT_PATTERNS += _prepare.EFFECT_PATTERNS
_SUBS += _prepare.SUBS
from .. import cx_triggers as _cx_triggers
_EFFECT_PATTERNS += _cx_triggers.EFFECT_PATTERNS
_SUBS += _cx_triggers.SUBS
from .. import cx_damage as _cx_damage
_EFFECT_PATTERNS += _cx_damage.EFFECT_PATTERNS
from .. import cx_event_triggers as _cx_event_triggers
_TRIGGERS += _cx_event_triggers.TRIGGERS
from .. import cx_night_quantity as _cx_night_quantity
_EFFECT_PATTERNS += _cx_night_quantity.EFFECT_PATTERNS
from .. import cx_night_groups as _cx_night_groups
_EFFECT_PATTERNS += _cx_night_groups.EFFECT_PATTERNS
from .. import cx_night_multi as _cx_night_multi
_EFFECT_PATTERNS += _cx_night_multi.EFFECT_PATTERNS
from .. import cx_night_xplayer as _cx_night_xplayer
_EFFECT_PATTERNS += _cx_night_xplayer.EFFECT_PATTERNS
from .. import cx_night_untap as _cx_night_untap
_EFFECT_PATTERNS += _cx_night_untap.EFFECT_PATTERNS
from .. import cx_night_flash as _cx_night_flash
_EFFECT_PATTERNS += _cx_night_flash.EFFECT_PATTERNS
from .. import cx_next_turn as _cx_next_turn
_EFFECT_PATTERNS += _cx_next_turn.EFFECT_PATTERNS
from .. import cx_links as _cx_links
_EFFECT_PATTERNS += _cx_links.EFFECT_PATTERNS
from .. import cx_events as _cx_events
_TRIGGERS += _cx_events.TRIGGERS
_TRIGGERS += _cx_links.TRIGGERS
from .. import cx_statics as _cx_statics
_EFFECT_PATTERNS += _cx_statics.EFFECT_PATTERNS
