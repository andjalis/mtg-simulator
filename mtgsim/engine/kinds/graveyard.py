"""Graveyard: returning, reanimating and exiling cards from graveyards."""
from __future__ import annotations

import dataclasses
import re

from ... import cast_triggers, returns, counter_mechanics
from ...cards import CardDef, Effect
from ...identity import Graveyard
from ..state import Permanent, Player, TrackedZone, card_matches
from . import NO_SBA, kind


@kind("dig_gy")
def dig_gy(game, p, eff, **_):
    """"Look at/reveal the top N: some go to your hand (or back on top), the rest into your graveyard."""
    n = eff.amount
    cards = list(reversed(p.library[-min(n, len(p.library)):])) if n else []
    keep, rest = [], list(cards)
    if eff.data.get("types"):    # "a creature card and/or an enchantment card": one of each type
        for t in eff.data["types"]:
            allowed = [c for c in cards if not any(c is x for x in keep) and card_matches(c, f"a {t} card")]
            if allowed:
                keep.append(max(allowed, key=lambda c: c.cmc))
    elif eff.data.get("to_top"):     # the best card goes back on top, the rest into the graveyard
        if cards:
            rest.remove(max(cards, key=lambda c: c.cmc))
    else:
        desc = eff.data.get("filter")
        allowed = [c for c in cards if card_matches(c, _filter_desc(desc))] if desc else cards
        if eff.data.get("any"):
            keep = allowed
        else:
            keep = [c for c in game.hook(p, "choose_dig")(game, p, list(allowed), eff.amount2)
                    if any(c is x for x in cards)][:eff.amount2]
    for c in keep:
        rest.remove(c)
        game.move_card(c, p.library, p.hand, reason="dig")
    for c in rest:
        game.move_card(c, p.library, p.graveyard, reason="dig")
    if keep or rest:
        game.log(f"digs {n}, keeps {len(keep)}, mills {len(rest)}", p)


def _filter_desc(desc: str) -> str:
    """A search description card_matches understands: commas become alternatives."""
    return "a " + re.sub(r",?\s+or\s+", " or a ", desc.replace(", ", " or "))


