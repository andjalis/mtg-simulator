"""Activated-ability cost parts the base cost parsers don't model, stored as ``cx_costs`` tuples:

    {Q} (untap symbol)     Remove three quest counters from ~ and sacrifice it
    Remove a +1/+1 counter from a creature you control
    Exile the top N cards of your library     Exile the top [creature] card of your graveyard

``parse_part`` is tried by ``cx_costs.parse_part`` after its own rules; ``payable``/``pay_one`` are called from
``cx_costs.payable``/``cx_costs.pay`` for the kinds in ``KINDS``."""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
      "nine": 9, "ten": 10}
_NUM = r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
KINDS = ("sacrifice_n", "untap_self", "remove_sac", "remove_creature_counter", "exile_top_library", "exile_top_gy")


def _n(word: str) -> int:
    return int(word) if word.isdigit() else _N[word.lower()]


def parse_part(part: str, extra: dict) -> bool:
    spec = None
    if part == "{Q}":
        spec = ("untap_self", 1, {})
    elif (m := re.fullmatch(rf"Remove {_NUM} ([a-z][\w-]*) counters? from ~ and sacrifice it", part)):
        spec = ("remove_sac", _n(m[1]), {"counter": m[2]})
    elif (m := re.fullmatch(rf"Remove {_NUM} (\+1/\+1|-1/-1) counters? from a creature you control", part)):
        spec = ("remove_creature_counter", _n(m[1]), {"counter": m[2]})
    elif (m := re.fullmatch(rf"Exile the top {_NUM} cards? of your library", part)) or \
            (m := re.fullmatch(r"Exile the top (card) of your library", part)):
        spec = ("exile_top_library", 1 if m[1] == "card" else _n(m[1]), {})
    elif (m := re.fullmatch(r"Exile the top (?:(creature|land|artifact|instant|sorcery) )?card of your graveyard", part)):
        spec = ("exile_top_gy", 1, {"type": m[1]} if m[1] else {})
    elif (m := re.fullmatch(rf"Sacrifice {_NUM} (.+)", part)):
        from .permanent_templates import selector
        n = _n(m[1])
        sel = selector(m[2], plural=n > 1)
        if sel is not None and n >= 1 and "controller" not in sel:
            spec = ("sacrifice_n", n, dict(sel))
    if spec is None or spec[1] < 1:
        return False
    extra["cx_costs"] = extra.get("cx_costs", ()) + (spec,)
    return True


def _gy_pick(p, spec):
    """The top (most recently added) graveyard card matching the type, or None."""
    for c in reversed(p.graveyard):
        if not spec.get("type") or spec["type"].capitalize() in c.types:
            return c
    return None


def _creature_with(p, perm, counter, n):
    """Creatures that can lose n counters, least valuable first."""
    from .cx_costs import _cheap
    return _cheap([x for x in p.battlefield if x.is_creature and x.counters.get(counter, 0) >= n])


def _sac_pool(game, p, perm, spec):
    from .permanent_templates import matches
    from .engine.policy import perm_value
    return sorted((x for x in p.battlefield if x is not perm and matches(game, x, spec, p, perm)), key=perm_value)


def payable(game, p, perm, kind, n, spec) -> bool:
    if kind == "sacrifice_n":
        return len(_sac_pool(game, p, perm, spec)) >= n
    if kind == "untap_self":
        return perm in p.battlefield and perm.tapped and not (perm.is_creature and perm.sick)   # CR 302.6
    if kind == "remove_sac":
        return perm in p.battlefield and perm.counters.get(spec["counter"], 0) >= n
    if kind == "remove_creature_counter":
        return bool(_creature_with(p, perm, spec["counter"], n))
    if kind == "exile_top_library":
        return len(p.library) >= n
    if kind == "exile_top_gy":
        return _gy_pick(p, spec) is not None
    return False


def pay_one(game, p, perm, kind, n, spec) -> bool:
    if kind == "sacrifice_n":
        pool = _sac_pool(game, p, perm, spec)
        if len(pool) < n:
            return False
        for x in pool[:n]:
            game.sacrifice(x)
        return True
    if kind == "untap_self":
        perm.tapped = False
    elif kind == "remove_sac":
        perm.counters[spec["counter"]] -= n
        game.sacrifice(perm)
    elif kind == "remove_creature_counter":
        pool = _creature_with(p, perm, spec["counter"], n)
        if not pool:
            return False
        pool[0].counters[spec["counter"]] -= n
    elif kind == "exile_top_library":
        for _ in range(n):
            game.move_card(p.library[-1], p.library, p.exile, reason="cost")
    elif kind == "exile_top_gy":
        c = _gy_pick(p, spec)
        if c is None:
            return False
        game.move_card(c, p.graveyard, p.exile, reason="cost")
    return True


def ai_cost_ok(game, me, perm, costs) -> bool:
    """Whether the AI should pay these cost parts for an ability (policy.ability_worth): it sacrifices only
    near-worthless permanents and doesn't exile its library down to nothing."""
    from .engine.policy import perm_value
    for kind, n, spec in costs.get("cx_costs", ()):
        if kind == "sacrifice_n":
            if any(not v.card.is_token and perm_value(v) > 1 for v in _sac_pool(game, me, perm, spec)[:n]):
                return False
        elif kind == "exile_top_library" and len(me.library) < n + 10:
            return False
    return True
