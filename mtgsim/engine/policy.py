"""Default decision policies.

Decisions the heuristic AI doesn't make are taken by these functions; an AI can
override each one by defining the hook of the same name (see README and DEFAULTS)."""
from __future__ import annotations

import dataclasses
import re

from typing import TYPE_CHECKING
from .. import alt_casts, transmute, copies, learning, proliferate, regeneration, removal, costs
from ..cards import COLORS, CardDef, Effect
from .. import modal
from .mana import add_costs, payable
from .state import Permanent, StackItem, TARGETED, _gy_desc, is_basic_land, protected_from

if TYPE_CHECKING:
    from .game import Game
    from .state import Player


def perm_value(x: Permanent) -> float:
    if x.is_planeswalker and not x.is_creature:
        return 4 + x.loyalty
    if x.card.token_kind:
        return 0.5
    return x.card.cmc + (x.power + x.toughness) / 2 + 0.5 * len(x.card.keywords)


_ANY_PLAYER = re.compile(r"any player may activate", re.I)
_ANY_PLAYER_WINDOW = re.compile(r"any player may activate this ability but only "
                                r"(during their turn|during any upkeep step|during their draw step|as a sorcery)", re.I)
_ANY_PLAYER_WINDOWS = {"during their turn": "their_turn", "during any upkeep step": "upkeep",
                       "during their draw step": "draw_step", "as a sorcery": "sorcery"}


def any_player_ability(act) -> bool:
    """Whether any player, not just the controller, may activate this ability
    ("Any player may activate this ability."). ``Activated.any_player`` is the parsed flag
    when the parser records one; the text fallback keeps hand-built abilities working."""
    return bool(getattr(act, "any_player", False) or _ANY_PLAYER.search(act.text or ""))


def any_player_window(act) -> str:
    """The timing restriction of "Any player may activate this ability but only ...":
    "their_turn" (their own turn), "upkeep" (any upkeep step), "draw_step" (their draw
    step), "sorcery", or "" when there is none."""
    m = _ANY_PLAYER_WINDOW.search(act.text or "")
    return _ANY_PLAYER_WINDOWS.get(m[1].lower(), "") if m else ""


def _threat(game: Game, me: Player, item: StackItem) -> float:
    """How much I want to counter an opponent's stack item."""
    score = item.card.cmc if item.card else 0
    for eff, tgt in zip(item.effects, item.targets):
        if tgt is me or (isinstance(tgt, Permanent) and tgt.controller is me):
            score += 2
        if isinstance(tgt, StackItem) and tgt.controller is me:
            score += 2 + (tgt.card.cmc if tgt.card else 0)
        if eff.kind == "damage" and tgt is me and eff.amount >= me.life:
            score += 100
        if eff.kind == "wrath" and me.creatures:
            score += 2 * len(me.creatures)
    if item.card and (item.card.is_creature or item.card.is_planeswalker):
        score += ((item.card.power or 0) + (item.card.toughness or 0)) / 4 + item.card.loyalty / 2
    return score


