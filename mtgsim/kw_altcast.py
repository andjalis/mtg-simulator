"""Alternative casting keywords and their object-bound upkeep/end-step abilities.

Mana keyword costs are supported; unusual nonmana costs remain visible to coverage.
"""
from __future__ import annotations

import dataclasses
import re

from . import delayed

MANA = r"(?:\{[0-9WUBRGC]+\})+"


def parse(line, extra, alternatives):
    from .cards import AltCost, parse_mana_cost
    if not line.startswith(("Madness", "Unearth", "Echo", "Buyback", "Dash", "Suspend", "Cumulative upkeep",
                            "Delve", "Improvise", "Retrace", "Rebound")):
        return False
    info = extra.setdefault("altcast", {})
    if line in ("Delve", "Improvise", "Retrace", "Rebound"):
        info[line.lower()] = True
        return True
    m = re.fullmatch(rf"(Madness|Unearth|Echo|Buyback|Dash) ({MANA})", line)
    if m:
        kind, cost = m[1].lower(), parse_mana_cost(m[2])
        if kind in ("echo", "buyback"):
            info[kind] = cost
        else:
            alternatives.append(AltCost(kind, cost, zone="graveyard" if kind == "unearth" else "hand"))
        return True
    m = re.fullmatch(rf"Suspend (\d+)—({MANA})", line)
    if m:
        alternatives.append(AltCost("suspend", parse_mana_cost(m[2]), counters=int(m[1])))
        return True
    m = re.fullmatch(rf"Cumulative upkeep(?:—| )({MANA}|Pay (\d+) life)\.?", line)
    if m:
        info["cumulative"] = ("life", int(m[2])) if m[2] else ("mana", parse_mana_cost(m[1]))
        return True
    return False


def options(game, p):
    from .cards import AltCost, CardDef, Effect
    from .engine import GraveyardTarget, add_costs
    out = []
    for c in p.hand:
        for alt in c.alt_costs:
            if alt.kind in ("dash", "suspend"):
                out.append(game._variant(c, alt.kind, alt))
        if "buyback" in c.altcast:
            out.append(game._variant(c, "buyback", AltCost("buyback", add_costs(c.mana_cost, c.altcast["buyback"]))))
    for c, entry in zip(p.graveyard, p.graveyard.entries):
        ref = GraveyardTarget(p, c, entry)
        if c.altcast.get("retrace") and any(x.is_land for x in p.hand):
            out.append(game._graveyard_variant(ref, "retrace", AltCost("retrace", c.mana_cost)))
        for alt in c.alt_costs:
            if alt.kind != "unearth":
                continue
            # Unearth is an activated ability; its card remains in the graveyard until resolution.
            v = CardDef(name=f"{c.name} (unearth)", mana_cost=alt.cost, cmc=c.cmc,
                        types=frozenset({"Sorcery"}), is_ability=True,
                        spell_effects=[Effect("alt_unearth", data={"entry": ref})])
            v.origin = c, "unearth", alt
            v.graveyard_target = ref
            out.append(v)
    return out


def plan_payment(game, p, card, cost, excluded=()):
    """Choose nonmana payments without mutating zones or tapping mana sources twice."""
    from .engine import find_payment
    cost = dict(cost)
    taps, exiles = [], []
    if card.altcast.get("improvise"):
        colored = {k: v for k, v in cost.items() if k not in ("generic", "X")}
        reserved = find_payment(game.mana_sources(p, spell=card), colored)
        if reserved is not None:
            artifacts = sorted((x for x in p.battlefield if "Artifact" in x.card.types and not x.tapped
                                and x not in excluded and x not in reserved), key=lambda x: bool(x.card.produces))
            taps = artifacts[:cost.get("generic", 0)]
            cost["generic"] = max(0, cost.get("generic", 0) - len(taps))
    if card.altcast.get("delve"):
        casting = getattr(card, "graveyard_target", None)
        exiles = [entry for entry in p.graveyard.entries if casting is None or entry is not casting.entry]
        exiles = exiles[:cost.get("generic", 0)]
        cost["generic"] = max(0, cost.get("generic", 0) - len(exiles))
    return cost, taps, exiles


