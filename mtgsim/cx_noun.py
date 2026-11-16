"""#403: object qualifiers for the shared noun-phrase reader (``permanent_templates.selector``).

Slice 1, "with mana value X", "with power X or less", "with toughness X or less" (selector key ``stat_x``:
[stat, "==" | "<="]). X is the X paid for the spell or ability:

- on resolution, and when a target is re-checked, it is the stack item's X (``item.x``);
- when an activated ability's targets are chosen, it is the X the AI chose (``fix_x`` writes it into the selector
  as a plain ``stat`` bound before the targets are picked);
- when a spell's targets are chosen, X isn't paid yet: a target is legal when its value is at most the largest
  X the caster could still pay. For "with mana value X" (equal) the spell then pays exactly the target's value
  (``x_from_targets``, play.cast); for "X or less" it pays as much X as the mana allows, as every X spell does.

Only a spell with {X} in its mana cost and an activated ability with {X} in its cost tie X to the payment;
anywhere else (a trigger, a modal spell, an alternative cost) the line stays unsupported (``unpaid_stat_x``).
"X or greater" is refused by the reader: the payment would have to be the smallest X, which nothing chooses.
"""
from __future__ import annotations

import dataclasses
import re


def _has(obj, depth=0) -> bool:
    """Whether an effect list (or a nested effect / dict) uses a ``stat_x`` selector."""
    if depth > 6 or obj is None:
        return False
    if isinstance(obj, dict):
        return "stat_x" in obj or any(_has(v, depth + 1) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has(v, depth + 1) for v in obj)
    data = getattr(obj, "data", None)
    if isinstance(data, dict):
        return _has(data, depth + 1)
    effects = getattr(obj, "effects", None)
    return _has(effects, depth + 1) if effects is not None else False


def _equal(obj, depth=0) -> bool:
    if depth > 6 or obj is None:
        return False
    if isinstance(obj, dict):
        return obj.get("stat_x", [None, None])[1] == "==" or any(_equal(v, depth + 1) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_equal(v, depth + 1) for v in obj)
    data = getattr(obj, "data", None)
    return _equal(data, depth + 1) if isinstance(data, dict) else False


def unpaid_stat_x(cost, spell, modes, triggers, activated, loyalty, etb, alt_costs=(), extra=None) -> list:
    """Unsupported notes for a "with mana value X" qualifier whose X isn't a mana {X} of that spell or ability."""
    bad = []
    if _has(spell) and not (cost or {}).get("X"):
        bad.append("spell")
    if any(_has(m) for m in (modes or ())):
        bad.append("mode")
    if any(_has(t.effects) for t in triggers or ()) or _has(etb):
        bad.append("trigger")
    if any(_has(a.effects) and not a.cost.get("X") for a in activated or ()):
        bad.append("ability")
    if any(_has(effs) for _, effs in loyalty or ()):
        bad.append("loyalty")
    if any(_has(getattr(a, "effects", None)) for a in alt_costs or ()):
        bad.append("alternative cost")
    if _has({k: v for k, v in (extra or {}).items() if k != "alt_costs"}):
        bad.append("other")
    return [f"'with mana value / power / toughness X' without a mana X of its own ({', '.join(bad)})"] if bad else []


def _bound_spec(spec, x, at_most=False):
    """A selector with its ``stat_x`` replaced by the plain bound ``stat`` for this X (nested selectors too)."""
    if isinstance(spec, dict):
        out = {k: _bound_spec(v, x, at_most) for k, v in spec.items() if k != "stat_x"}
        if "stat_x" in spec:
            stat, op = spec["stat_x"]
            out["stat"] = [stat, "<=" if at_most else op, x]
        return out
    if isinstance(spec, list):
        return [_bound_spec(v, x, at_most) for v in spec]
    return spec


def fix_x(effects, x):
    """Effects judged with the X chosen for an activation: each ``stat_x`` becomes the bound ``stat`` for X."""
    return [dataclasses.replace(e, data=_bound_spec(e.data, x)) if _has(e) else e for e in effects]


