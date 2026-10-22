"""Alternative and additional ways to cast a card.

    Buyback {3}             (pay it on top of the mana cost: the spell returns to your hand as it resolves)
    Surge {1}{R}            (its surge cost once you've cast another spell this turn)
    Prototype {2}{R} — 3/2  (cast for that cost as a smaller creature)
    Suspend 4—{1}{G}        (exile it with four time counters; remove one each upkeep; cast it free when the last
                             is removed, and a creature cast this way has haste)
    Entwine {2}             (pay it on top of the mana cost to choose all the modes)
    Disturb {1}{W}          (cast it transformed from the graveyard; exiled if it would go to a graveyard)
    Jump-start              (cast it from the graveyard, discarding a card as well; then exile it)
    Replicate {1}{R}        (pay it any number of times on top of the mana cost: a copy for each)
    Dredge 2                (instead of a draw, mill two cards and return this card from the graveyard to your hand)
    Escape—{R}{R}, Exile N other cards from your graveyard.     ~ escapes with a +1/+1 counter on it.
    Embalm {3}{W}{W} / Eternalize {5}{G}{G} / Scavenge {1}{B}{G}   (sorcery-speed graveyard actions: a token
                             copy that's a white Zombie / a 4/4 black Zombie; +1/+1 counters equal to its power)

``parse_line`` reads the keyword lines into AltCosts. Game.spell_options offers buyback, surge and prototype
as variants of the hand card; suspending is a main-phase action (``suspend``, chosen in policy.default_actions),
and ``upkeep`` ticks the suspended cards. A prototype keeps its colors. The AI escapes, embalms, eternalizes and
scavenges whenever it can pay for it after its other plays (``graveyard_actions``). Replicate is offered paid one
to three times. The AI dredges its most expensive dredge card instead of a draw while its library has at least
ten cards more than the dredge amount.
"""
from __future__ import annotations

import re


_N = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    if line == "Jump-start":
        st.alt_costs.append(AltCost("jump_start", {}, zone="graveyard"))
        return True
    m = re.fullmatch(r"Escape—((?:\{[^}]+\})+), Exile (\w+) other cards from your graveyard\.", line)
    if m and m[2] in _N:
        st.alt_costs.append(AltCost("escape", parse_mana_cost(m[1]), zone="graveyard", counters=_N[m[2]]))
        return True
    m = re.fullmatch(r"~ escapes with (a|one|two|three|four|five) \+1/\+1 counters? on it\.", line)
    if m:
        st.extra["escape_counters"] = _N[m[1]]
        return True
    m = re.fullmatch(r"(Embalm|Eternalize|Scavenge) ((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2]), zone="graveyard"))
        return True
    m = re.fullmatch(r"(Disturb) ((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost("disturb", parse_mana_cost(m[2]), zone="graveyard"))
        return True
    m = re.fullmatch(r"Dredge (\d+)", line)
    if m:
        st.extra["dredge"] = int(m[1])
        return True
    m = re.fullmatch(r"(Buyback|Surge|Entwine|Replicate) ((?:\{[^}]+\})+)", line)
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
        elif a.kind == "replicate":
            for k in (1, 2, 3):
                extra = {c: n * k for c, n in a.cost.items()}
                out.append(game._variant(card, f"replicate_{k}", AltCost(f"replicate_{k}", add_mana(card.mana_cost, extra))))
        elif a.kind == "entwine" and card.modes:      # Game.cast chooses all the modes of this variant
            out.append(game._variant(card, "entwine", AltCost("entwine", add_mana(card.mana_cost, a.cost))))
    return out


def graveyard_variants(game, p, card) -> list:
    """Jump-start and escape casts of a graveyard card."""
    from .cards import AltCost
    out = []
    for a in card.alt_costs:
        if a.kind == "jump_start" and len(p.hand) > 0:
            v = game._variant(card, "jump_start", AltCost("jump_start", dict(card.mana_cost)))
            v.extra_discard = 1
            out.append(v)
        elif a.kind == "escape" and sum(c is not card for c in p.graveyard) >= a.counters:
            out.append(game._variant(card, "escape", a))
    return out


def pay_escape(game, p, card, alt):
    """Exile the N other graveyard cards an escape cost asks for (the least valuable ones)."""
    others = sorted((c for c in p.graveyard if c is not card), key=lambda c: (c.is_land is False, c.cmc))
    for c in others[:alt.counters]:
        game.move_card(c, p.graveyard, p.exile, reason="escape")


def graveyard_actions(game, p):
    """Embalm, eternalize and scavenge what can be paid for (sorcery speed, after the other plays)."""
    import dataclasses
    from .engine import perm_value
    for card in list(p.graveyard):
        for a in card.alt_costs:
            if a.kind not in ("embalm", "eternalize", "scavenge") or card not in p.graveyard:
                continue
            if a.kind == "scavenge" and not p.creatures:
                continue
            if not game.can_pay(p, a.cost) or game.pay(p, a.cost) is None:
                continue
            game.move_card(card, p.graveyard, p.exile, reason=a.kind)
            if a.kind == "scavenge":
                host = max(p.creatures, key=perm_value)
                host.counters["+1/+1"] = host.p1 + (card.power or 0)
                game.log(f"scavenges {card.name} onto {host.card.name}", p)
                continue
            black = a.kind == "eternalize"
            token = dataclasses.replace(card, name=f"{card.name} token", mana_cost={"generic": 0}, cmc=0, hybrid=(),
                                        is_token=True, alt_costs=[], color_override=frozenset("B" if black else "W"),
                                        subtypes=frozenset(card.subtypes) | {"Zombie"},
                                        power=4 if black else card.power, toughness=4 if black else card.toughness)
            game.log(f"{a.kind}s {card.name}", p)
            game.enter_battlefield(p, token)


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
    elif kind == "escape":
        perm.escaped = True
        if perm.card.escape_counters:
            perm.counters["+1/+1"] = perm.p1 + perm.card.escape_counters


def replicated(game, p, item, kind):
    """A replicated spell: copy it once for each time the replicate cost was paid."""
    from .cards import Effect
    if kind.startswith("replicate_"):
        game.queue_trigger(p, [Effect("storm_copy", int(kind[10:]))], name=f"{item.card.name}: replicate", context=item)


def dredge(game, p) -> bool:
    """Replace a draw with dredge when it's worth it; True if the draw was replaced."""
    cards = [c for c in p.graveyard if c.dredge and len(p.library) >= c.dredge + 10]
    if not cards:
        return False
    card = max(cards, key=lambda c: c.cmc)
    game.log(f"dredges {card.name}", p)
    for _ in range(card.dredge):
        game.move_card(p.library[-1], p.library, p.graveyard, reason="dredge")
    game.move_card(card, p.graveyard, p.hand, reason="dredge")
    return True


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
