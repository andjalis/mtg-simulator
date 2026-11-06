"""Condition riders on whole sentences: "If C, B instead" and "B instead if C".

An "instead" sentence replaces the effects of the sentence before it when its condition holds:

    ~ deals 2 damage to any target. If you're the monarch, it deals 7 damage instead.
    Draw two cards. If you have the city's blessing, draw three cards instead.
    You gain 2 life. If a creature died this turn, you gain 8 life instead.

"If C, ..." is split off by ``_parse_effects`` (which puts C on the body's effects); the body "B instead" reaches
the grammar fallback, where the rider below parses B and marks its effects. ``resolve_instead`` (the last step of
``_parse_effects``) then gives the replaced effects the opposite condition. The replaced effects are the ones just
before, matched kind by kind; anything else is rejected, so an "instead" never runs next to what it replaces.
An elided object ("it deals 7 damage instead") is the replaced effect's: the same target, or the same players.
"""
from __future__ import annotations

import dataclasses
import re

from .cx_grammar import rider

_SAME = "cx_same"      # placeholder target: the object of the effect this one replaces


def _body(text: str):
    """Effects for the body of an "instead" sentence, or None."""
    from .cards import _parse_effects
    text = text.strip()
    new, bad = _parse_effects(text[0].upper() + text[1:] + ".")
    if new and not bad:
        return new
    m = re.fullmatch(r"(?:~|it|this creature) deals (\d+) damage", text, re.I)
    if m:
        from .cards.model import Effect
        return [Effect("damage", int(m[1]), target=_SAME)]
    return None


def _mark(effects, cond=""):
    return [dataclasses.replace(e, cond=e.cond or cond, data=dict(e.data, cx_instead=True)) for e in effects]


@rider(r"(?P<body>.+?) instead if (?P<cond>.+)")
def instead_if(m, inner):
    from .cards.clauses import _if_cond
    cond = _if_cond(m["cond"])
    effects = _body(m["body"]) if cond else None
    return _mark(effects, cond) if effects else None


@rider(r"(?P<body>.+?) instead")
def instead(m, inner):
    effects = _body(m["body"])
    return _mark(effects) if effects else None


def _negate(code: str) -> str:
    from .cx_condlib import _code
    return code[1:] if code.startswith("!") else _code("not", code)


def _both(a: str, b: str) -> str:
    from .cx_condlib import _code
    return _code("and", a, b) if a else b


def _nested() -> bool:
    """Whether this _parse_effects call runs inside another one (it parses a part of a sentence)."""
    import sys
    frame, calls = sys._getframe(1), 0
    while frame is not None:
        calls += frame.f_code.co_name == "_parse_effects"
        frame = frame.f_back
    return calls > 1


def resolve_instead(effects: list) -> list:
    """Give the effects an "instead" group replaces the opposite condition, in place. Returns the sentences that
    could not be tied to what they replace (for the unmatched list)."""
    from .engine.state import TARGETED
    bad = []
    i = 0
    while i < len(effects):
        if not effects[i].data.get("cx_instead"):
            i += 1
            continue
        cond = effects[i].cond
        j = i
        while j < len(effects) and effects[j].data.get("cx_instead") and effects[j].cond == cond:
            j += 1
        k = j - i
        old = effects[i - k:i] if i >= k else []
        group = effects[i:j]
        if not old and _nested():
            i = j               # the body of "If C, B instead" parsed on its own: the outer sentence list resolves it
            continue
        if not cond or not old or any(o.data.get("cx_instead") for o in old) or \
                [o.kind for o in old] != [g.kind for g in group]:
            bad.append("An \"instead\" effect without the effect it replaces.")
            del effects[i:j]
            continue
        for n, o in enumerate(old):
            effects[i - k + n] = dataclasses.replace(o, cond=_both(o.cond, _negate(cond)))
        for n, g in enumerate(group):
            data = {key: v for key, v in g.data.items() if key != "cx_instead"}
            target = g.target
            if target == _SAME:
                # "it deals 7 damage instead": the replaced effect's object, the very same target
                target = "prev" if old[n].target in TARGETED else old[n].target
                data = dict(old[n].data, **data)
            effects[i + n] = dataclasses.replace(g, target=target, data=data)
        i = j
    return bad


# ---------------------------------------------------------------- "B unless ..."

_PAYERS = {"you": "you", "they": "they", "that player": "they", "its controller": "controller",
           "their controller": "controller", "that creature's controller": "controller",
           "that permanent's controller": "controller", "that spell's controller": "controller"}


def _cost(text: str):
    """The cost of "pay(s) {2}{U}", "pay(s) 3 life", "sacrifice(s) a|another <filter>" or "discard(s) a [<filter>]
    card", else None."""
    from .cards.model import parse_mana_cost
    m = re.fullmatch(r"pays? ((?:\{[\dWUBRGC]\})+)", text, re.I)
    if m:
        return {"mana": parse_mana_cost(m[1].upper())}
    m = re.fullmatch(r"pays? (\d+) life", text, re.I)
    if m:
        return {"life": int(m[1])}
    from .cx_condlib import _filter
    m = re.fullmatch(r"sacrifices? (a|an|another) ([\w -]+)", text, re.I)
    if m:
        spec = _filter(m[2], plural=False)
        return {"sacrifice": spec, "other": m[1].lower() == "another"} if spec else None
    m = re.fullmatch(r"discards? (?:a|an) (?:([\w -]+) )?card", text, re.I)
    if m:
        spec = _filter(m[1], plural=False) if m[1] else {}
        return {"discard": spec} if spec is not None else None
    return None


def _who_pays(payer: str, first):
    """The cx_unless payer code for the payer words and B's first effect, or None when the words have no fixed
    referent there: "they" is the player B names, "its controller" the controller of the object B names."""
    from .engine.state import TARGETED
    if payer == "you":
        return "you"
    if first.kind == "cx_players":
        who = first.data.get("who")
        return {"controller": "prev_controller", "that_player": "context", "opponents": "opponent"}.get(who) \
            if payer == "they" else None
    if payer == "they":
        return {"player": "target", "each_opponent": "opponent", "that_player": "context"}.get(first.target)
    if first.target == "prev":
        return "prev_controller"
    return "controller" if first.target in TARGETED and first.target != "player" else None


@rider(r"(?P<body>.+?) unless (?P<rest>.+)")
def unless(m, inner):
    """"B unless C": B when C doesn't hold. "B unless <payer> pays <cost>": the payer may pay as B would resolve;
    B happens only if they don't (a cx_unless Effect just before B records the choice)."""
    from .cards.clauses import _if_cond
    from .cards.model import Effect
    from .cx_condlib import _code
    effects = _body(m["body"])
    if not effects or any(e.target == _SAME for e in effects):
        return None
    rest = m["rest"].strip()
    payer = next((v for k, v in _PAYERS.items() if rest.lower().startswith(k + " ")), None)
    if payer is None:
        cond = _if_cond(rest)
        return [dataclasses.replace(e, cond=_both(e.cond, _negate(cond))) for e in effects] if cond else None
    cost = _cost(rest[len(next(k for k, v in _PAYERS.items() if rest.lower().startswith(k + " "))) + 1:])
    if cost is None:
        return None
    who = _who_pays(payer, effects[0])
    if who is None:
        return None
    gate = Effect("cx_unless", data=dict(cost, payer=who))
    unpaid = _code("unless_unpaid")
    return [gate] + [dataclasses.replace(e, cond=_both(e.cond, unpaid)) for e in effects]