def default_choose_target(game: Game, me: Player, eff: Effect):
    """A reasonable target for eff, respecting hexproof and targeting restrictions."""
    opp = game.opponent(me)
    legal = game.legal_targets(me, eff)
    theirs = [x for x in legal if isinstance(x, Permanent) and x.controller is opp]
    mine = [x for x in legal if isinstance(x, Permanent) and x.controller is me]
    k = eff.kind
    if eff.target == "player" and k in ("draw", "gain_life"):
        return me if me in legal else None      # "target player draws/gains": the beneficiary is the caster
    if k == 'linked_exile':
        enemies = [x for x in legal if isinstance(x, Permanent) and x.controller is opp]
        if enemies:
            return max(enemies, key=perm_value)
        cards = [x for x in legal if isinstance(x, CardDef)]
        return max(cards, key=lambda c: c.cmc, default=None)
    if k == "damage":
        from ..cx_abil_damage import scaled
        eff = scaled(game, me, eff)
        if eff.target == "player" and not (eff.data.get("or_pw") and eff.amount < opp.life):
            return opp
        if eff.target == "any" and eff.amount >= opp.life:
            return opp
        killable = [x for x in theirs if (x.is_creature and eff.target != "player" and x.toughness - x.damage <= eff.amount and
                                          not x.has("indestructible")) or (x.is_planeswalker and not x.is_creature
                                                                           and x.loyalty <= eff.amount)]
        if killable:
            return max(killable, key=perm_value)
        return opp if eff.target in ("any", "player") else None
    if k in removal.KINDS:
        return removal.choose(game, me, eff)
    if k in ('graveyard_exile_all', 'graveyard_exile_choice'):
        return opp
    if k == 'adapt_exception':
        return max(mine, key=perm_value, default=None)
    if k in ('control_permanent', 'opponent_exile'):
        return max(theirs, key=perm_value, default=None) if k == 'control_permanent' else opp
    if k in ('grave_library_top', 'return_tribal_grave'):
        return max(legal, key=lambda c: c.cmc, default=None)
    if k == 'allocated_counter':
        return max(mine, key=perm_value, default=None)
    if k == 'advanced_quantity_stats':
        return max(theirs if eff.data['power'].startswith('-') else mine, key=perm_value, default=None)
    if k == 'source_control':
        return max(theirs, key=perm_value, default=None)
    if k == 'untap_prev':
        return max((x for x in mine if x.tapped), key=perm_value, default=None)
    if k == 'animate_land':     # one of my lands that isn't a creature yet, untapped first
        return min((x for x in mine if not x.is_creature), key=lambda x: (x.tapped, perm_value(x)), default=None)
    if k == 'move_counter_self':
        source = getattr(game.target_source, 'source', game.target_source)
        return max((x for x in mine if x is not source and x.p1), key=lambda x: (x.p1, perm_value(x)), default=None)
    if k == 'grant_combat_destroy':
        return max(mine, key=perm_value, default=None)
    if k == 'exile_permanent':
        return max(theirs, key=perm_value, default=None)
    if k == 'grant_triggers':
        return max(mine, key=perm_value, default=None)
    if k == 'modify_counters':
        pool = theirs if eff.data['operation'] == 'remove' else mine
        if eff.data.get('counter') == '-1/-1':
            pool = mine if eff.data['operation'] == 'remove' else theirs
        return max(pool, key=perm_value, default=None)
    if k == 'add_counter':
        pool = theirs if eff.data.get('counter') == '-1/-1' else mine
        return max(pool, key=perm_value, default=None)
    if k == 'return_grave_target':
        return max(legal, key=lambda c: c.cmc, default=None)
    if k == 'quantity_stats':
        return max(theirs if eff.data['power'].startswith('-') else mine, key=perm_value, default=None)
    if k == 'grant_activated':
        return max(mine, key=perm_value, default=None)
    if k == 'blink_next_end':
        return max(mine, key=perm_value, default=None)
    if k == 'relationship_mark':
        if eff.data.get('relationship') == 'counter':
            return max((x for x in mine if x.p1 > 0), key=lambda x: x.p1, default=None)
        pool = [x for x in legal if x.card.aura] if eff.data.get('relationship') == 'aura' else [x for x in legal if x.auras]
        return max(pool, key=perm_value, default=None)
    if k in ('transfer_between', 'move_aura', 'move_auras'):
        return max(mine or legal, key=perm_value, default=None)
    if k == 'player_action_lock':
        return opp
    if k == "mill":
        return opp
    if k == "tap":
        theirs = [x for x in theirs if not x.tapped]
        return max(theirs, key=perm_value, default=None)
    if k == "shrink":
        return max(theirs, key=perm_value, default=None)
    if k in ("destroy", "debuff_one", "bounce"):
        if k == "debuff_one":
            theirs = [x for x in theirs if x.toughness <= eff.amount2]
        theirs = [x for x in theirs if not (k == "destroy" and x.has("indestructible"))]
        return max(theirs, key=perm_value, default=None)
    if k in ("pump", "p1_counters", "double_power", "grant", "explore", "attach_self", "force_blocked", "inherit_counters"):
        return max(mine, key=perm_value, default=None)
    if k == "oring":
        return max(theirs, key=perm_value, default=None)
    if k in ("stun", "shuffle_away", "cant_block_turn", "force_block"):
        return max(theirs, key=perm_value, default=None)
    if k == "unblockable":
        ready = [x for x in mine if x.can_attack() and x.power > 0]
        return max(ready, key=lambda x: x.power, default=None)
    if k in ("counter", "bounce_spell"):
        return next((i for i in reversed(game.stack) if i in legal), None)
    if k in ("discard", "discard_choice", "hand_exile"):
        return opp if opp.hand else None
    if k in ("connive", "attach_new_equipment"):    # the best creature of ours that can be chosen
        return max((x for x in mine if x.is_creature), key=perm_value, default=None)
    side = eff.data.get("side") if eff.data else None
    if side == "auto":                  # neutral effects (a colour change) take the side of what follows them
        from ..cx_grammar import auto_side
        side = auto_side(game, eff)
    if eff.target == "graveyard_card" and side in ("mine", "theirs", "any"):   # cx_grammar_zones: whose graveyard
        pool = [c for c in legal if side == "any" or any(c is x for x in (me if side == "mine" else opp).graveyard)]
        return max(pool, key=lambda c: c.cmc, default=None)
