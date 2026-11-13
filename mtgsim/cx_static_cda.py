"""Characteristic-defining power / toughness read with the shared quantity reader (#401):

    ~'s power and toughness are each equal to the number of creatures your opponents control.
    ~'s power and toughness are each equal to 1 plus twice the number of age counters on it.
    ~'s power is equal to the number of creature cards in all graveyards and its toughness is equal to that number plus 1.
    ~'s power is equal to the number of cards in your hand.                  (the toughness is printed)
    ~'s toughness is equal to your devotion to white.

Q is read by ``cards.clauses._xq`` and checked like the static gate's quantities (``cx_static_gate._quantity``: no
reading of power / toughness, of the resolving item, or a count copies.fits can't read). The rule is
``advanced_rules["cda"] = (power, toughness)``, each ``(spec, times, plus)`` or None for the printed value, and sets
the base power / toughness in ``continuous.pt`` / ``base_pt`` before any set-base effect (layer 7a), on the
battlefield. The older ``cx_cda`` / ``pt_cda`` lines keep their own path."""
from __future__ import annotations

import re

_PART = r"(?:(?P<{0}n>\d+) plus )?(?P<{0}x>twice )?(?P<{0}q>.+?)"
_BOTH = re.compile(rf"~'s power and toughness are each equal to {_PART.format('a')}")
_POWER = re.compile(rf"~'s power is equal to {_PART.format('a')}"
                    r"(?: and its toughness is equal to that number plus (?P<plus>\d+))?")
_TOUGH = re.compile(rf"~'s toughness is equal to {_PART.format('a')}")


def _spec(m):
    """(quantity spec, times, plus) for the matched part, or None."""
    from .cards.clauses import _xq
    from .cx_static_gate import _quantity
    text = re.sub(r" on it$", " on ~", m["aq"])
    spec = _quantity(_xq(text), text, strict=False)
    if not spec:
        return None
    return spec, 2 if m["ax"] else 1, int(m["an"] or 0)


def parse_line(line: str, st) -> bool:
    s = re.sub(r"^[A-Z][\w' ,-]* — ", "", line.strip())
    if not s.endswith(".") or "Creature" not in st.types and "Creature" not in st.type_line:
        return False
    s = s[:-1]
    for rx, which in ((_BOTH, "both"), (_POWER, "power"), (_TOUGH, "toughness")):
        m = rx.fullmatch(s)
        if m is None:
            continue
        spec = _spec(m)
        if spec is None:
            return False
        if which == "both":
            cda = (spec, spec)
        elif which == "power":
            cda = (spec, (spec[0], spec[1], spec[2] + int(m["plus"])) if m["plus"] else None)
        else:
            cda = (None, spec)
        rules = st.extra.setdefault("advanced_rules", {})
        old = rules.get("cda", (None, None))
        if any(a is not None and b is not None for a, b in zip(old, cda)):
            return False        # two lines define the same value
        rules["cda"] = tuple(b if b is not None else a for a, b in zip(old, cda))
        return True
    return False


_ACTIVE: set = set()


def base(permanent, p, t):
    """The printed (p, t) with the characteristic-defining values in place."""
    cda = permanent.card.advanced_rules.get("cda")
    if not cda or permanent.abilities_suppressed or id(permanent) in _ACTIVE:
        return p, t
    game = getattr(permanent.controller, "_game", None)
    if game is None:
        return p, t
    from .engine.state import StackItem
    _ACTIVE.add(id(permanent))
    try:
        item = StackItem(permanent.controller, [], [], source=permanent)
        out = []
        for part, printed in zip(cda, (p, t)):
            if part is None:
                out.append(printed)
            else:
                spec, times, plus = part
                out.append(max(0, game.x_quantity(permanent.controller, spec, item, None)) * times + plus)
    finally:
        _ACTIVE.discard(id(permanent))
    return out[0], out[1]
