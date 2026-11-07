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

HEXPROOF_FROM = ("white", "blue", "black", "red", "green", "monocolored")


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"When you unlock this door, (.+)", line)
    if m:
        from .cards import _parse_effects
        effs, bad = _parse_effects(m[1].replace("this Room", "~"))
        if bad or not effs:
            return False
        st.etb += effs          # the door's unlock effects: they run as the Room enters through this half
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
    """Splice variants of the hand card (an Arcane spell): each set of up to three other spliceable cards in hand."""
    from .cards import AltCost, add_mana
    out = _cost_variants(game, p, card)
    if "Room" in card.subtypes and card.back is not None:
        out += [game._variant(card, "room_left"), game._variant(card, "room_right")]
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


# ---------------------------------------------------------------------------
# Rooms: cast either half; its door is unlocked as it enters ("When you unlock this door" is an enter effect of
# that half); as a sorcery, pay the other half's mana cost to unlock the other door. A Room permanent's card is its
# unlocked doors: one half, or both halves merged (lists joined, dicts combined, sets unioned).
# ---------------------------------------------------------------------------


def _merge(left, right):
    import dataclasses
    changes = {"name": f"{left.name} // {right.name}"}
    for f in dataclasses.fields(left):
        lv, rv = getattr(left, f.name), getattr(right, f.name)
        if f.name in ("name", "mana_cost", "cmc", "back", "origin", "origin_generation"):
            continue
        if isinstance(lv, list) and isinstance(rv, list):
            changes[f.name] = lv + rv
        elif isinstance(lv, dict) and isinstance(rv, dict):
            changes[f.name] = {**rv, **lv}
        elif isinstance(lv, (set, frozenset)) and isinstance(rv, (set, frozenset)):
            changes[f.name] = lv | rv
        elif isinstance(lv, tuple) and isinstance(rv, tuple):
            changes[f.name] = lv + rv
    return dataclasses.replace(left, **changes)


def _doors(perm):
    """(left def, right def, which door the permanent's card is: "left", "right" or "both")."""
    card, base = perm.card, perm.front
    if base.back is None or "Room" not in base.subtypes:
        return None
    left, right = base, base.back
    if card.name == left.name:
        return left, right, "left"
    return left, right, "right" if card.name == right.name else "both"


def _mv(cost: dict) -> int:
    return sum(v for k, v in cost.items() if k != "X")


def room_entered(perm) -> None:
    """On the battlefield a Room's mana value is that of its unlocked doors (in hand and elsewhere it's both)."""
    import dataclasses
    doors = _doors(perm)
    if doors:
        perm.card = dataclasses.replace(perm.card, cmc=_mv(perm.card.mana_cost))


def can_unlock(game, p, perm) -> bool:
    doors = _doors(perm) if perm in p.battlefield else None
    return bool(doors and doors[2] != "both" and p is game.active and game.step in ("main1", "main2")
                and not game.stack)


def unlock(game, p, perm) -> bool:
    """Pay the locked door's mana cost (a sorcery): the permanent gains that half; its unlock effects run."""
    from .engine.mana import payable
    if not can_unlock(game, p, perm):
        return False
    left, right, state = _doors(perm)
    locked = right if state == "left" else left
    if not payable(game.mana_sources(p), locked.mana_cost) or game.pay(p, locked.mana_cost, spell="ability") is None:
        return False
    perm.card = _merge(left, right)
    import dataclasses
    perm.card = dataclasses.replace(perm.card, cmc=_mv(left.mana_cost) + _mv(right.mana_cost))
    game.log(f"unlocks {locked.name}", p)
    if locked.etb_effects:
        game.queue_trigger(p, locked.etb_effects, perm, f"{locked.name}: unlock")
    game.settle()
    return True


def ai_unlock(game, p) -> None:
    """The AI unlocks a locked door whenever it can pay for it."""
    for perm in list(p.battlefield):
        if can_unlock(game, p, perm):
            unlock(game, p, perm)


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
