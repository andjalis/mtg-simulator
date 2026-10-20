"""Alternative and additional ways to cast a card.

    Buyback {3}             (pay it on top of the mana cost: the spell returns to your hand as it resolves)
    Surge {1}{R}            (its surge cost once you've cast another spell this turn)
    Prototype {2}{R} — 3/2  (cast for that cost as a smaller creature)
    Suspend 4—{1}{G}        (exile it with four time counters; remove one each upkeep; cast it free when the last
                             is removed, and a creature cast this way has haste)
    Entwine {2}             (pay it on top of the mana cost to choose all the modes)
    Disturb {1}{W}          (cast it transformed from the graveyard; exiled if it would go to a graveyard)

``parse_line`` reads the keyword lines into AltCosts. Game.spell_options offers buyback, surge and prototype
as variants of the hand card; suspending is a main-phase action (``suspend``, chosen in policy.default_actions),
and ``upkeep`` ticks the suspended cards. A prototype keeps its colors.
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"(Disturb) ((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost("disturb", parse_mana_cost(m[2]), zone="graveyard"))
        return True
    m = re.fullmatch(r"(Buyback|Surge|Entwine) ((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2])))
        return True
    m = re.fullmatch(r"Prototype ((?:\{[^}]+\})+) — (\d+)/(\d+)", line)
    if m:
        st.alt_costs.append(AltCost("prototype", parse_mana_cost(m[1]), pt=(int(m[2]), int(m[3]))))
        return True
    m = re.fullmatch(r"Suspend (\d+)—((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost("suspend", parse_mana_cost(m[2]), counters=int(m[1])))
        return True
    return False


def variants(game, p, card) -> list:
    """The spell_options variants of a hand card for these costs."""
    from .cards import AltCost, add_mana
    out = []
    for a in card.alt_costs:
        if a.kind == "buyback":
            out.append(game._variant(card, "buyback", AltCost("buyback", add_mana(card.mana_cost, a.cost))))
        elif a.kind == "surge" and game.spells_cast_turn(p) >= 1:
            out.append(game._variant(card, "surge", a))
        elif a.kind == "prototype":
            out.append(game._variant(card, "prototype", a))
        elif a.kind == "entwine" and card.modes:      # Game.cast chooses all the modes of this variant
            out.append(game._variant(card, "entwine", AltCost("entwine", add_mana(card.mana_cost, a.cost))))
    return out


def entered(perm, kind, alt):
    """A prototype enters with its smaller power and toughness; a suspended creature has haste."""
    import dataclasses
    if kind == "prototype" and alt is not None:
        perm.card = dataclasses.replace(perm.card, power=alt.pt[0], toughness=alt.pt[1], mana_cost=dict(alt.cost),
                                        cmc=sum(alt.cost.values()))
    elif kind == "suspended" and perm.is_creature:
        perm.perm_kw.add("haste")
    elif kind == "disturb":
        perm.disturbed = True


def suspend(game, p, card) -> bool:
    """Pay the suspend cost and exile the card with its time counters."""
    alt = next((a for a in card.alt_costs if a.kind == "suspend"), None)
    if card not in p.hand or alt is None or game.pay(p, alt.cost) is None:
        return False
    p.hand.remove(card)
    p.exile.append(card)
    p.suspended.append([card, alt.counters])
    game.log(f"suspends {card.name} ({alt.counters} time counters)", p)
    return True


def upkeep(game, p):
    """Remove a time counter from each suspended card; cast the ones that lost their last one, without paying."""
    from .cards import AltCost
    ready = []
    for entry in p.suspended:
        entry[1] -= 1
        if entry[1] <= 0:
            ready.append(entry)
    for entry in ready:
        p.suspended.remove(entry)
        card = entry[0]
        if card in p.exile:
            game.log(f"casts suspended {card.name}", p)
            game.cast(p, game._variant(card, "suspended", AltCost("suspended", {"generic": 0})))


def worth_suspending(game, p, card) -> bool:
    """Suspend a card the AI can't cast for a while (its mana value is at least two more than its lands) or at all."""
    alt = next((a for a in card.alt_costs if a.kind == "suspend"), None)
    lands = sum(x.card.is_land for x in p.battlefield)
    no_cost = not any(card.mana_cost.values())         # Ancestral Vision: suspend is the only way to cast it
    return alt is not None and (no_cost or card.cmc >= lands + 2) and game.can_pay(p, alt.cost)
