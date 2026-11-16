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
from .. import cx_combat_costs as _cx_combat_costs
_EFFECT_PATTERNS += _cx_combat_costs.EFFECT_PATTERNS
_SUBS += _cx_combat_costs.SUBS
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
from .. import cx_trig_events as _cx_trig_events
_TRIGGERS += _cx_trig_events.TRIGGERS

from .. import prevent_templates as _prevent_templates
_EFFECT_PATTERNS += _prevent_templates.EFFECT_PATTERNS
_SUBS += _prevent_templates.SUBS
from .. import prevent_next_templates as _prevent_next_templates
_EFFECT_PATTERNS += _prevent_next_templates.EFFECT_PATTERNS
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
from .. import cx_flash_perm as _cx_flash_perm
_EFFECT_PATTERNS += _cx_flash_perm.EFFECT_PATTERNS
from .. import cx_links as _cx_links
_EFFECT_PATTERNS += _cx_links.EFFECT_PATTERNS
from .. import cx_events as _cx_events
_TRIGGERS += _cx_events.TRIGGERS
_TRIGGERS += _cx_links.TRIGGERS
from .. import cx_statics as _cx_statics
_EFFECT_PATTERNS += _cx_statics.EFFECT_PATTERNS
from .. import cx_effects as _cx_effects
_EFFECT_PATTERNS += _cx_effects.EFFECT_PATTERNS
_SUBS += _cx_effects.SUBS
from .. import cx_mech as _cx_mech
_EFFECT_PATTERNS += _cx_mech.EFFECT_PATTERNS
_SUBS += _cx_mech.SUBS

