"""#646: cumulative upkeep with costs other than plain mana or life (CR 702.24).

    Cumulative upkeep {G} or {W}                                   ("or", ({"G": 1}, {"W": 1}))
    Cumulative upkeep—Sacrifice a land. / Sacrifice a creature.    ("sac", "land" | "creature")
    Cumulative upkeep—Discard a card.                              ("discard", 1)
    Cumulative upkeep—Put a -1/-1 counter on this creature.        ("self_m1", 1)
    Cumulative upkeep—Put a +1/+1 counter on a creature an opponent controls.   ("opp_p1", 1)
    Cumulative upkeep—An opponent gains 1 life.                    ("opp_life", 1)
    Cumulative upkeep—Put two cards from a single graveyard on the bottom of their owner's library.  ("gy_bottom", 2)

CR 702.24a: at the beginning of your upkeep put an age counter on it, then you may pay [cost] once for each age counter
on it; if you don't, sacrifice it. The whole payment is made or none of it (a cost can't be paid in part, CR 601.2h /
118.3), and a choice in the cost is made separately for each age counter (CR 702.24b: "{G} or {W}" may be paid with any
mix; each "two cards from a single graveyard" may use a different graveyard). The upkeep itself runs in
batch1_templates.cumulative_upkeep (age counter, then ``pay`` here for these kinds); the pay-or-sacrifice choice is
the controller's (the default AI below keeps paying while the price stays small).
"""
from __future__ import annotations

import re

_ONE = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}


def parse_line(line: str, st) -> bool:
    from .cards.model import parse_mana_cost
    s = line.strip()
    cost = None
    m = re.fullmatch(r"Cumulative upkeep (\{[WUBRG]\}) or (\{[WUBRG]\})", s)
    if m and m[1] != m[2]:
        cost = ("or", (parse_mana_cost(m[1]), parse_mana_cost(m[2])))
    m = re.fullmatch(r"Cumulative upkeep—(.+)\.", s)
    body = m[1] if m else ""
    if (k := re.fullmatch(r"Sacrifice an? (land|creature)", body)):
        cost = ("sac", k[1])
    elif body == "Discard a card":
        cost = ("discard", 1)
    elif re.fullmatch(r"Put a -1/-1 counter on (?:this creature|~)", body):
        cost = ("self_m1", 1)
    elif body == "Put a +1/+1 counter on a creature an opponent controls":
        cost = ("opp_p1", 1)
    elif (k := re.fullmatch(r"An opponent gains (one|two|three|\d+) life", body)):
        cost = ("opp_life", _ONE.get(k[1]) or int(k[1]))
    elif body == "Put two cards from a single graveyard on the bottom of their owner's library":
        cost = ("gy_bottom", 2)
    if cost is None:
        return False
    st.extra.setdefault("advanced_rules", {})["cumulative_upkeep"] = cost
    return True


def _or_payment(game, p, pair, age):
    """The mix of the two colours (one per age counter) that can be paid, preferring the colour we have more of."""
    for k in range(age, -1, -1):
        for first, second in (pair, pair[::-1]):
            total = {"generic": 0}
            for c, n in first.items():
                total[c] = total.get(c, 0) + n * k
            for c, n in second.items():
                total[c] = total.get(c, 0) + n * (age - k)
            if game.can_pay(p, total):
                return total
    return None


def pay(game, p, perm, kind, data, age) -> bool:
    """Pay the cost age times (True), or decline (False: the caller sacrifices perm). The default AI's rules: it pays
    while the total stays small and the payment is worth less than keeping perm."""
    from .engine.policy import perm_value
    keep = perm_value(perm)
    opp = game.opponent(p)
    if kind == "or":
        total = _or_payment(game, p, data, age) if age <= 3 else None
        return total is not None and game.pay(p, total) is not None
    if kind == "sac":
        pool = [x for x in p.battlefield if x is not perm and
                (x.card.is_land if data == "land" else x.is_creature)]
        if len(pool) < age:
            return False
        victims = sorted(pool, key=perm_value)[:age]
        lands = sum(x.card.is_land for x in p.battlefield)
        if data == "land" and lands - age < 4 or data == "creature" and sum(map(perm_value, victims)) >= keep:
            return False
        for v in victims:
            game.log(f"sacrifices {v.card.name} for cumulative upkeep", p)
            game.sacrifice(v)
        return True
    if kind == "discard":
        if len(p.hand) < age or age > 2:
            return False
        hand, picks = list(p.hand), []
        try:                            # choose every card first: the cost is paid in full or not at all
            for _ in range(age):
                card = p.ai.choose_discard(game, p)
                if card not in p.hand:
                    return False
                picks.append(card)
                p.hand.remove(card)
        finally:
            p.hand[:] = hand
        for card in picks:
            game.discard_card(p, card)
            game.log(f"discards {card.name} for cumulative upkeep", p)
        return True
    if kind == "self_m1":
        if perm.toughness - age <= 0:
            return False                # it would die anyway: sacrificing it is the same for us
        perm.counters["-1/-1"] = perm.counters.get("-1/-1", 0) + age
        game.log(f"puts {age} -1/-1 counter(s) on {perm.card.name}", p)
        return True
    if kind == "opp_p1":
        theirs = opp.creatures
        if not theirs:
            return False                # no creature an opponent controls: the cost can't be paid (CR 118.3)
        if age > 3:
            return False
        for _ in range(age):            # each counter: the creature that gains least from it
            pick = min(theirs, key=lambda x: (x.has("flying") or x.has("trample"), x.power, perm_value(x)))
            pick.counters["+1/+1"] = pick.counters.get("+1/+1", 0) + 1
            game.log(f"puts a +1/+1 counter on {pick.card.name}", p)
        return True
    if kind == "opp_life":
        if data * age > 4:
            return False
        game.change_life(opp, data * age, f"{perm.card.name}: cumulative upkeep")
        return True
    if kind == "gy_bottom":
        picks = []
        piles = {id(pl): list(pl.graveyard) for pl in game.players}
        for _ in range(age):            # each payment: two cards from one graveyard, the opponent's first
            pl = next((x for x in (opp, p) if len(piles[id(x)]) >= data), None)
            if pl is None:
                return False
            pile = sorted(piles[id(pl)], key=lambda c: -(c.cmc + (3 if c.is_creature else 0)))
            chosen, piles[id(pl)] = pile[:data], pile[data:]
            picks.append((pl, chosen))
        for pl, chosen in picks:
            for c in chosen:
                pl.graveyard.remove(c)
                pl.library.insert(0, c)
            game.log(f"puts {[c.name for c in chosen]} on the bottom of {pl}'s library", p)
        return True
    return False
