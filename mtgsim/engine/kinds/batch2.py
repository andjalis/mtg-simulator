"""Library and hand effects of batch2_templates."""
from ..policy import perm_value
from ..state import Permanent, Player
from . import kind
from ... import copies, counter_mechanics


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
    who = p if eff.data.get("self") else target if isinstance(target, Player) else game.opponent(p)
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
                 and (not d.get("sub") or d["sub"] in x.card.subtypes) and (not d.get("tapped") or x.tapped)]:
        game.destroy(perm, counter_sources=sources)


@kind("discard_hand")
def discard_hand(game, p, **_):
    for c in list(p.hand):
        game.discard_card(p, c)


@kind("discard_redraw")
def discard_redraw(game, p, **_):
    """"Discard all the cards in your hand, then draw that many cards" (Decaying Time Loop)."""
    n = len(p.hand)
    for c in list(p.hand):
        game.discard_card(p, c)
    game.draw(p, n)


@kind("discard_random_target")
def discard_random_target(game, p, eff, target, opp, **_):
    who = target if isinstance(target, Player) else opp
    if who.hand:
        card = game.rng.choice(list(who.hand))
        game.discard_card(who, card)
        game.log(f"discards {card.name} at random", who)


@kind("sac_at_end")
def sac_at_end(game, p, prev, item, **_):
    """Sacrifice the permanent made or targeted earlier in this ability at the next end step."""
    if isinstance(prev, Permanent):
        from ...cards import Effect
        game.delayed_end_step.append((p, [Effect("sac_now")], item.source if item is not None else None, prev))


@kind("sac_now")
def sac_now(game, item, **_):
    perm = item.context if item is not None else None
    if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
        game.sacrifice(perm)


@kind("haunt_attach")
def haunt_attach(game, p, item, **_):
    """Haunt: the dead creature is exiled from the graveyard, haunting a creature."""
    from ...batch2_templates import haunt_card
    perm = item.source if item is not None else None
    if isinstance(perm, Permanent):
        haunt_card(game, perm.owner, perm.front)


@kind("group_remove")
def group_remove(game, p, eff, item, cause, **_):
    from ...permanent_templates import matches
    source = item.source if item else None
    victims = [x for pl in game.players for x in pl.battlefield if matches(game, x, eff.data["selector"], p, source)]
    op = eff.data["op"]
    sources = counter_mechanics.death_sources(game) if op == "destroy" else None
    src = (item.source if item.source is not None else item.card) if item is not None else None
    for perm in victims:
        if perm not in perm.controller.battlefield:
            continue
        if op == "destroy":
            game.destroy(perm, counter_sources=sources, no_regen=eff.data.get("no_regen", False))
        elif op == "damage":
            game.deal_damage(perm, eff.amount, by=p, cause=cause, source=src)
        else:
            game.leave_battlefield(perm, "exile" if op == "exile" else "hand")


@kind("conspire")
def conspire(game, p, item, **_):
    """Conspire: tap two untapped creatures that share a colour with the spell, and copy it."""
    spell = item.context if item is not None else None
    if spell is None or spell not in game.stack or spell.card is None:
        return
    colors = spell.card.colors
    pool = sorted((c for c in p.creatures if not c.tapped and colors & c.card.colors), key=perm_value)
    if len(pool) < 2 or not any(e.kind != "conspire" for e in spell.effects):
        return
    for c in pool[:2]:
        c.tapped = True
    game.log(f"conspires {spell.card.name}", p)
    copies.copy_spell(game, p, spell)


@kind("hideaway")
def hideaway(game, p, eff, item, **_):
    """Look at the top N, exile one face down (the costliest spell, else a land), the rest go to the bottom."""
    src = item.source if item is not None else None
    top = [p.library.pop() for _ in range(min(eff.amount, len(p.library)))]
    if not top or not isinstance(src, Permanent):
        for c in top:
            p.library.insert(0, c)
        return
    pick = max(top, key=lambda c: (not c.is_land, c.cmc))
    top.remove(pick)
    p.exile.append(pick)
    src.hidden = pick
    for c in top:
        p.library.insert(0, c)
    game.log("hides a card away", p)


@kind("hideaway_play")
def hideaway_play(game, p, eff, item, **_):
    from ...batch1_templates import hideaway_holds
    src = item.source if item is not None else None
    card = getattr(src, "hidden", None)
    if card is None or card not in p.exile or not hideaway_holds(game, p, eff.data["cond"]):
        return
    src.hidden = None
    if card.is_land:
        game.play_land(p, card)
    else:
        game.cast_free(p, card)


@kind("hideaway_return")
def hideaway_return(game, p, item, **_):
    src = item.source if item is not None else None
    card = getattr(src, "hidden", None)
    if card is not None and card in p.exile:
        game.move_card(card, p.exile, p.hand, reason="hideaway-return")