def plan_x(effects, x):
    """A spell's effects as the AI judges them before casting (ai._sized), at the most X its mana pays: "with mana
    value X" (equal) reads as "X or less", since play.cast pays exactly the chosen target's value."""
    return [dataclasses.replace(e, data=_bound_spec(e.data, x, at_most=True)) if _has(e) else e for e in effects]


def affordable_x(game, controller, card) -> int:
    """The largest X ``controller`` could pay for ``card`` on top of the rest of its cost right now."""
    from .engine.mana import payable
    per = max(1, (card.mana_cost or {}).get("X", 1))
    cost = {k: v for k, v in game.cost_of(controller, card).items() if k != "X"}
    sources = game.mana_sources(controller, spell=card)
    n = 0
    while n < 20 and payable(sources, dict(cost, generic=cost.get("generic", 0) + (n + 1) * per)):
        n += 1
    return n


def x_bound(game, controller):
    """(X, exact) for a ``stat_x`` qualifier being checked now, or None when no X applies. ``exact`` is False while
    a spell's targets are chosen (X is the most the caster can still pay, so "equal" reads as "at most")."""
    from .engine.state import StackItem
    from .cards.model import CardDef
    src = getattr(game, "target_source", None)
    if isinstance(src, StackItem):
        return getattr(src, "x", 0) or 0, True
    item = getattr(game, "resolving_item", None)
    if isinstance(item, StackItem):
        return getattr(item, "x", 0) or 0, True
    if isinstance(src, CardDef) and (src.mana_cost or {}).get("X") and controller is not None:
        return affordable_x(game, controller, src), False
    return None


def stat_x_ok(game, permanent, spec, controller) -> bool:
    bound = x_bound(game, controller)
    if bound is None:
        return False
    n, exact = bound
    stat, op = spec["stat_x"]
    value = permanent.card.cmc if stat == "mana value" else getattr(permanent, stat)
    return value <= n if op == "<=" or not exact else value == n


def x_from_targets(game, effects, targets):
    """The X a spell pays when a "with mana value X" target fixes it (play.cast): the chosen target's value, or
    None when no such qualifier is targeted (False when two targets disagree)."""
    xs = set()
    for e, t in zip(effects, targets):
        spec = e.data.get("selector") if t is not None and _equal(e) else None
        if spec is None or "stat_x" not in spec or not hasattr(t, "card"):
            continue
        stat = spec["stat_x"][0]
        xs.add(t.card.cmc if stat == "mana value" else getattr(t, stat))
    if not xs:
        return None
    return xs.pop() if len(xs) == 1 else False


def ability_x(game, p, perm, act, best):
    """The X for an activated ability with a "with mana value X" (equal) target: the value of the best target the
    AI would pick at some X it can pay (0 .. best), else ``best``."""
    from .engine.state import TARGETED
    if not _equal(act.effects):
        return best
    choice, top = None, None
    for x in range(0, (best or 0) + 1):
        preview = fix_x(act.effects, x)
        with game.targeting(perm):
            picked = game.auto_targets(p, preview, perm)
        if any(e.target in TARGETED and t is None and not e.data.get("optional_target")
               for e, t in zip(preview, picked)):
            continue
        hit = [t for e, t in zip(preview, picked) if e.target in TARGETED and t is not None]
        if not hit:
            continue
        from .ai import perm_value
        score = sum(perm_value(t) if t.controller is not p else -perm_value(t) for t in hit if hasattr(t, "card"))
        if top is None or score > top:
            choice, top = x, score
    return choice if choice is not None else best


# ---------------------------------------------------------------- slice 3: relational stats
# "with power less than ~'s power", "with power less than or equal to the number of creatures you control",
# "with power greater than its base power", "with toughness greater than the number of cards in your hand"
# (selector key ``stat_rel``: [stat, "<" | ">", or_equal, ref]). ref is ("base",) / ("own", stat) for the matched
# permanent's own base or current value, or ("q", spec) for a quantity cards.clauses._xq reads, counted for the
# selector's controller ("you") with the ability's source as "~".

_REL = re.compile(r" with (power|toughness|mana value) (less|greater) than( or equal to)? (.+)$", re.I)


