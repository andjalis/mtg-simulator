"""Library and hand effects of batch2_templates."""
from ..state import Permanent, Player
from . import kind
from ... import counter_mechanics


@kind("tuck_perm")
def tuck_perm(game, p, eff, target, **_):
    """Put a permanent on top of (or one card below the top of) its owner's library; a token just leaves."""
    if not (isinstance(target, Permanent) and game.leave_battlefield(target, "graveyard")) or target.front.is_token:
        return
    owner = target.owner
    if target.front in owner.graveyard:
        owner.graveyard.remove(target.front)
        owner.library.insert(max(0, len(owner.library) - eff.data.get("depth", 0)), target.front)
        game.log(f"{target.card.name} goes into its owner's library", p)


def _gy_to_library(who):
    for c in list(who.graveyard):
        who.graveyard.remove(c)
        who.library.append(c)


@kind("shuffle_gy")
def shuffle_gy(game, p, target, **_):
    who = target if isinstance(target, Player) else p
    _gy_to_library(who)
    who.library.shuffle(game.rng)
    game.log(f"{who} shuffles their graveyard into their library", p)


@kind("wheel_all")
def wheel_all(game, p, eff, opp, **_):
    for who in (p, opp):
        for c in list(who.hand):
            if eff.data.get("shuffle_gy"):
                who.hand.remove(c)
                who.library.append(c)
            else:
                game.discard_card(who, c)
        if eff.data.get("shuffle_gy"):
            _gy_to_library(who)
            who.library.shuffle(game.rng)
        game.draw(who, eff.amount)


@kind("lose_half")
def lose_half(game, p, eff, target, cause, **_):
    who = target if isinstance(target, Player) else game.opponent(p)
    half = (who.life + (1 if eff.data.get("up") else 0)) // 2
    if half > 0:
        game.change_life(who, -half, cause)


@kind("poison")
def poison(game, p, eff, target, opp, **_):
    who = [p, opp] if eff.target == "each_player" else [target if isinstance(target, Player) else opp]
    for pl in who:
        pl.counters["poison"] = pl.counters.get("poison", 0) + eff.amount
        game.log(f"gets {eff.amount} poison counter(s)", pl)


@kind("destroy_group")
def destroy_group(game, p, eff, opp, **_):
    """Destroy all permanents of a type minus an excluded one (nonartifact creatures) or of a land subtype."""
    sources = counter_mechanics.death_sources(game)
    d = eff.data
    for perm in [x for x in p.battlefield + opp.battlefield
                 if (not d.get("types") or d["types"] in x.card.types) and (not d.get("not") or d["not"] not in x.card.types)
                 and (not d.get("sub") or d["sub"] in x.card.subtypes)]:
        game.destroy(perm, counter_sources=sources)


@kind("discard_hand")
def discard_hand(game, p, **_):
    for c in list(p.hand):
        game.discard_card(p, c)
