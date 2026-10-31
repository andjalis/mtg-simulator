"""More activated-ability cost parts, paid after the mana:

    Tap two untapped creatures you control      Tap an untapped Ally you control      Tap another untapped creature you control
    Discard two cards     Discard a creature card     Discard a card at random     Discard your hand
    Return ~ to its owner's hand     Return a land you control to its owner's hand
    Exile two cards from your graveyard     Mill a card     Put a -1/-1 counter on ~     Exert ~
    Remove a counter from ~

``parse_part`` adds ``(kind, count, filter)`` to ``extra_costs["cx_costs"]``; ``payable`` and ``pay`` are called from
Game.can_activate / Game.activate_ability. The AI pays with its least valuable cards and permanents."""
from __future__ import annotations

import re

_Q = r"(?P<q>a|an|one|two|three|four|five|six|seven|another)"
_QN = {"a": 1, "an": 1, "one": 1, "another": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_RULES = [
    ("tap", re.compile(rf"Tap {_Q} untapped (?P<f>[\w -]+?) you control")),
    ("discard", re.compile(rf"Discard {_Q} cards?(?P<f>)")),
    ("discard_random", re.compile(rf"Discard {_Q} cards? at random(?P<f>)")),
    ("discard", re.compile(rf"Discard {_Q} (?P<f>[\w -]+?) cards?")),
    ("discard_hand", re.compile(r"Discard your hand(?P<q>)(?P<f>)")),
    ("bounce_self", re.compile(r"Return ~ to its owner's hand(?P<q>)(?P<f>)")),
    ("bounce", re.compile(rf"Return {_Q} (?P<f>[\w -]+?) you control to (?:its|their) owner's hands?")),
    ("exile_gy", re.compile(rf"Exile {_Q} (?P<f>[\w -]*?)cards? from your graveyard")),
    ("mill", re.compile(rf"Mill {_Q} cards?(?P<f>)")),
    ("counter_self", re.compile(rf"Put {_Q} (?P<f>-1/-1|\+1/\+1|[a-z]+) counters? on ~")),
    ("exert", re.compile(r"Exert ~(?P<q>)(?P<f>)")),
    ("remove_any", re.compile(rf"Remove {_Q} counters? from ~(?P<f>)")),
]


def parse_part(part: str, extra: dict) -> bool:
    from .cx_condlib import _filter
    for kind, rx in _RULES:
        m = rx.fullmatch(part)
        if not m:
            continue
        q = (m["q"] or "a").lower()
        n = _QN[q]
        f = (m["f"] or "").strip()
        spec: dict = {}
        if f and kind not in ("counter_self",):
            spec = _filter(f, plural=n > 1)
            if spec is None:
                return False
        if kind == "counter_self":
            spec = {"counter": f}
        if q == "another":
            spec = dict(spec, other=True)
        extra["cx_costs"] = extra.get("cx_costs", ()) + ((kind, n, spec),)
        return True
    return False


def _cards(p, card_list, spec, source=None):
    from .cx_condlib import _card_ok
    return [c for c in card_list if not spec or _card_ok(c, spec)]


def _candidates(game, p, perm, kind, spec):
    from .cx_condlib import _card_ok
    if kind == "tap":
        return [x for x in p.battlefield if not x.tapped and not (spec.get("other") and x is perm)
                and _card_ok(x.card, spec, x) and not (x.is_creature and x is perm)]
    if kind == "bounce":
        return [x for x in p.battlefield if not (spec.get("other") and x is perm) and _card_ok(x.card, spec, x)]
    if kind in ("discard", "discard_random"):
        return _cards(p, p.hand, spec)
    if kind == "exile_gy":
        return _cards(p, p.graveyard, spec)
    return []


def payable(game, p, perm, costs) -> bool:
    used: set = set()
    for kind, n, spec in costs:
        if kind in ("tap", "bounce", "discard", "discard_random", "exile_gy"):
            pool = [c for c in _candidates(game, p, perm, kind, spec) if id(c) not in used]
            if len(pool) < n:
                return False
            if kind != "discard_random":
                used.update(id(c) for c in pool[:n])
        elif kind == "mill" and len(p.library) < n:
            return False
        elif kind == "remove_any" and sum(v for v in perm.counters.values() if v > 0) < n:
            return False
        elif kind in ("exert",) and perm.tapped:
            return False
        elif kind in ("bounce_self", "counter_self", "exert", "remove_any") and perm not in p.battlefield:
            return False
    return True


def _cheap(things):
    from .engine.policy import perm_value
    from .engine.state import Permanent

    def key(x):
        if isinstance(x, Permanent):
            return perm_value(x)
        return (not x.is_land, x.cmc)
    return sorted(things, key=key)


def pay(game, p, perm, costs) -> bool:
    """Pay the parts in order; False when one can't be paid (the activation is rolled back)."""
    if not payable(game, p, perm, costs):
        return False
    for kind, n, spec in costs:
        if kind == "tap":
            for x in _cheap(_candidates(game, p, perm, kind, spec))[:n]:
                x.tapped = True
                game.fire(p, "becomes_tapped", x)
        elif kind == "discard":
            for _ in range(n):
                pool = _candidates(game, p, perm, kind, spec)
                if not pool:
                    return False
                choice = p.ai.choose_discard(game, p) if not spec else None
                game.discard_card(p, choice if choice in pool else _cheap(pool)[0])
        elif kind == "discard_random":
            for _ in range(n):
                if not p.hand:
                    return False
                game.discard_card(p, game.rng.choice(p.hand))
        elif kind == "discard_hand":
            for c in list(p.hand):
                game.discard_card(p, c)
        elif kind == "bounce":
            for x in _cheap(_candidates(game, p, perm, kind, spec))[:n]:
                game.leave_battlefield(x, "hand")
        elif kind == "bounce_self":
            game.leave_battlefield(perm, "hand")
        elif kind == "exile_gy":
            for c in _cheap(_candidates(game, p, perm, kind, spec))[:n]:
                game.move_card(c, p.graveyard, p.exile, reason="cost")
        elif kind == "mill":
            for _ in range(n):
                p.graveyard.append(p.library.pop())
        elif kind == "counter_self":
            perm.counters[spec["counter"]] = perm.counters.get(spec["counter"], 0) + n
        elif kind == "exert":
            perm.skip_untap += 1
            game.fire(p, "exerted", source=perm)
        elif kind == "remove_any":
            for _ in range(n):
                name = max((k for k, v in perm.counters.items() if v > 0), key=lambda k: perm.counters[k])
                perm.counters[name] -= 1
    return True
