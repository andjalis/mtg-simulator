"""Suspect riders (the suspect action itself is cx_night_suspect):

    If ~ is suspected, put a +1/+1 counter on it. Otherwise, suspect it.     ("it's suspected" is a cx_condlib condition)
    If it's suspected, it's no longer suspected.     All suspected creatures are no longer suspected.
    {3}{B}, Sacrifice a suspected creature: ...      ("suspected" is a cx_condlib filter word)

``cx_unsuspect`` takes away what suspecting gave: menace, can't block and the ``suspected`` mark."""
from __future__ import annotations


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _who(word):
    return "self" if word == "~" else "prev"


EFFECT_PATTERNS = [
    (r"(?P<w>it|~|that creature)(?:'s| is) no longer suspected", lambda m: _effect("cx_unsuspect", target=_who(m["w"]))),
    (r"(?:you may )?have (?P<w>it|~|that creature) become no longer suspected",
     lambda m: _effect("cx_unsuspect", target=_who(m["w"]))),
    (r"all suspected creatures are no longer suspected", lambda m: _effect("cx_unsuspect", data={"all": True})),
]


def unsuspect(game, p, perm):
    from .engine.kinds.cx_night_suspect import SUSPECT_KEYWORDS
    if "suspected" not in perm.perm_kw:
        return
    perm.perm_kw.difference_update(SUSPECT_KEYWORDS)
    game.log(f"{perm.card.name} is no longer suspected", p)


def parse_otherwise(sentence: str, effects: list) -> bool:
    """"Otherwise, <effects>." after an effect gated by a cx_condlib condition: the effects run when it fails."""
    import re
    import dataclasses
    m = re.fullmatch(r"otherwise, (.+?)\.?", sentence.strip(), re.I)
    if not m or not effects or not effects[-1].cond.startswith("lib:"):
        return False
    from .cards import _parse_effects
    from .cx_condlib import _code
    body = m[1]
    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if bad or not new or any(e.cond for e in new):
        return False
    cond = effects[-1].cond
    effects.extend(dataclasses.replace(e, cond=_code("not", cond)) for e in new)
    return True


def otherwise_without_roll(sentence: str, effects: list, first: int) -> None:
    """The dungeon template reads "Otherwise, put a +1/+1 counter on ~" as the other faces of a die roll
    (Poultrygeist). With no die roll before it and a cx_condlib condition gating the effect just before
    ("put a +1/+1 counter on that creature if its power is less than ~'s power. Otherwise, ..."), it is that
    condition's other branch instead, as parse_otherwise reads it."""
    import re
    import dataclasses
    if first == 0 or len(effects) != first + 1 or not re.fullmatch(r"otherwise, .+", sentence.strip(), re.I):
        return
    eff, before = effects[first], effects[first - 1]
    cond = before.cond
    if eff.kind != "die_check" or not cond.startswith("lib:") or "instead_gate" in before.data \
            or any(e.kind == "die_roll" for e in effects[:first]):
        return
    # decided once, before either branch runs: a counter on "that creature" mustn't flip the comparison
    gate = {"cond": cond}
    effects[first - 1] = dataclasses.replace(before, cond="", data=dict(before.data, instead_gate=gate,
                                                                        instead_branch=True))
    effects[first:] = [dataclasses.replace(e, data=dict(e.data, instead_gate=gate, instead_branch=False))
                       for e in eff.data["then"]]
