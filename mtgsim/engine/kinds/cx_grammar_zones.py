"""Kinds for the grammar's zone-change verbs (see mtgsim.cx_grammar_zones)."""
from ..policy import perm_value
from ..state import Permanent, Player
from . import kind


@kind("cx_edict")
def edict(game, p, eff, target, item, **_):
    """"<player> sacrifices N <noun phrase>": that player chooses (the least valuable first) among the permanents
    they control that match, fixed before any is sacrificed."""
    if not isinstance(target, Player):
        return
    from ... import counter_mechanics
    from ...cx_grammar import group_members
    source = item.source if item is not None else None
    pool = group_members(game, target, {"group": eff.data["noun"]}, source, target)
    pool = [x for x in pool if not (eff.data.get("other") and x is source)]
    victims = sorted(pool, key=lambda x: (not x.card.is_token, perm_value(x)))[:eff.amount]
    sources = counter_mechanics.death_sources(game)
    for v in victims:
        if isinstance(v, Permanent) and v in target.battlefield:
            game.log(f"sacrifices {v.card.name}", target)
            game.sacrifice(v, counter_sources=sources)


@kind("cx_tuck")
def tuck(game, p, eff, target, **_):
    """Put a permanent on top of / on the bottom of / shuffled into its owner's library, never through the
    graveyard (Game.put_in_library); a token ceases to exist."""
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        name = target.card.name
        if game.put_in_library(target, eff.data["where"]):
            game.log(f"{name} goes into its owner's library ({eff.data['where']})", p)


@kind("cx_card_move")
def card_move(game, p, eff, target, item=None, **_):
    """Move a targeted card out of a graveyard: to its owner's hand, exile or library (top / bottom), or onto the
    battlefield under your control or its owner's."""
    from ...referent import remember_card
    remember_card(item, None)
    owner = next((pl for pl in game.players if any(c is target for c in pl.graveyard)), None)
    if owner is None:
        return
    remember_card(item, target)
    to = eff.data["to"]
    if to == "battlefield":
        owner.graveyard.remove(target)
        controller = p if eff.data.get("under", "you") == "you" else owner
        attacking = (eff.data.get("attacking", False) and controller is game.active and
                     game.step in ("declare_attackers", "declare_blockers", "first_strike_damage", "combat_damage",
                                   "end_combat"))
        game.enter_battlefield(controller, target, tapped=bool(eff.data.get("tapped")), tapped_attacking=attacking)
    elif to in ("library_top", "library_bottom"):
        owner.graveyard.remove(target)
        if to == "library_top":
            owner.library.append(target)
        else:
            owner.library.insert(0, target)
    else:
        game.move_card(target, owner.graveyard, owner.hand if to == "hand" else owner.exile, reason="cx_card_move")
    game.log(f"{target.name} goes from {owner}'s graveyard to {to}", p)


@kind("cx_card_choose")
def card_choose(game, p, eff, target, item=None, **_):
    """Choose a bounded number of cards at resolution, without adding spell targets."""
    import dataclasses
    from ...backlog_templates import entry_batch
    from ...cx_grammar_zones import card_fits
    if not isinstance(target, Player):
        return
    source = item.source if item is not None else None
    pool = [c for c in target.graveyard if card_fits(c, eff.data["cx_card"], source)]
    chosen = []
    for card in game.hook(target, "choose_dig")(game, target, list(pool), eff.amount):
        if any(card is c for c in pool) and not any(card is c for c in chosen):
            chosen.append(card)
    if not eff.data["up_to"]:
        chosen += [c for c in pool if not any(c is x for x in chosen)]
    move = dataclasses.replace(eff, kind="cx_card_move")
    with entry_batch(game):
        for card in chosen[:eff.amount]:
            if any(card is c for c in target.graveyard):
                card_move(game, p, move, card, item)
