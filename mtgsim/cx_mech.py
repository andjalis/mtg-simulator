"""Named mechanics (cx_mech*): rare keywords that need their own cast option.

    Splice onto Arcane {1}{W}   (as you cast an Arcane spell, reveal this card from your hand and pay its splice
                                 cost: add this card's effects to that spell; this card stays in your hand)

``parse_line`` reads the keyword into ``AltCost("splice", cost)`` (never a cast option of the card itself: a
spliceable card is only cast normally). ``variants`` offers, for each Arcane spell in hand, one variant per other
spliceable card in hand: the Arcane spell's cost plus the splice cost, its effects followed by the spliced card's.

    Undaunted                   (costs {1} less to cast for each opponent: ``cost_reduction = "undaunted"``)
    Escalate {2}                (pay it for each mode chosen beyond the first: cast variants ``escalate_k``)
    Buyback—Sacrifice a land.   (the buyback cost is a sacrifice or discard instead of mana: a ``buyback`` variant
    Buyback—Discard two cards.   at the card's own mana cost with that additional cost)
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    if parse_alt_line(line, st):
        return True
    m = re.fullmatch(r"Recover ((?:\{[^}]+\})+)(?: \(.*\))?", line)
    if m:
        st.alt_costs.append(AltCost("recover", parse_mana_cost(m[1]), zone="graveyard"))
        return True
    m = re.fullmatch(r"Splice onto Arcane ((?:\{[^}]+\})+)(?: \(.*\))?", line)
    if m:
        st.alt_costs.append(AltCost("splice", parse_mana_cost(m[1])))
        return True
    if re.fullmatch(r"Undaunted(?: \(.*\))?", line):
        st.extra["cost_reduction"] = "undaunted"
        return True
    m = re.fullmatch(r"Escalate ((?:\{[^}]+\})+)(?: \(.*\))?", line)
    if m:
        st.extra.setdefault("advanced_rules", {})["escalate"] = parse_mana_cost(m[1])
        return True
    m = re.fullmatch(r"Buyback—(?:Sacrifice (a land)|Discard (two|three|a) cards?)\.(?: \(.*\))?", line)
    if m:
        n = {"a": 1, "two": 2, "three": 3}.get(m[2], 0)
        st.alt_costs.append(AltCost("buyback_cost", {}, sacrifice="land" if m[1] else "", discard=n))
        return True
    return False


def variants(game, p, card) -> list:
    """Splice variants of the hand card (an Arcane spell) with each other spliceable card in hand."""
    from .cards import AltCost, add_mana
    out = _cost_variants(game, p, card)
    if "Arcane" not in card.subtypes or card.is_permanent:
        return out
    for other in p.hand:
        splice = next((a for a in other.alt_costs if a.kind == "splice"), None)
        if other is card or splice is None or not other.spell_effects:
            continue
        alt = AltCost(f"splice_{getattr(other, 'physical_id', id(other))}", add_mana(card.mana_cost, splice.cost),
                      extra=list(other.spell_effects))
        v = game._variant(card, alt.kind, alt)
        v.spliced = other
        out.append(v)
    return out


def _cost_variants(game, p, card) -> list:
    """Escalate casts with k extra modes, and buyback paid with a sacrifice or discard."""
    from .cards import AltCost, add_mana
    out = []
    esc = card.advanced_rules.get("escalate")
    if esc and card.modes:
        for k in range(1, len(card.modes)):
            extra = {c: n * k for c, n in esc.items()}
            out.append(game._variant(card, f"escalate_{k}", AltCost(f"escalate_{k}", add_mana(card.mana_cost, extra))))
    for a in card.alt_costs:
        if a.kind == "buyback_cost":
            out.append(game._variant(card, "buyback", AltCost("buyback", dict(card.mana_cost), sacrifice=a.sacrifice,
                                                              discard=a.discard)))
    return out


# ---------------------------------------------------------------------------
# Conditional and extra-cost alternative casts
#
#   Freerunning {3}{B}   cast for it if you dealt combat damage to a player this turn with an Assassin or commander
#   Prowl {2}{B}         ... with a creature that shares a creature type with the card
#   Web-slinging {2}{W}  cast for it if you also return a tapped creature you control to its owner's hand
#   Beam me up {3}{G}    cast it from your graveyard for it if you also return a creature you control to its
#                        owner's hand; the spell is exiled as it resolves (``beam`` variant, graveyard zone)
#   Reinforce 2—{1}{G}   {1}{G}, discard this card: put two +1/+1 counters on target creature (channel-style)
#
# Freerunning / prowl / web-slinging become ``cond_alt_N`` costs of cx_altcost (condition code + parts), so the
# hand variants, payment and the AI's "only when the normal cost isn't payable" rule are shared with it.
# ---------------------------------------------------------------------------


def note_hit(game, src) -> None:
    """Record the creature types of a creature that dealt combat damage to a player (freerunning, prowl)."""
    p = src.controller
    hits = getattr(p, "mech_hits", None)
    if hits is None or hits[0] != game.turn:
        hits = p.mech_hits = (game.turn, [])
    hits[1].append(frozenset(src.card.subtypes))


def check(game, p, code: str) -> bool:
    """``mech:hit:<Type>|<Type>``: you dealt combat damage to a player this turn with one of those types."""
    hits = getattr(p, "mech_hits", None)
    if hits is None or hits[0] != game.turn:
        return False
    types = set(code[9:].split("|"))
    return any(types & h for h in hits[1])


def pay_beam(game, p) -> bool:
    """Return a creature you control to its owner's hand (the cheapest first)."""
    mine = sorted((x for x in p.battlefield if x.is_creature), key=lambda x: x.card.cmc)
    if not mine:
        return False
    game.leave_battlefield(mine[0], "hand")
    return True