@kind("fof")
def fof(game, p, eff, item, **_):
    """Fact or Fiction: an opponent splits the top N into two piles; you keep the better half."""
    from ...ai import card_value
    n = eff.amount + (getattr(item, "x", 0) if eff.data.get("x_plus") and item is not None else 0)
    cards = list(reversed(p.library[-min(n, len(p.library)):]))
    keep = sorted(cards, key=card_value, reverse=True)[:max(1, (n + 1) // 2)] if cards else []
    rest = list(cards)
    for c in keep:
        rest.remove(c)
        game.move_card(c, p.library, p.hand, reason="fact-or-fiction")
    for c in rest:
        game.move_card(c, p.library, p.graveyard, reason="fact-or-fiction")
    game.log(f"keeps {len(keep)} of the top {n}, mills {len(rest)}", p)


@kind("process_payoff")
def process_payoff(game, p, eff, item, opp, **_):
    """Process: put a card an opponent owns from exile into their graveyard; if one is there,
    run the "If you do, <payoff>" effects."""
    src = item.source if item is not None else None
    if opp.exile:
        card = max(opp.exile, key=lambda c: c.cmc)
        game.move_card(card, opp.exile, opp.graveyard, reason="process")
        game.log(f"puts {card.name} from exile into {opp}'s graveyard", p)
        game.queue_trigger(p, eff.data["effects"], src, "payoff", context=getattr(item, "context", None))


@kind("exile_self_payoff")
def exile_self_payoff(game, p, eff, item, **_):
    """A dies trigger's "you may exile it. If you do, <payoff>": exile the dead card, then queue the payoff."""
    src = item.source if item is not None else None
    card = src.front if isinstance(src, Permanent) else (item.context if item is not None else None)
    owner = src.owner if isinstance(src, Permanent) else p
    if card is not None and any(card is c for c in owner.graveyard):
        game.move_card(card, owner.graveyard, owner.exile, reason="exile")
        game.log(f"exiles {card.name} from the graveyard", p)
        game.queue_trigger(p, eff.data["effects"], src, "payoff", context=getattr(item, "context", None))


@kind("exile_hand_perm")
def exile_hand_perm(game, p, eff, target, **_):
    """Reveal a player's hand, you choose a card, exile it for good (Night Terrors,
    Castigate, Appetite for Brains)."""
    from .cards import _HAND_FILTERS, _hand_matches
    if isinstance(target, Player) and target.hand:
        if eff.filter in _HAND_FILTERS and not eff.data.get("mv"):
            legal = [c for c in target.hand if _HAND_FILTERS[eff.filter](c)]
        else:
            legal = [c for c in target.hand if _hand_matches(c, eff)]
        if legal:
            card = max(legal, key=lambda c: c.cmc)
            game.move_card(card, target.hand, target.exile, reason="exile")
            game.log(f"exiles {card.name} from {target}'s hand", p)


@kind("exiled_returned")
def exiled_returned(game, **_):
    """"When ~ leaves the battlefield, return the exiled card ...": the exile effect that took
    the card (exiled_cards / exiled_to_hand on the source) already returned it."""
    return NO_SBA


@kind("reanimate_temp")
def reanimate_temp(game, p, eff, item, **_):
    """Return a creature card from a graveyard ... it gains haste, exiled at the next end
    step (Goryo's Vengeance, Dawn of the Dead); data["zone"] ("any" / "opp") widens the
    source graveyard to anyone's or an opponent's (Gruesome Encore)."""
    if eff.data.get("zone") in ("any", "opp"):
        owners = [p, game.opponent(p)] if eff.data["zone"] == "any" else [game.opponent(p)]
        pairs = [(o, c) for o in owners for c in o.graveyard if c.is_creature]
        if not pairs:
            return
        owner, card = max(pairs, key=lambda oc: oc[1].cmc)
        owner.graveyard.remove(card)
        game.log(f"returns {card.name} to the battlefield", p)
        perm = game.enter_battlefield(p, card)
        if perm is not None:
            game.resolve(p, Effect("grant", data={"keyword": "haste"}), perm, item)
            game.delayed_end_step.append((p, [Effect("exile_at_end")],
                                          item.source if item is not None else None, perm))
        return
    if eff.data.get("top"):
        cands = [c for c in reversed(list(p.graveyard)) if c.is_creature][:1]
    else:
        cands = [c for c in p.graveyard if c.is_creature and not (eff.data.get("legendary") and not c.legendary)]
        if eff.data.get("x") and item is not None:
            cands = [c for c in cands if c.cmc <= (getattr(item, "x", 0) or 0)]
    if not cands:
        return
    card = cands[0] if eff.data.get("top") else max(cands, key=lambda c: c.cmc)
    p.graveyard.remove(card)
    game.log(f"returns {card.name} to the battlefield", p)
    perm = game.enter_battlefield(p, card)
    if perm is not None:
        game.resolve(p, Effect("grant", data={"keyword": "haste"}), perm, item)
        game.delayed_end_step.append((p, [Effect("exile_at_end")], item.source if item is not None else None, perm))


@kind("exile_at_end")
def exile_at_end(game, item, **_):
    perm = item.context if item is not None else None
    if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
        game.leave_battlefield(perm, "exile")


@kind("regrow")
def regrow(game, p, eff, **_):
    for _ in range(max(1, eff.amount)):
        cands = [c for c in p.graveyard if c.is_creature]
        if not cands:
            break
        card = max(cands, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        p.hand.append(card)
        game.log(f"returns {card.name} to hand", p)


@kind("recruit")
def recruit(game, p, **_):
    game.draw(p)
    if p.hand:
        card = p.ai.choose_discard(game, p)
        game.discard_card(p, card)
        game.log(f"recruits, discarding {card.name}", p)
        if not card.is_land:
            game.create_token(p, Effect("token", 1, data={"name": "Human Soldier", "power": 1,
                                                          "toughness": 1, "keywords": frozenset()}))


@kind("reanimate_snow")
def reanimate_snow(game, p, item, **_):
    x = item.snow_spent if item else 0
    cands = [c for c in p.graveyard if (c.is_creature or c.is_planeswalker) and c.cmc <= x]
    if cands:
        card = max(cands, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        game.log(f"returns {card.name} to the battlefield", p)
        game.enter_battlefield(p, card)


@kind("gy_hate")
def gy_hate(game, p, eff, opp, cause, **_):
    creatures = [c for c in opp.graveyard if c.is_creature]
    if creatures:
        card = max(creatures, key=lambda c: c.cmc)
        opp.graveyard.remove(card)
        opp.exile.append(card)
        game.change_life(opp, -eff.amount, cause)
        game.change_life(p, eff.amount, cause)
    elif opp.graveyard:
        card = max(opp.graveyard, key=lambda c: c.is_instant or c.is_sorcery)
        opp.graveyard.remove(card)
        opp.exile.append(card)


@kind("return_as_enchantment")
def return_as_enchantment(game, p, item, **_):
    card = item.source.front if item and item.source else None
    if card is not None and card in p.graveyard:
        p.graveyard.remove(card)
        ench = dataclasses.replace(card, types=card.types - {"Creature"}, power=None, toughness=None)
        game.enter_battlefield(p, ench, physical_card=card)
        game.log(f"returns {card.name} as an enchantment", p)


@kind("tutor_gy")
def tutor_gy(game, p, **_):
    if p.library:
        card = max(p.library, key=lambda c: (c.is_creature, c.cmc))
        p.library.remove(card)
        p.graveyard.append(card)
        p.library.shuffle(game.rng)
        game.log(f"puts {card.name} from library into graveyard", p)


@kind("reanimate_total")
def reanimate_total(game, p, eff, **_):
    budget, count = eff.amount, 0
    for card in sorted((c for c in p.graveyard if c.is_creature), key=lambda c: -c.cmc):
        if count < 2 and card.cmc <= budget:
            p.graveyard.remove(card)
            budget -= card.cmc
            count += 1
            game.enter_battlefield(p, card)
            game.log(f"returns {card.name} to the battlefield", p)


@kind("reanimate_one")
def reanimate_one(game, p, eff, item, **_):
    cands = [c for c in p.graveyard if c.is_creature]
    if cands:
        card = max(cands, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        game.enter_battlefield(p, card, counters=returns.entry_counters(eff, item))
        game.log(f"reanimates {card.name}", p)


@kind("regrow_perm")
def regrow_perm(game, p, **_):
    cands = [c for c in p.graveyard if c.is_permanent]
    if cands:
        card = max(cands, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        p.hand.append(card)
        game.log(f"returns {card.name} to hand", p)


@kind("gy_move")
def gy_move(game, p, eff, item, **_):
    """Return cards from a graveyard; with data["haste"] the returned permanents gain haste."""
    if not eff.data.get("haste"):
        game.gy_move(p, eff, item)
        return
    before = {id(x) for x in p.battlefield}
    game.gy_move(p, eff, item)
    for perm in p.battlefield:
        if id(perm) not in before:
            game.resolve(p, Effect("grant", data={"keyword": "haste"}), perm, item)


@kind("grant_flashback")
def grant_flashback(game, p, **_):
    cands = [c for c in p.graveyard if (c.is_instant or c.is_sorcery) and c.alt_costs is not None]
    if cands:
        best = max(cands, key=lambda c: c.cmc)
        p.granted_fb.append(best)
        game.log(f"{best.name} gains flashback", p)


@kind("regrow_any")
def regrow_any(game, p, **_):
    if p.graveyard:
        card = max(p.graveyard, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        p.hand.append(card)


@kind("exile_gy")
def exile_gy(game, eff, opp, **_):
    if eff.amount:
        if opp.graveyard:
            card = max(opp.graveyard, key=lambda c: c.cmc)
            opp.graveyard.remove(card)
            opp.exile.append(card)
    else:
        for card in list(opp.graveyard):
            game.move_card(card, opp.graveyard, opp.exile, reason="exile_graveyard")


@kind("last_gift")
def last_gift(game, p, item, **_):
    src = item.source if item else None
    before = {pl.name: [c for c in pl.graveyard if c.is_creature] for pl in game.players}
    sources = counter_mechanics.death_sources(game)
    for pl in game.players:
        for c in [x for x in pl.creatures if x is not src]:
            game.sacrifice(c, counter_sources=sources)
    for pl in game.players:
        for card in before[pl.name]:
            if card in pl.graveyard:
                pl.graveyard.remove(card)
                game.enter_battlefield(pl, card)
        game.log(f"{pl} returns {len(before[pl.name])} creatures", p)


@kind("exile_gy_cards")
def exile_gy_cards(game, p, eff, opp, **_):
    pool = [(c, pl) for pl in (opp, p) for c in pl.graveyard]
    pool.sort(key=lambda t: (t[1] is p, -(t[0].cmc + (3 if t[0].is_creature else 0))))
    first_owner = pool[0][1] if pool else None
    for c, pl in [t for t in pool if t[1] is first_owner][:eff.amount]:
        pl.graveyard.remove(c)
        pl.exile.append(c)
        game.log(f"exiles {c.name} from {pl}'s graveyard", p)


@kind("gy_bottom")
def gy_bottom(game, p, eff, opp, **_):
    pl = p if eff.data.get("mine") else opp
    if pl.graveyard:
        c = max(pl.graveyard, key=lambda x: x.cmc + (3 if x.is_creature else 0))
        pl.graveyard.remove(c)
        pl.library.insert(0, c)
        game.log(f"puts {c.name} on the bottom of {pl}'s library", p)


@kind("return_self_gy")
def return_self_gy(game, p, eff, item, **_):
    card = item.context if item is not None else None
    if item is not None and item.context_ref is not None:
        card = item.context_ref.find(p.graveyard)
    if isinstance(card, CardDef) and card in p.graveyard:
        p.graveyard.remove(card)
        game.log(f"returns {card.name} from the graveyard", p)
        if eff.data.get("to") == "hand":
            p.hand.append(card)
            return
        game.enter_battlefield(p, card, tapped=eff.data.get("tapped", False),
                               counters=returns.entry_counters(eff, item))


@kind("undying_return", "persist_return")
def undying_return(game, item, k, **_):
    owner, card, version = item.context
    grave = owner.graveyard
    index = next((i for i, c in enumerate(grave) if c is card), None)
    if index is not None and isinstance(grave, Graveyard) and grave.version(card) == version:
        del grave[index]
        game.enter_battlefield(owner, card, counters={"-1/-1" if k == "persist_return" else "+1/+1": 1})


@kind("shuffle_self")
def shuffle_self(game, p, eff, item, **_):
    """"Shuffle ~ into its owner's library" (the Beacon and Zenith spells): mark the
    resolving spell so Game.to_graveyard_after_resolving puts it into its owner's
    library, shuffled, instead of the graveyard (the stack hook reads item.shuffle_self)."""
    if item is not None and item.is_spell:
        item.shuffle_self = True


@kind("rebound_cast")
def rebound_cast(game, p, item, **_):
    card, version = item.context
    if not isinstance(p.exile, TrackedZone) or p.exile.version(card) != version:
        return NO_SBA
    if not any(c is card for c in p.exile) or not game.hook(p, "choose_rebound")(game, p, card):
        return NO_SBA
    cast_triggers.cast_exiled(game, p, card, "rebound")