from .. import cx_ability_effects as _cx_ability_effects
_EFFECT_PATTERNS += _cx_ability_effects.EFFECT_PATTERNS
from .. import cx_abil_damage as _cx_abil_damage
_EFFECT_PATTERNS += _cx_abil_damage.EFFECT_PATTERNS
from .. import cx_abil_mana as _cx_abil_mana
_EFFECT_PATTERNS += _cx_abil_mana.EFFECT_PATTERNS
from .. import cx_grammar_addmana as _cx_grammar_addmana
_EFFECT_PATTERNS += _cx_grammar_addmana.EFFECT_PATTERNS
_SUBS += _cx_grammar_addmana.SUBS
from .. import cx_lures as _cx_lures
_EFFECT_PATTERNS += _cx_lures.EFFECT_PATTERNS
from .. import cx_recolor as _cx_recolor
_EFFECT_PATTERNS += _cx_recolor.EFFECT_PATTERNS
from .. import cx_shields as _cx_shields
_EFFECT_PATTERNS += _cx_shields.EFFECT_PATTERNS
_SUBS += _cx_shields.SUBS
from .. import cx_mixed as _cx_mixed
_EFFECT_PATTERNS += _cx_mixed.EFFECT_PATTERNS
_SUBS += _cx_mixed.SUBS
from .. import cx_night_suspect as _cx_night_suspect
_EFFECT_PATTERNS += _cx_night_suspect.EFFECT_PATTERNS
from .. import cx_suspect as _cx_suspect
_EFFECT_PATTERNS += _cx_suspect.EFFECT_PATTERNS
from .. import cx_night_redirect as _cx_night_redirect
_EFFECT_PATTERNS += _cx_night_redirect.EFFECT_PATTERNS
from .. import cx_night_lair as _cx_night_lair
_EFFECT_PATTERNS += _cx_night_lair.EFFECT_PATTERNS
from .. import cx_night_draw as _cx_night_draw
_EFFECT_PATTERNS += _cx_night_draw.EFFECT_PATTERNS
from .. import cx_night_dead as _cx_night_dead
_EFFECT_PATTERNS += _cx_night_dead.EFFECT_PATTERNS
from .. import cx_night_flip as _cx_night_flip
_EFFECT_PATTERNS += _cx_night_flip.EFFECT_PATTERNS
from .. import cx_night_lifemv as _cx_night_lifemv
_EFFECT_PATTERNS += _cx_night_lifemv.EFFECT_PATTERNS
from .. import cx_night_endturn as _cx_night_endturn
_EFFECT_PATTERNS += _cx_night_endturn.EFFECT_PATTERNS
from .. import cx_night_counter as _cx_night_counter
_EFFECT_PATTERNS += _cx_night_counter.EFFECT_PATTERNS
from .. import cx_night_combat as _cx_night_combat
_EFFECT_PATTERNS += _cx_night_combat.EFFECT_PATTERNS
from .. import cx_night_loot as _cx_night_loot
_SUBS += _cx_night_loot.SUBS
_EFFECT_PATTERNS += _cx_night_loot.EFFECT_PATTERNS
from .. import cx_night_edict as _cx_night_edict
_SUBS += _cx_night_edict.SUBS
_EFFECT_PATTERNS += _cx_night_edict.EFFECT_PATTERNS
from .. import cx_night_misc as _cx_night_misc
_EFFECT_PATTERNS += _cx_night_misc.EFFECT_PATTERNS
_SUBS += _cx_night_endturn.SUBS
from .. import cx_tokens as _cx_tokens
_EFFECT_PATTERNS += _cx_tokens.EFFECT_PATTERNS
from . import parse as _parse_module
_parse_module._FACE_LINE_PARSERS = (_chance_templates.face_line, _cx_tokens.face_line) + _parse_module._FACE_LINE_PARSERS
from .. import cx_counters as _cx_counters
_EFFECT_PATTERNS += _cx_counters.EFFECT_PATTERNS
_SUBS += _cx_counters.SUBS
from .. import referent as _referent
_EFFECT_PATTERNS += _referent.EFFECT_PATTERNS
_SUBS += _referent.SUBS
from .. import blink as _blink
_EFFECT_PATTERNS += _blink.EFFECT_PATTERNS
_SUBS += _blink.SUBS
from .. import that_spell as _that_spell
_EFFECT_PATTERNS += _that_spell.EFFECT_PATTERNS
_SUBS += _that_spell.SUBS
from .. import conjure as _conjure_templates
_EFFECT_PATTERNS += _conjure_templates.EFFECT_PATTERNS
from .. import cx_grammar_counters as _cx_grammar_counters
_EFFECT_PATTERNS += _cx_grammar_counters.EFFECT_PATTERNS
from .. import hand_put as _hand_put
_EFFECT_PATTERNS += _hand_put.EFFECT_PATTERNS
_SUBS += _hand_put.SUBS
from .. import cx_exchange as _cx_exchange
_EFFECT_PATTERNS += _cx_exchange.EFFECT_PATTERNS
from .. import cx_trigger_grants as _cx_trigger_grants
_SUBS += _cx_trigger_grants.SUBS
from .. import search_counted as _search_counted
_EFFECT_PATTERNS += _search_counted.EFFECT_PATTERNS
_SUBS += _search_counted.SUBS
from .. import time_counters as _time_counters
_EFFECT_PATTERNS += _time_counters.EFFECT_PATTERNS
_SUBS += _time_counters.SUBS
from .. import capped_counters as _capped_counters
_EFFECT_PATTERNS += _capped_counters.EFFECT_PATTERNS
_SUBS += _capped_counters.SUBS
from .. import card_referent as _card_referent
_EFFECT_PATTERNS += _card_referent.EFFECT_PATTERNS
from .. import cx_attach as _cx_attach
_EFFECT_PATTERNS += _cx_attach.EFFECT_PATTERNS
_EFFECT_PATTERNS += _that_much.LATE_PATTERNS  # "~ deals that much damage to <any recipient>" (#626)
from .. import cx_replace_amounts as _cx_replace_amounts       # counter-amount replacements (#407)
_parse_module._FACE_LINE_PARSERS = (_cx_replace_amounts.face_line,) + _parse_module._FACE_LINE_PARSERS
from .. import cx_static_cost as _cx_static_cost  # one-shot spell-group discounts (#341)
_EFFECT_PATTERNS += _cx_static_cost.EFFECT_PATTERNS
from .. import this_way as _this_way  # noqa: E402  "<effect> for each <thing> <verb> this way" (#642)
_EFFECT_PATTERNS += _this_way.EFFECT_PATTERNS
from .. import cx_exile_play as _cx_exile_play          # "exile the top card of that player's library" (#316)
_EFFECT_PATTERNS += _cx_exile_play.EFFECT_PATTERNS
_SUBS += _cx_exile_play.SUBS
from .. import linked_exile as _linked_exile  # noqa: E402
_EFFECT_PATTERNS += _linked_exile.EFFECT_PATTERNS
from .. import cx_trig_turn as _cx_trig_turn  # noqa: E402
_EFFECT_PATTERNS += _cx_trig_turn.EFFECT_PATTERNS
from .. import cx_spent as _cx_spent  # noqa: E402
_SUBS += _cx_spent.SUBS
from .. import named_tokens as _named_tokens  # noqa: E402
_EFFECT_PATTERNS += _named_tokens.EFFECT_PATTERNS
from .. import library_peek as _library_peek  # noqa: E402
_EFFECT_PATTERNS += _library_peek.EFFECT_PATTERNS
_SUBS += _library_peek.SUBS
from .. import cx_ifpos as _cx_ifpos  # noqa: E402
_SUBS += _cx_ifpos.SUBS
from .. import damage_reorder as _damage_reorder  # noqa: E402
_SUBS += _damage_reorder.SUBS
_EFFECT_PATTERNS += _damage_reorder.EFFECT_PATTERNS
from .. import chance_each as _chance_each  # noqa: E402
_SUBS += _chance_each.SUBS
_EFFECT_PATTERNS += _chance_each.EFFECT_PATTERNS
from .. import protection_types as _protection_types  # noqa: E402
KEYWORDS.update(_protection_types.KEYWORDS)
from .. import bounce_own as _bounce_own  # noqa: E402
_EFFECT_PATTERNS += _bounce_own.EFFECT_PATTERNS
from .. import zone_exile as _zone_exile  # noqa: E402
_EFFECT_PATTERNS += _zone_exile.EFFECT_PATTERNS
from .. import give_control as _give_control  # noqa: E402
_EFFECT_PATTERNS += _give_control.EFFECT_PATTERNS
from .. import life_total as _life_total  # noqa: E402
_EFFECT_PATTERNS += _life_total.EFFECT_PATTERNS
from .. import free_cast as _free_cast  # noqa: E402  "cast a spell from your hand without paying its mana cost" (#625)
_EFFECT_PATTERNS += _free_cast.EFFECT_PATTERNS
from .. import cx_dmg_equal as _cx_dmg_equal  # noqa: E402  damage equal to a quantity (#626)
_EFFECT_PATTERNS += _cx_dmg_equal.EFFECT_PATTERNS
from .. import cx_owner_library as _cx_owner_library  # noqa: E402  "put it on top of its owner's library" (#628)
_EFFECT_PATTERNS += _cx_owner_library.EFFECT_PATTERNS
from .. import spell_grants as _spell_grants  # noqa: E402  "the next spell you cast this turn has cascade" (#633)
_EFFECT_PATTERNS += _spell_grants.EFFECT_PATTERNS
from .. import until_nonland as _until_nonland  # noqa: E402  "exile until a nonland card, you may cast it" (#625)
_EFFECT_PATTERNS += _until_nonland.EFFECT_PATTERNS
_SUBS += _until_nonland.SUBS
from .. import emblems as _emblems  # noqa: E402  emblems with a triggered ability (#839)
_EFFECT_PATTERNS += _emblems.EFFECT_PATTERNS
_SUBS += _emblems.SUBS
from .. import another_target as _another_target  # noqa: E402  "another target creature you control" (#809)
_SUBS += _another_target.SUBS
