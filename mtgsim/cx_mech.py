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

from .cards.model import KEYWORDS

HEXPROOF_FROM = ("white", "blue", "black", "red", "green", "monocolored")
KEYWORDS.update(f"hexproof from {w}" for w in HEXPROOF_FROM)


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
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
    """Splice variants of the hand card (an Arcane spell): each set of up to three other spliceable cards in hand."""
    from .cards import AltCost, add_mana
    out = _cost_variants(game, p, card)
    if "Arcane" not in card.subtypes or card.is_permanent:
        return out
    from itertools import combinations
    pool = [(o, next(a for a in o.alt_costs if a.kind == "splice")) for o in p.hand
            if o is not card and o.spell_effects and any(a.kind == "splice" for a in o.alt_costs)]
    for size in range(1, min(3, len(pool)) + 1):      # one, two or three spliced cards (up to three offered)
        for combo in combinations(pool, size):
            cost = card.mana_cost
            for _, splice in combo:
                cost = add_mana(cost, splice.cost)
            kind = "splice_" + "_".join(str(getattr(o, "physical_id", id(o))) for o, _ in combo)
            alt = AltCost(kind, cost, extra=[e for o, _ in combo for e in o.spell_effects])
            v = game._variant(card, kind, alt)
            v.spliced = [o for o, _ in combo]
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


# "~ becomes prepared" / "if ~ isn't prepared, it becomes prepared" / "it becomes prepared": the effect kind and the
# prepared-spell cast are prepare.py's; these are the self and "it" targets (the second wording is idempotent).
EFFECT_PATTERNS = [
    (r"(?:if ~ isn't prepared, it|~) becomes prepared",
     lambda m: _prep("self")),
    (r"it becomes prepared", lambda m: _prep("prev")),
]
SUBS: list = []


def _prep(target):
    from .cards import Effect
    return Effect("prepare", 1, target=target, data={"prepared": True})


def hexproof_from(perm, by, source) -> bool:
    """Hexproof from <color / monocolored>: whether ``by`` can't target perm with a source of that quality."""
    from .cards.model import CardDef
    from .engine.state import Permanent, StackItem
    if perm.controller is by or not isinstance(perm, Permanent):
        return False
    if isinstance(source, StackItem):
        source = source.card or source.source
    card = source.card if isinstance(source, Permanent) else source
    if not isinstance(card, CardDef):
        return False
    from .engine.state import COLOR_WORDS
    if len(card.colors) == 1 and perm.has("hexproof from monocolored"):
        return True
    return any(perm.has(f"hexproof from {w}") for w, c in COLOR_WORDS.items() if c in card.colors)
