"""#403 — the object qualifiers one shared noun-phrase reader knows.

Three readers parse a noun phrase: the template regexes that hand a ``cx_desc`` to
``cx_events._object_subject``, ``permanent_templates.selector`` and ``cx_grammar._noun`` (the
compositional grammar's single entry point for a noun phrase, which tries ``selector`` first and
``_object_subject`` second). They used to know different qualifier subsets, so a sentence parsed
as soon as one qualifier was removed. This module owns the shapes the others did not know, and
the predicate evaluator both sides share:

    with mana value X [or less] / with power X or less / with toughness X or less
        X is the X paid for the spell or ability when its targets are chosen (``x_paid``)
    with mana value equal to N
    with power less than / greater than [or equal to] ~'s power (also toughness vs ~'s power)
    that entered this turn
    that has a <kind> counter on it / that has counters on it

"of the chosen type / of that type" is deliberately absent: the choice is not stored on the source
yet, so those lines stay ignored.

``take`` strips up to three trailing qualifiers off a noun phrase and returns their predicates;
``pred_ok`` evaluates one predicate against a permanent. ``selector`` maps the predicates onto its
spec keys and ``matches`` evaluates them; ``_object_subject`` appends them to its ``with`` list and
``_with_ok`` evaluates them through the same ``pred_ok``.
"""
from __future__ import annotations

import re

_COUNTER = r"(?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?)"

# Trailing qualifiers of a noun phrase, matched at its end. (regex, predicate maker).
QUALIFIERS = [
    # "with mana value X or less" / "with power X": X is the X paid for the spell or ability
    (r" with (mana value|power|toughness) (?:X|\{X\})(?: or (less|greater))?$",
     lambda m: ("stat_x", m[1].lower(), "<=" if (m[2] or "").lower() != "greater" else ">=", "X")),
    (r" with (mana value|power|toughness) equal to (\d+)$",
     lambda m: ("stat_eq", m[1].lower(), int(m[2]))),
    # "with power less than ~'s power", "with power greater than or equal to ~'s" (ref defaults to the stat)
    (r" with (power|toughness) (less|greater) than( or equal to)? ~'s(?: (power|toughness))?$",
     lambda m: ("rel_self", m[1], ">" if m[2] == "greater" else "<", bool(m[3]), m[4] or m[1])),
    (r" that entered(?: the battlefield)? this turn$", lambda m: ("entered_turn",)),
    (r" that has (?:a|an|one or more) (" + _COUNTER + r") counters? on (?:it|them)$",
     lambda m: ("counter_kind", m[1].lower())),
    (r" that has (?:a|an|one or more) counters? on (?:it|them)$", lambda m: ("any_counter",)),
]

_LIMIT = 3


def take_one(text: str):
    """Strip one trailing qualifier off a noun phrase: (core, pred), or (text, None) if none matches."""
    for pat, mk in QUALIFIERS:
        m = re.search(pat, text, re.I)
        if m:
            return text[:m.start()].strip(), mk(m)
    return text, None


def take(text: str, limit: int = _LIMIT):
    """Strip up to ``limit`` trailing qualifiers off a noun phrase: (core, preds)."""
    preds = []
    for _ in range(limit):
        core, pred = take_one(text)
        if pred is None:
            break
        preds.append(pred)
        text = core
    return text, preds


def x_paid(game, controller=None) -> int:
    """The X paid for the spell or ability whose targets are being chosen: the stack item's X when
    there is one, else the most X the controller could pay for the card being cast right now (the
    engine pays as much X as the remaining mana allows)."""
    from .engine.state import StackItem
    src = getattr(game, "target_source", None)
    if isinstance(src, StackItem):
        return getattr(src, "x", 0) or 0
    n = getattr(src, "x_paid", None)          # an AI-sized spell copy (ai.HeuristicAI._sized)
    if n is not None:
        return n
    if controller is None:
        return 0
    from .engine.mana import payable
    from .cards.model import CardDef
    sources = game.mana_sources(controller)
    if isinstance(src, CardDef) and "X" in (src.mana_cost or {}):
        cost = {k: v for k, v in game.cost_of(controller, src).items() if k != "X"}
        n = 0
        while n < 20 and payable(sources, dict(cost, generic=cost.get("generic", 0) + n + 1)):
            n += 1
        return n
    n = 0
    while n < 20 and payable(sources, {"generic": n + 1}):
        n += 1
    return n


def _stat_value(perm, stat: str):
    return perm.card.cmc if stat == "mana value" else getattr(perm, stat, 0)


def pred_ok(game, perm, pred, source, controller=None) -> bool:
    """Whether ``perm`` satisfies one qualifier predicate. ``source`` is what "~'s" names; it may be
    a Permanent, a card, or cx_grammar's _Viewer (which reads "~'s power" lazily)."""
    k = pred[0]
    if k == "stat_x":
        _, stat, op, _bound = pred
        n = x_paid(game, controller)
        v = _stat_value(perm, stat)
        return v <= n if op == "<=" else v >= n if op == ">=" else v == n
    if k == "stat_eq":
        _, stat, n = pred
        return _stat_value(perm, stat) == n
    if k == "rel_self":
        _, stat, op, incl, ref = pred
        want = getattr(source, ref, None) if source is not None else None
        if want is None:
            return False
        v = getattr(perm, stat, 0)
        if op == "<":
            return v < want or (incl and v == want)
        return v > want or (incl and v == want)
    if k == "entered_turn":
        return getattr(perm, "entered_turn", -1) == game.turn
    if k == "counter_kind":
        return perm.counters.get(pred[1], 0) > 0
    if k == "any_counter":
        return any(v > 0 for v in perm.counters.values())
    return False
