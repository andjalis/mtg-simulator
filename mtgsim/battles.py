"""Battles (#254): defense counters, protectors, attacking battles and Siege defeat.

Scope: two-player Sieges. A Siege enters with defense counters equal to its printed defense and its
caster's opponent as protector (``Permanent.protector``). A player may attack a battle they don't protect,
including one they control; the protector is then the defending player and blocks for it. Damage to a
battle removes defense counters. When the last defense counter of a Siege is removed (by damage or any
counter removal) its controller gets a defeat trigger: exile it, then they may cast it transformed without
paying its mana cost. A battle with no defense counters that isn't the source of a pending trigger is put
into its owner's graveyard (704.5v). Other battle types (Control Points) keep their defense counters but are
reported as unsupported by the parser.
"""
from __future__ import annotations

from .cards import Effect


def is_siege(perm) -> bool:
    return perm.is_battle and "Siege" in perm.card.subtypes


def defender_of(attacked):
    """The defending player for an attacked object: a player itself, a planeswalker's controller, a battle's
    protector."""
    from .engine.state import Permanent
    if isinstance(attacked, Permanent):
        if attacked.is_battle:
            return getattr(attacked, "protector", None)
        return attacked.controller
    return attacked


def defending_player(game, item):
    """The player the relevant attacker (the item's source, else its event context) is attacking, through
    defender_of; None when the item names no attacker (#297)."""
    from .engine.state import Permanent
    attacks = getattr(game, "attack_targets", None) or {}
    for creature in (getattr(item, "source", None), getattr(item, "context", None)):
        if isinstance(creature, Permanent) and creature in attacks:
            defender = defender_of(attacks[creature])
            if defender in game.players:
                return defender
    return None


def on_battlefield(perm) -> bool:
    return perm in perm.controller.battlefield


def can_attack(game, p, obj) -> bool:
    """Whether p's creatures may attack obj: the opponent, a planeswalker they control, or a battle on the
    battlefield protected by someone other than p (p's own Siege is protected by the opponent)."""
    from .engine.state import Permanent
    opp = game.opponent(p)
    if obj is opp:
        return True
    if not isinstance(obj, Permanent) or not on_battlefield(obj):
        return False
    if obj.is_battle:
        protector = getattr(obj, "protector", None)
        return protector in game.players and protector is not p
    return obj.is_planeswalker and obj.controller is opp


def attackable(game, p) -> list:
    """The battles p may attack now."""
    return [x for pl in game.players for x in pl.battlefield if x.is_battle and can_attack(game, p, x)]


def entered(game, perm):
    """A battle enters with its defense counters; a Siege's controller chooses an opponent to protect it."""
    if perm.card.defense:
        perm.counters["defense"] = perm.card.defense
    if is_siege(perm):
        perm.protector = game.opponent(perm.controller)


def defense_removed(perm, old: int, new: int):
    """Counters hook: the last defense counter of a Siege on the battlefield was removed."""
    if not (old > 0 >= new) or not is_siege(perm) or not on_battlefield(perm) or perm.abilities_suppressed:
        return
    game = getattr(perm.controller, "_game", None)
    if game is None:
        return
    game.queue_trigger(perm.controller, [Effect("siege_defeat")], perm, f"{perm.card.name}: defeated")


def _trigger_pending(game, perm) -> bool:
    """Whether perm is the source of an ability that has triggered but not yet left the stack."""
    if any(entry[2] is perm for entry in game.pending):
        return True
    return any(getattr(item, "source", None) is perm and not item.is_spell for item in game.stack)


def sba(game, perm) -> bool:
    """704.5v and 704.5x for one battle; True when it left the battlefield."""
    if not perm.is_battle:
        return False
    if is_siege(perm):
        protector = getattr(perm, "protector", None)
        if protector not in game.players or protector is perm.controller:
            perm.protector = game.opponent(perm.controller)
    if perm.counters.get("defense", 0) <= 0 and not _trigger_pending(game, perm):
        game.log(f"{perm.card.name} has no defense counters", perm.controller)
        game.leave_battlefield(perm, "graveyard")
        return True
    return False


def defeat(game, p, item):
    """The defeat trigger resolves: exile the Siege, then p may cast it transformed without paying its mana
    cost. A card that can't be cast (or a declined cast) stays in exile."""
    perm = item.source if item is not None else None
    if perm is None or not on_battlefield(perm):
        return
    card = perm.front
    game.log(f"{perm.card.name} is defeated", p)
    game.leave_battlefield(perm, "exile")
    if card is None or card.back is None or card not in p.exile:
        return                          # a token, or an exiled card p doesn't own: stays in exile
    from .cards import AltCost
    variant = game._variant(card, "siege", AltCost("siege", {"generic": 0}))
    if not game.cast(p, variant):
        game.log(f"{card.name} stays in exile", p)


def attack_targets(game, me, attackers: list, out: dict) -> dict:
    """AI: send attackers no untapped opposing creature can block at a battle they would defeat together;
    otherwise leave them on the opponent."""
    from .engine.state import can_block
    opp = game.opponent(me)
    blockers = [b for b in opp.creatures if not b.tapped]
    free = [a for a in attackers if a not in out and a.power > 0
            and not any(can_block(b, a) for b in blockers)]
    for battle in sorted(attackable(game, me), key=lambda x: x.counters.get("defense", 0)):
        need = battle.counters.get("defense", 0)
        chosen, total = [], 0
        for a in sorted(free, key=lambda a: -a.power):
            if total >= need:
                break
            chosen.append(a)
            total += a.power
        if need > 0 and total >= need:
            for a in chosen:
                out[a] = battle
                free.remove(a)
    return out
