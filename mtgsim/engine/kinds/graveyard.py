"""Graveyard: returning, reanimating and exiling cards from graveyards."""
from __future__ import annotations

import dataclasses

from ... import cast_triggers, returns
from ...cards import CardDef, Effect
from ...identity import Graveyard
from ..state import TrackedZone
from . import NO_SBA, kind


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
    game.gy_move(p, eff, item)


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
    if eff.amount:                  # "exile up to four target cards from a single graveyard": the opponent's best
        for card in sorted(opp.graveyard, key=lambda c: -c.cmc)[:eff.amount]:
            opp.graveyard.remove(card)
            opp.exile.append(card)
    else:
        for card in list(opp.graveyard):
            game.move_card(card, opp.graveyard, opp.exile, reason="exile_graveyard")


@kind("last_gift")
def last_gift(game, p, item, **_):
    src = item.source if item else None
    before = {pl.name: [c for c in pl.graveyard if c.is_creature] for pl in game.players}
    for pl in game.players:
        for c in [x for x in pl.creatures if x is not src]:
            game.sacrifice(c)
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


@kind("rebound_cast")
def rebound_cast(game, p, item, **_):
    card, version = item.context
    if not isinstance(p.exile, TrackedZone) or p.exile.version(card) != version:
        return NO_SBA
    if not any(c is card for c in p.exile) or not game.hook(p, "choose_rebound")(game, p, card):
        return NO_SBA
    cast_triggers.cast_exiled(game, p, card, "rebound")