def parse_alt_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"(Freerunning|Prowl|Web-slinging|Beam me up) ((?:\{[^}]+\})+)(?: \((.*)\))?", line)
    if m:
        cost = parse_mana_cost(m[2])
        kind = m[1]
        if kind == "Beam me up":
            st.alt_costs.append(AltCost("beam", cost, zone="graveyard"))
            return True
        parts, code = (), ""
        if kind == "Web-slinging":
            parts = (("bounce", 1, {"tapped": True, "types": ["creature"]}),)
        elif kind == "Freerunning":
            code = "mech:hit:Assassin"      # or a commander: no commanders in this simulator
        else:
            types = st.type_line.split("—")[1].split() if "—" in st.type_line else []
            if not types:
                return False
            code = "mech:hit:" + "|".join(types)     # prowl: a creature that shares a type with the card
        index = len(st.extra.setdefault("advanced_rules", {}).get("alt_if", ()))
        st.extra["advanced_rules"]["alt_if"] = st.extra["advanced_rules"].get("alt_if", ()) + ((code, parts),)
        st.alt_costs.append(AltCost(f"cond_alt_{index}", cost))
        return True
    m = re.fullmatch(r"Reinforce (\d+)—((?:\{[^}]+\})+)(?: \(.*\))?", line)
    if m:
        from .cards import _parse_effects
        effs, bad = _parse_effects(f"Put {m[1]} +1/+1 counters on target creature.")
        if bad:
            return False
        st.alt_costs.append(AltCost("channel", parse_mana_cost(m[2]), effects=effs))
        return True
    return False


def beam_variants(game, p, card) -> list:
    """Beam me up casts of a graveyard card: needs a creature to return."""
    if not any(x.is_creature for x in p.battlefield):
        return []
    return [game._variant(card, "beam", a) for a in card.alt_costs if a.kind == "beam"]


def queue_recover(game, perm) -> None:
    """A creature was put into its owner's graveyard: each Recover card there gets its trigger."""
    from .cards.model import Effect
    owner = perm.owner
    for card in list(owner.graveyard):
        if any(a.kind == "recover" for a in card.alt_costs):
            version = owner.graveyard.version(card) if hasattr(owner.graveyard, "version") else None
            game.queue_trigger(owner, [Effect("cx_recover")], None, f"{card.name}: recover",
                               context=(owner, card, version))


def resolve_recover(game, item) -> None:
    """Pay the recover cost to return the card to hand; otherwise exile it."""
    from .engine.mana import payable
    owner, card, version = item.context
    grave = owner.graveyard
    if card not in grave or (version is not None and hasattr(grave, "version") and grave.version(card) != version):
        return
    cost = next(a.cost for a in card.alt_costs if a.kind == "recover")
    if payable(game.mana_sources(owner), cost) and game.pay(owner, cost, spell="ability") is not None:
        game.move_card(card, grave, owner.hand, reason="recover")
        game.log(f"recovers {card.name}", owner)
    else:
        game.move_card(card, grave, owner.exile, reason="recover")
        game.log(f"{card.name} is exiled (recover not paid)", owner)