def take_rel(text):
    """(text without the qualifier, the stat_rel spec) for a trailing relational stat qualifier, (text, None) when
    there is none, or (text, False) when there is one this reader can't evaluate."""
    m = _REL.search(text)
    if not m:
        return text, None
    stat, ref = m[1].lower(), m[4].strip()
    low = ref.lower()
    own = re.fullmatch(r"(?:its|their) (base )?(power|toughness)", low)
    if own:
        if own[1] and own[2] != stat:
            return text, False          # "power greater than its base toughness": not a printed shape
        spec = ("base",) if own[1] else ("own", own[2])
    else:
        if re.fullmatch(r"~'s", low):           # "with power less than ~'s": the same stat of the source
            low = f"~'s {stat}"
        if re.search(r"\b(?:it|its|them|their|they)\b", low):
            return text, False          # "the number of rust counters on it": "it" is the matched object (Corrosion)
        from .cards.clauses import _xq
        q = _xq(low)
        if q is None or q[0] == "stat" and q[1] != "self" or q[0] in ("spell", "sac"):
            return text, False          # "that creature's power", "that spell's ...": no referent in a selector
        spec = ("q", q)
    return text[:m.start()], [stat, "<" if m[2].lower() == "less" else ">", bool(m[3]), spec]


def rel_ok(game, permanent, spec, controller, source) -> bool:
    from .engine.state import Permanent, StackItem
    stat, op, or_equal, ref = spec["stat_rel"]
    value = permanent.card.cmc if stat == "mana value" else getattr(permanent, stat)
    if ref[0] == "base":
        from .continuous import base_pt
        bound = base_pt(permanent)[0 if stat == "power" else 1]
    elif ref[0] == "own":
        bound = getattr(permanent, ref[1])
    else:
        q = ref[1]
        if q[0] == "stat" and not isinstance(source, Permanent):
            return False                # "~'s power" with no source on the battlefield
        item = game.target_source if isinstance(game.target_source, StackItem) else \
            getattr(game, "resolving_item", None)
        if not isinstance(item, StackItem) or item.source is not source:
            item = StackItem(controller, [], [], source=source if isinstance(source, Permanent) else None,
                             name="qualifier")
        if controller is None:
            return False
        bound = game.x_quantity(controller, q, item, None)
    if value == bound:
        return or_equal
    return value < bound if op == "<" else value > bound


# ---------------------------------------------------------------- slice 4: damage this turn
# "that was dealt damage this turn", "that dealt damage this turn", "that dealt damage to you this turn" (selector
# key ``damage_turn``: "was_dealt" | "dealt" | "dealt_you"). Game.deal_damage records, per permanent, the turn it was
# last dealt damage and the turn it last dealt damage (with the players it dealt damage to that turn).

_DAMAGE = re.compile(r" that (was dealt|were dealt|dealt) damage( to you)? this turn$", re.I)


def take_damage(text):
    m = _DAMAGE.search(text)
    if not m:
        return text, None
    if m[1].lower() in ("was dealt", "were dealt"):
        return (text[:m.start()], "was_dealt") if not m[2] else (text, False)
    return text[:m.start()], "dealt_you" if m[2] else "dealt"


def note_damage(game, source, target):
    from .engine.state import Permanent, Player
    if isinstance(target, Permanent):
        target.cx_dealt_damage_turn = game.turn
    if isinstance(source, Permanent):
        players = source.cx_damage_to[1] if getattr(source, "cx_damage_to", (None,))[0] == game.turn else set()
        if isinstance(target, Player):
            players = players | {id(target)}
        source.cx_damage_to = (game.turn, players)


def damage_ok(game, permanent, how, controller) -> bool:
    if how == "was_dealt":      # marked damage only lasts the turn; the record also covers infect / wither damage
        return permanent.damage > 0 or getattr(permanent, "cx_dealt_damage_turn", None) == game.turn
    turn, players = getattr(permanent, "cx_damage_to", (None, set()))
    if turn != game.turn:
        return False
    return how == "dealt" or controller is not None and id(controller) in players
