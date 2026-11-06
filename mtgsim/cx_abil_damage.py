"""One damage sentence, in general: "<source> deals N damage to <target>" / "... deals damage equal to <quantity> to <target>".

The target phrase goes through the shared selector grammar (``permanent_templates.selector``): "target creature with flying",
"target attacking creature without flying", "target red creature", "each creature without flying", "another target
creature", "target creature or planeswalker", "target creature token, player, or planeswalker". Phrases relative to the
source ("target creature blocking it", "target creature it's blocking") are checked by ``rel_ok`` (a hook in
``Game.passes_filter``); "that was dealt damage this turn" uses the engine's ``damaged`` filter.
A second clause "and N damage to itself" is its own effect. The amount is a number, X, or a quantity the engine knows
(``cards.clauses._xq``: its power, counters on it, creatures you control, ...)."""
from __future__ import annotations

import re

_SRC = r"(?:~|it|this creature|that creature)"
_AMOUNT = r"(?P<n>\d+|x)"


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


_REL = {" blocking it": "blocking_source", " it's blocking": "blocked_by_source",
        " blocking or blocked by it": "either"}


def _target(phrase: str):
    """(target kind, selector, filter, rel, other) for a "target ..." phrase, or None."""
    from .permanent_templates import selector
    phrase = phrase.strip()
    m = re.fullmatch(r"(another )?target (.+)", phrase)
    if m is None:
        return None
    other, sel = bool(m[1]), m[2]
    rel = filt = ""
    for suffix, code in _REL.items():
        if sel.endswith(suffix):
            sel, rel = sel[:-len(suffix)], code
            break
    if sel.startswith("attacking or blocking "):
        sel, filt = sel[len("attacking or blocking "):], "attacking_blocking"
    if sel.endswith(" that was dealt damage this turn"):
        sel, filt = sel[:-len(" that was dealt damage this turn")], "damaged"
    spec = selector(sel)
    if spec is None:
        return None
    spec = dict(spec)
    if other:
        spec["other"] = True
    types = spec.get("types_all") or spec.get("types_any") or []
    if set(types) == {"creature"} and "types_any" not in spec:
        kind = "creature"
    elif set(types) == {"creature", "planeswalker"}:
        kind = "creature_pw"
    else:
        return None
    return kind, spec, filt, rel


def _damage(amount, target, extra=None):
    kind, spec, filt, rel = target
    data = {"selector": spec}
    if rel:
        data["cx_rel"] = rel
    if extra:
        data.update(extra)
    return _effect("damage", amount, target=kind, filter=filt, data=data)


def _amount(m):
    """(Effect amount, extra data) from the sentence's amount group, or None."""
    if m.groupdict().get("n"):
        n = m["n"].lower()
        return (0, {"x": True}) if n == "x" else (int(n), {})
    from .cards.clauses import _xq
    spec = _xq(m["q"])
    if spec is None or "prev" in spec:
        return None
    if spec[0] == "stat" and spec[1] == "self":
        return (1, {"xq": spec})
    return (1, {"xq": spec})


def _simple(m):
    from .cards.model import NO_MATCH
    amount = _amount(m)
    if amount is not None and m["t"] == "any target":
        return _effect("damage", amount[0], target="any", data=dict(amount[1]))
    target = _target(m["t"])
    if amount is None or target is None:
        return NO_MATCH
    return _damage(amount[0], target, amount[1])


def _each(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import selector
    amount = _amount(m)
    spec = selector(m["t"], plural=False) or selector(m["t"], plural=True)
    if amount is None or spec is None or amount[1] or not set(spec.get("types_all", ())) == {"creature"}:
        return NO_MATCH
    return _effect("group_remove", amount[0], data={"selector": spec, "op": "damage"})


def _and_itself(m):
    from .cards.model import NO_MATCH
    target = _target(m["t"]) if m["t"] != "any target" else None
    if m["t"] == "any target":
        first = _effect("damage", int(m["n"]), target="any")
    elif target is None:
        return NO_MATCH
    else:
        first = _damage(int(m["n"]), target)
    return [first, _effect("damage", int(m["m"]), target="self")]


EFFECT_PATTERNS = [
    (rf"{_SRC} deals (?P<n>\d+) damage to (?P<t>.+?) and (?P<m>\d+) damage to itself", _and_itself),
    (rf"{_SRC} deals {_AMOUNT} damage to each (?P<t>.+)", _each),
    (rf"{_SRC} deals {_AMOUNT} damage to (?P<t>.+)", _simple),
    (rf"{_SRC} deals damage equal to (?P<q>.+?) to (?P<t>.+)", _simple),
]


def rel_ok(game, eff, perm) -> bool:
    """Whether perm stands in the relation to the damage's source that eff asks for (see _REL)."""
    src = game.target_source.source if hasattr(game.target_source, "source") else game.target_source
    code = eff.data["cx_rel"]
    blocked_by = [b for atk, group in game.blocks.items() if atk is perm for b in group]      # perm's blockers
    perm_blocks_src = any(perm in group for atk, group in game.blocks.items() if atk is src)
    src_blocks_perm = src in blocked_by
    return {"blocking_source": perm_blocks_src, "blocked_by_source": src_blocks_perm,
            "either": perm_blocks_src or src_blocks_perm}[code]


def scaled(game, me, eff):
    """eff with its amount worked out for target choice: "damage equal to its power / the number of ..." and the
    source's power are known before the ability resolves, so the AI can tell what a target would die to."""
    import dataclasses
    src = game.target_source.source if hasattr(game.target_source, "source") else game.target_source
    if eff.data.get("xq") and src is not None and hasattr(src, "counters"):
        stub = type("Stub", (), {"source": src, "card": None, "x": 0})()
        return dataclasses.replace(eff, amount=eff.amount * game.x_quantity(me, eff.data["xq"], stub, None))
    if eff.data.get("source_power") and src is not None and hasattr(src, "power"):
        return dataclasses.replace(eff, amount=max(0, src.power))
    return eff