def can_pay(game, p, card, cost):
    # cost_of already removed the nonmana contribution. Reserve its artifacts for mana planning.
    taps = getattr(game, "_altcast_taps", ())
    spell = "ability" if card.is_ability or game._origin(card)[1] == "suspend" else card
    return game.can_pay(p, cost, spell=spell) if not taps else _with_tapped(game, p, card, cost, taps)


def _with_tapped(game, p, card, cost, taps):
    old = [x.tapped for x in taps]
    try:
        for x in taps:
            x.tapped = True
        return game.can_pay(p, cost, spell=card)
    finally:
        for x, was in zip(taps, old):
            x.tapped = was


def exile_entry(p, card):
    # Deck copies share CardDef objects. Give this physical exile object its own identity.
    card = dataclasses.replace(card)
    p.exile.append(card)
    return {"card": card, "version": p.exile.version(card)}


def suspend(game, p, card, alt):
    base = game._origin(card)[0]
    if base not in p.hand or game.pay(p, alt.cost, spell="ability") is None:
        return False
    p.hand.remove(base)
    entry = exile_entry(p, base)
    entry["time"] = alt.counters
    p.suspended = getattr(p, "suspended", []) + [entry]
    if not alt.counters:
        # A card exiled with zero time counters never loses its last counter.
        p.suspended.remove(entry)
    game.log(f"suspends {base.name} ({alt.counters} time counters)", p)
    return True


def exile_live(p, entry):
    return any(c is entry["card"] for c in p.exile) and p.exile.version(entry["card"]) == entry["version"]


def upkeep(game, p):
    from .cards import Effect
    for perm in list(p.battlefield):
        if "echo" in perm.card.altcast and getattr(perm, "echo_controller", None) is not p:
            game.queue_trigger(p, [Effect("alt_echo")], perm, f"{perm.card.name} echo")
            perm.echo_controller = p
        if "cumulative" in perm.card.altcast:
            game.queue_trigger(p, [Effect("alt_cumulative")], perm, f"{perm.card.name} cumulative upkeep")
    live = []
    for entry in getattr(p, "suspended", []):
        if exile_live(p, entry):
            live.append(entry)
            game.queue_trigger(p, [Effect("alt_time", data={"entry": entry})], name="suspend")
    p.suspended = live
    pending, p.rebounding = getattr(p, "rebounding", []), []
    for entry in pending:
        if exile_live(p, entry):
            game.queue_trigger(p, [Effect("alt_free", data={"entry": entry, "kind": "rebound_cast"})], name="rebound")


def entered(game, perm, kind):
    from .cards import Effect
    if kind in ("dash", "suspend_cast", "unearth"):
        # Suspend and unearth haste do not expire at cleanup.
        perm.altcast_haste = True
        perm.altcast_kind = kind
    if kind in ("dash", "unearth"):
        if kind == "unearth":
            perm.unearthed = True
        delayed.schedule(game, perm.controller, Effect("alt_depart", data={"to": "hand" if kind == "dash" else "exile"}),
                         perm, name=kind)


def control_changed(perm):
    perm.echo_controller = None
    if getattr(perm, "altcast_kind", "") == "suspend_cast":
        perm.altcast_haste = False


def discard(game, p, card):
    from .cards import Effect
    alt = next((a for a in card.alt_costs if a.kind == "madness"), None)
    if alt is None:
        return False
    entry = exile_entry(p, card)
    game.queue_trigger(p, [Effect("alt_madness", data={"entry": entry, "alt": alt})], name=f"{card.name} madness")
    return True


def resolved(game, item, success):
    """True when a keyword replaces the usual destination after successful resolution."""
    if not success:
        return False
    p = item.controller
    base, kind, _ = game._origin(item.card)
    if kind == "buyback":
        p.hand.append(base)
        return True
    if base.altcast.get("rebound") and getattr(item, "cast_from_hand", False):
        p.rebounding = getattr(p, "rebounding", []) + [exile_entry(p, base)]
        return True
    return False


