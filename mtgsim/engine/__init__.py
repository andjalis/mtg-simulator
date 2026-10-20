"""A simplified two-player Magic rules engine.

Covered: lands and mana (mana creatures, Sol Ring-style sources, Treasure),
the stack with priority passing, instant-speed play (counterspells, removal and
flash permanents on the opponent's turn), triggered abilities (enters, attacks,
dies, combat damage to a player, "whenever you cast", "whenever you draw",
upkeep, end step, landfall, ward, prowess), modal spells, sagas, planeswalkers
(loyalty abilities, attacking and burning them), tokens (creatures, Treasure,
Clue, Blood), +1/+1 counters, transforming cards, adventures, flashback,
foretell, spectacle, blitz, channel, manlands and vehicles, combat with
flying/reach/haste/vigilance/defender/menace/trample/first strike/double strike/
deathtouch/lifelink, hexproof, indestructible, the London mulligan, decking, and
the seven-card hand limit.

Priority windows: after anything is put on the stack, and with an empty stack in
the declare attackers, declare blockers and end steps. Decisions the heuristic
AI doesn't make are taken by the default policies in engine/policy.py;
an AI can override each one by defining the hook of the same name (see README).

Modules: state (objects), mana (payment), game (the Game class) and its mixins
costs, targets, turns, stack, play, abilities, battlefield, resolve, effects and combat; policy (default decisions).
"""
from __future__ import annotations

import dataclasses
import itertools
import json
import random
import re

from .. import auras, cast_triggers, copies, counting, graveyard, learning, milling, proliferate, regeneration, removal, returns, search, xspells
from ..cards import BASIC_MANA, COLORS, KEYWORDS, Activated, AltCost, CardDef, Effect, Trigger, add_mana, jace_token, make_token, role_token
from .. import modal, rules_events, continuous
from ..identity import CardInstance, CardZone, Graveyard, instance
from ..actions import atomic_action, perform, can_perform

from .state import (
    TrackedZone, TEAM_KEYWORDS, COLOR_WORDS, TARGETED, Permanent, FIREBEND_MANA, _POOL_MANA, _gy_desc, pool_mana,
    OUTLAWS, PROTECTION, Player, StackItem, can_block, protected_from, is_basic_land, _TYPE_WORDS, card_matches,
)
from .mana import _mana_of, find_payment, _find_payment, payable, add_costs
from .policy import (
    perm_value, _threat, default_choose_target, choose_basic, choose_earthbend, play_extra_lands, choose_tutor,
    choose_color, choose_target, _mode_value, default_choose_modes, _targets_for, _removal, respond, _option_value,
    respond_extras, _self_pump, ability_worth, choose_equip_target, equip_all, choose_ability, combat_pump,
    _wants_land, scry, choose_dig, pay_unless, pay_optional, pay_shock, choose_discard_from, choose_rummage,
    saddle_creatures, choose_crew, _reserve, before_attacks, choose_attack_targets, default_loyalty_choice,
    use_abilities, default_sneak, DEFAULTS, default_respond, default_scry, default_dig,
)
from .game import Game
from .costs import CostsMixin
from .targets import TargetsMixin
from .turns import TurnsMixin
from .stack import StackMixin
from .play import PlayMixin
from .abilities import AbilitiesMixin
from .battlefield import BattlefieldMixin
from .resolve import ResolveMixin
from .effects import EffectsMixin
from .combat import CombatMixin
