"""Edicts on a chosen player, life from a destroyed creature's stats, peeking, and the monarch."""
from ..policy import perm_value
from ..state import Permanent, Player, can_block
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
        value = {"power": lambda: prev.power, "toughness": lambda: prev.toughness,
                 "mana value": lambda: prev.card.cmc}[eff.data["stat"]]()
        game.change_life(p, max(0, value), cause)


@kind("powerstone")
def powerstone(game, p, eff, **_):
    from ...batch1_templates import powerstone as make
    for _ in range(eff.amount):
        game.enter_battlefield(p, make(), tapped=bool(eff.data.get("tapped")))
    game.log(f"creates {eff.amount} Powerstone", p)


@kind("incubate")
def incubate(game, p, eff, **_):
    from ...batch1_templates import incubator
    token = game.enter_battlefield(p, incubator())
    token.counters["+1/+1"] = eff.amount
    game.log(f"incubates {eff.amount}", p)


@kind("incubator_transform")
def incubator_transform(game, p, item, **_):
    import dataclasses
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in p.battlefield and "Incubator" in src.card.subtypes:
        src.card = dataclasses.replace(src.card, name="Phyrexian token", types=frozenset({"Artifact", "Creature"}),
                                       subtypes=frozenset({"Phyrexian"}), power=0, toughness=0, activated=[])
        game.log("incubator transforms into a Phyrexian", p)


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


@kind("sac_land_each")
def sac_land_each(game, p, opp, **_):
    for pl in (p, opp):
        lands = [x for x in pl.battlefield if x.card.is_land]
        if lands:
            game.sacrifice(min(lands, key=perm_value))


@kind("discard_random_that")
def discard_random_that(game, p, target, **_):
    if isinstance(target, Player) and target.hand:
        card = game.rng.choice(list(target.hand))
        game.discard_card(target, card)
        game.log(f"discards {card.name} at random", target)


@kind("damage_group")
def damage_group(game, p, eff, opp, cause, item, **_):
    src = item.source if item is not None else None
    victims = game.attackers if eff.data["group"] == "attacking" else opp.creatures
    for c in list(victims):
        game.deal_damage(c, eff.amount, by=p, cause=cause, source=src)


@kind("host_lose", "host_damage", "host_shrink")
def host_effects(game, p, eff, item, cause, **_):
    host = item.context if item is not None else None
    if not isinstance(host, Permanent) or host not in host.controller.battlefield:
        return
    if eff.kind == "host_lose":
        game.change_life(host.controller, -eff.amount, cause)
    elif eff.kind == "host_damage":
        game.deal_damage(host.controller, eff.amount, by=p, cause=cause, source=item.source)
    else:
        host.counters["-1/-1"] = host.m1 + 1


@kind("exploit")
def exploit(game, p, item, **_):
    """You may sacrifice a creature (a token or a cheap one) when the exploiter enters."""
    src = item.source if item is not None else None
    if not isinstance(src, Permanent):
        return
    pool = [c for c in p.creatures if perm_value(c) <= 2.5 or c is src and src.card.token_kind]
    token_first = sorted((c for c in pool), key=lambda c: (not c.card.is_token, perm_value(c)))
    victim = next((c for c in token_first if c is not src), None)
    if victim is None:
        return
    nontoken = not victim.card.is_token
    game.log(f"exploits {victim.card.name}", p)
    game.sacrifice(victim)
    if src in p.battlefield:
        game.fire(p, "exploit_self", src)
    game.fire(p, "exploit_any")
    if nontoken:
        game.fire(p, "exploit_any_nontoken")


@kind("peek_hand")
def peek_hand(game, p, target, opp, **_):
    game.log(f"looks at {target or opp}'s hand", p)


@kind("become_monarch")
def become_monarch(game, p, **_):
    game.monarch = p
    game.log("becomes the monarch", p)