def free_cast(game, p, entry, kind, alt=None):
    from .cards import AltCost
    if not exile_live(p, entry):
        return False
    base = entry["card"]
    card = dataclasses.replace(game._variant(base, kind, alt or AltCost(kind, {"generic": 0})))
    card.origin = (base, kind, alt or AltCost(kind, {"generic": 0}))
    card.exile_entry = entry
    if not game._available(p, card):
        return False
    from .engine import TARGETED
    if any(e.target in TARGETED and not e.data.get("upto") and not game.legal_targets(p, e)
           for e in card.spell_effects):
        return False
    # Ignore card-type timing during the resolving trigger, but retain targets and restrictions.
    card.resolving_permission = True
    if not game.can_cast_now(p, card):
        return False
    return game.cast(p, card)


def resolve(game, p, eff, item):
    from .cards import Effect
    k, d = eff.kind, eff.data
    src = item.source if item else None
    if k == "alt_unearth":
        ref = d["entry"]
        index = ref.index()
        if index is not None:
            p.graveyard.pop(index)
            entered(game, game.enter_battlefield(p, ref.card), "unearth")
    elif k == "alt_depart":
        perm = item.context
        if perm in perm.controller.battlefield:
            game.leave_battlefield(perm, d["to"])
    elif k in ("alt_echo", "alt_cumulative"):
        if src is None or src not in src.controller.battlefield:
            return
        # Echo's intervening condition is checked again on resolution.
        if k == "alt_echo":
            cost, life = src.card.altcast["echo"], 0
        else:
            src.counters["age"] = src.counters.get("age", 0) + 1
            typ, amount = src.card.altcast["cumulative"]
            cost = {c: n * src.counters["age"] for c, n in amount.items()} if typ == "mana" else {}
            life = amount * src.counters["age"] if typ == "life" else 0
        paid = p.life > life and game.hook(p, "pay_optional")(game, p, cost, k)
        if paid and life:
            game.change_life(p, -life, "cumulative upkeep")
        elif paid:
            paid = game.pay(p, cost, spell="ability") is not None
        if not paid and src.controller is p:
            game.sacrifice(src)
    elif k == "alt_time":
        entry = d["entry"]
        if exile_live(p, entry) and entry["time"] > 0:
            entry["time"] -= 1
            if not entry["time"]:
                if entry in getattr(p, "suspended", []):
                    p.suspended.remove(entry)
                game.queue_trigger(p, [Effect("alt_free", data={"entry": entry, "kind": "suspend_cast"})], name="suspend cast")
    elif k == "alt_free":
        free_cast(game, p, d["entry"], d["kind"])
    elif k == "alt_madness":
        entry = d["entry"]
        if not free_cast(game, p, entry, "madness_cast", d["alt"]) and exile_live(p, entry):
            p.exile.remove(entry["card"])
            p.graveyard.append(entry["card"])


def use_abilities(game, p):
    """Minimal policy for special actions/abilities the spell evaluator cannot value."""
    for option in list(options(game, p)):
        base, kind, alt = game._origin(option)
        if kind == "suspend":
            # Save the delay when the normal spell can already be cast.
            if base.altcast.get("no_mana_cost") or not game.can_pay(p, game.cost_of(p, base), spell=base):
                if game.can_cast_now(p, option):
                    game.cast(p, option)
        elif kind == "unearth" and game.can_cast_now(p, option):
            game.cast(p, option)


def pay_x(game, p, card, targets):
    """Choose X using remaining mana plus delve/improvise, then pay exactly that X."""
    x = 0
    for n in range(1, 21):
        cost, taps, _ = plan_payment(game, p, card, {"generic": n})
        if not _with_tapped(game, p, card, cost, taps):
            break
        x = n
    if x and hasattr(p.ai, "choose_x"):
        x = max(0, min(x, p.ai.choose_x(game, p, card, targets, x)))
    cost, taps, exiles = plan_payment(game, p, card, {"generic": x})
    for perm in taps:
        perm.tapped = True
    payment = game.pay(p, cost, spell=card)
    if payment is None:
        for perm in taps:
            perm.tapped = False
        return 0, []
    for entry in exiles:
        p.exile.append(p.graveyard.pop(p.graveyard.entries.index(entry)))
    return x, payment
