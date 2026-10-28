"""Edicts on a chosen player, life from a destroyed creature's stats, peeking, and the monarch."""
from ..policy import perm_value
from ..state import Permanent, can_block
from . import kind
from ... import counter_mechanics


def _edict(game, p, victim_owner):
    victims = sorted(victim_owner.creatures, key=perm_value)[:1]
    sources = counter_mechanics.death_sources(game)
    for v in victims:
        game.sacrifice(v, counter_sources=sources)


@kind("edict_player")
def edict_player(game, p, target, opp, **_):
    _edict(game, p, target if target is not None and not isinstance(target, Permanent) else opp)


@kind("edict_each")
def edict_each(game, p, opp, **_):
    for pl in (p, opp):
        _edict(game, p, pl)


@kind("gain_prev_stat")
def gain_prev_stat(game, p, eff, prev, cause, **_):
    if isinstance(prev, Permanent):
        value = prev.power if eff.data["stat"] == "power" else prev.toughness
        game.change_life(p, max(0, value), cause)


@kind("powerstone")
def powerstone(game, p, eff, **_):
    from ...batch1_templates import powerstone as make
    for _ in range(eff.amount):
        game.enter_battlefield(p, make(), tapped=bool(eff.data.get("tapped")))
    game.log(f"creates {eff.amount} Powerstone", p)


@kind("provoke")
def provoke(game, p, item, opp, **_):
    """Untap the defender's creature that can block the source and is worth least; it must block if able."""
    src = item.source if item is not None else None
    if not isinstance(src, Permanent):
        return
    able = [c for c in opp.creatures if can_block(c, src)]
    if not able:
        able = [c for c in opp.creatures if c.tapped and not c.has("cant_block_now")]
    if able:
        pick = min(able, key=perm_value)
        pick.tapped = False
        game.__dict__.setdefault("provoked", {})[pick] = src
        game.log(f"{pick.card.name} must block {src.card.name}", p)


@kind("peek_hand")
def peek_hand(game, p, target, opp, **_):
    game.log(f"looks at {target or opp}'s hand", p)


@kind("become_monarch")
def become_monarch(game, p, **_):
    game.monarch = p
    game.log("becomes the monarch", p)
