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

_SRC = r"(?P<s>~|this creature|it|that creature)"
_AMOUNT = r"(?P<n>\d+|x)"


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


_REL = {" blocking it": "blocking_source", " it's blocking": "blocked_by_source",
        " blocking or blocked by it": "either"}


def _it(m) -> bool:
    """Whether the sentence's subject is "it" / "that creature" (an earlier target or the triggering creature)."""
    return m["s"].lower() in ("it", "that creature")


def _target(phrase: str, it: bool = False):
    """(target kind, selector, filter, rel) for a "target ..." phrase, or None. After "it" / "that creature",
    "another target" means another than the creature that deals the damage (the earlier target)."""
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
    if other and it:
        rel = rel or "not_prev"
    elif other:
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
        if _it(m):
            return (1, {"source_power": True}) if spec[2] == "power" else None   # the dealer's own stat, read at resolution
        return (1, {"xq": spec})
    return (1, {"xq": spec})


def _simple(m):
    from .cards.model import NO_MATCH
    amount = _amount(m)
    extra = dict(amount[1]) if amount is not None else {}
    if _it(m):
        extra["src_prev"] = True            # the damage comes from the earlier target / triggering creature, not the card
        if m["s"].lower() == "that creature":
            extra["src_ctx"] = True         # only "that creature" may mean the creature a trigger fired for ("it" is ~)
    if amount is not None and m["t"] == "any target":
        return _effect("damage", amount[0], target="any", data=extra)
    target = _target(m["t"], _it(m))
    if amount is None or target is None:
        return NO_MATCH
    return _damage(amount[0], target, extra)


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
    if _it(m):
        return NO_MATCH
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
    if code == "not_prev":              # "it deals ... to another target creature": not the creature dealing the damage
        dealer = next((t for t in getattr(game, "_choosing_targets", ()) if hasattr(t, "counters")), None)
        return perm is not dealer          # the first permanent chosen is the one dealing the damage
    blocked_by = [b for atk, group in game.blocks.items() if atk is perm for b in group]      # perm's blockers
    perm_blocks_src = any(perm in group for atk, group in game.blocks.items() if atk is src)
    src_blocks_perm = src in blocked_by
    return {"blocking_source": perm_blocks_src, "blocked_by_source": src_blocks_perm,
            "either": perm_blocks_src or src_blocks_perm}[code]


def plan_damage(ai, game, me, eff, card, precombat, earlier):
    """The AI's (target, value) for a damage effect after "it" / "another target": the amount is the earlier target's
    power, and that creature is not a legal target again."""
    outer = getattr(game, "_choosing_targets", None)
    game._choosing_targets = list(earlier)
    try:
        return ai.best_damage_target(game, me, scaled(game, me, eff), card, precombat)
    finally:
        game._choosing_targets = outer if outer is not None else []


def scaled(game, me, eff):
    """eff with its amount worked out for target choice: "damage equal to its power / the number of ..." and the
    source's power are known before the ability resolves, so the AI can tell what a target would die to."""
    import dataclasses
    src = game.target_source.source if hasattr(game.target_source, "source") else game.target_source
    if eff.data.get("xq") and src is not None and hasattr(src, "counters"):
        stub = type("Stub", (), {"source": src, "card": None, "x": 0})()
        return dataclasses.replace(eff, amount=eff.amount * game.x_quantity(me, eff.data["xq"], stub, None))
    if eff.data.get("src_prev"):
        earlier = [t for t in getattr(game, "_choosing_targets", ()) if hasattr(t, "counters")]
        ctx = getattr(game, "trigger_context", None) or getattr(game.target_source, "context", None)   # the trigger's creature
        src = earlier[0] if earlier else ctx if hasattr(ctx, "counters") and eff.data.get("src_ctx") else src
    if eff.data.get("source_power") and src is not None and hasattr(src, "power"):
        return dataclasses.replace(eff, amount=max(0, src.power))
    return eff


def damage_source(game, item, src, target=None, eff=None):
    """Who deals the damage when the sentence says "it" / "that creature": the first permanent an earlier effect of the
    same spell or ability targeted (Deadshot, Brokers Charm); for "that creature" else the creature that triggered the
    ability (Electropotence, Halana); else the ability's own source ("it" in a trigger about ~ is ~)."""
    from .engine.state import Permanent
    if item is not None:
        slot = next((i for i, (e, t) in enumerate(zip(item.effects, item.targets))
                     if e.data.get("src_prev") and t is target), None)
        for t in (item.targets[:slot] if slot is not None else ()):
            if isinstance(t, Permanent):
                return t
        if isinstance(item.context, Permanent) and eff is not None and eff.data.get("src_ctx"):
            return item.context
    return src
