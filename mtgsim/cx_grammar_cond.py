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
    from .cards.model import Effect, _num
    text = text.strip()
    m = re.fullmatch(r"(?:~|it|this creature) deals (\d+) damage", text, re.I)
    if m:
        return [Effect("damage", int(m[1]), target=_SAME)]
    m = re.fullmatch(r"create (a|an|one|two|three|four|five|six|seven|eight|nine|ten|X|\d+) of those tokens"
                     r"(?:, where X is (.+))?", text, re.I)
    if m:
        from .cards.clauses import _xq
        spec = _xq(m[2]) if m[2] else None
        if m[1].lower() == "x":
            return [Effect("token", 1, target=_SAME, data={"xq": spec})] if spec else None
        n = _num(m[1])
        return [Effect("token", n, target=_SAME)] if n and not m[2] else None
    if re.fullmatch(r"(?:~|it|this spell) deals twice X damage to that (?:permanent|creature|player)", text, re.I):
        return [Effect("damage", target=_SAME, data={"x": True, "instead_multiplier": 2})]
    if re.fullmatch(r"that player mills twice that many cards", text, re.I):
        return [Effect("mill", target=_SAME, data={"instead_amount": True, "instead_multiplier": 2})]
    new, bad = _parse_effects(text[0].upper() + text[1:] + ".")
    if new and not bad:
        return new
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


@rider(r"instead,? (?P<body>.+)")
def instead_prefix(m, inner):
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
    referents = set(TARGETED) | {"self", "prev"}
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
        if (i and len(group) == 1 and effects[i - 1].kind == "copy_next_spell" and
                group[0].kind == "copy_spell" and group[0].data.get("of") == "that"):
            # "Copy that spell twice instead" changes the number of future
            # copies, preserving the delayed instruction's kind and MV limit.
            group = [dataclasses.replace(group[0], kind="copy_next_spell",
                     data=dict(effects[i - 1].data, **group[0].data))]
            effects[i:j] = group
        if any(g.target == _SAME and (not old or g.kind != old[min(n, len(old) - 1)].kind)
               for n, g in enumerate(group)) and old:
            bad.append('An "instead" effect without a matching referent.')
            del effects[i:j]
            continue
        # A replacement may add effects around the single effect it replaces ("instead scry 3, then
        # draw three cards" for "draw three cards"), or change that effect's kind while referring
        # to its target (damage -> destroy).
        if i and (not old or [o.kind for o in old] != [g.kind for g in group]):
            candidate = effects[i - 1]
            if not candidate.cond and any(g.kind == candidate.kind or
                                           g.target == "prev" and candidate.target in referents
                                           for g in group):
                old, k = [candidate], 1
        if not old and _nested():
            i = j               # the body of "If C, B instead" parsed on its own: the outer sentence list resolves it
            continue
        matches = [o.kind for o in old] == [g.kind for g in group]
        if len(old) == 1:
            matches |= any(g.kind == old[0].kind or
                           g.target == "prev" and old[0].target in referents for g in group)
        if not cond or not old or any(o.data.get("cx_instead") for o in old) or not matches:
            bad.append("An \"instead\" effect without the effect it replaces.")
            del effects[i:j]
            continue
        if cond.startswith('lib:["prev_is",') and all(o.target == "self" for o in old):
            # "~ gets +1/+0. If it's an Aura, ... instead": "it" is the object of the replaced sentence, ~ itself
            src = 'lib:["src_is",' + cond[len('lib:["prev_is",'):]
            group = [dataclasses.replace(g, cond=src) for g in group]
            cond = src
        gate = {"cond": cond}       # shared identity: evaluate once before either branch changes the board
        for n, o in enumerate(old):
            effects[i - k + n] = dataclasses.replace(o, cond=_both(o.cond, _negate(cond)),
                                                    data=dict(o.data, instead_gate=gate, instead_branch=False,
                                                              instead_base_cond=o.cond))
        for n, g in enumerate(group):
            data = {key: v for key, v in g.data.items() if key != "cx_instead"}
            data.update(instead_gate=gate, instead_branch=True)
            target = g.target
            if g.kind == "cx_players" and g.data.get("who") == "that_player" and old[0].target == "player":
                target = "prev"
                data["who"] = "target"
            if target == _SAME:
                # "it deals 7 damage instead": the replaced effect's object, the very same target
                prior = old[min(n, len(old) - 1)]
                target = "prev" if prior.target in TARGETED else prior.target
                inherited = {key: value for key, value in prior.data.items()
                             if key not in ("x", "x2", "xq", "xq_size", "per", "per_kick")}
                data = dict(inherited, **data)
                if data.pop("instead_amount", False):
                    g = dataclasses.replace(g, amount=prior.amount, amount2=prior.amount2)
                    for key in ("x", "x2", "xq", "xq_size", "per", "per_kick"):
                        if key in prior.data:
                            data[key] = prior.data[key]
            effects[i + n] = dataclasses.replace(g, target=target, data=data)
        i = j
    return bad


# ---------------------------------------------------------------- "B unless ..."

_PAYERS = {"you": "you", "they": "they", "that player": "they", "its controller": "controller",
           "their controller": "controller", "that creature's controller": "controller",
           "that permanent's controller": "controller", "that spell's controller": "controller",
           # two players: "target opponent" is the opponent, as "target opponent loses 3 life" already reads
           "target opponent": "opponent", "an opponent": "opponent", "any player": "any"}

# "unless any player pays": whose interest B is, from B's kinds. B that only costs its controller (the source
# leaves) is paid for by the controller; B that only helps the controller is paid for by an opponent. Anything
# else stays unmatched.
_HURTS_CONTROLLER = ("sacrifice_self", "exile_self")
_HELPS_CONTROLLER = ("draw", "gain_life")
_HELPS_SELF = ("pump", "p1_counters")


def _against(effects):
    if all(e.kind in _HURTS_CONTROLLER or e.kind == "destroy" and e.target == "self" for e in effects):
        return "controller"
    if all(e.kind in _HELPS_CONTROLLER and e.target == "none" or e.kind in _HELPS_SELF and e.target == "self"
           and e.amount >= 0 and e.amount2 >= 0 for e in effects):
        return "opponents"
    return None


def _costs(text: str):
    """A list of alternative costs: "pays {1} or 1 life", "sacrifices a nonland permanent or discards a card"."""
    one = _cost(text)
    if one is not None:
        return [one]
    m = re.fullmatch(r"(\w+) (.+?) or (?:(\w+) )?(.+)", text, re.I)
    if m is None:
        return None
    verb = m[1]
    second = f"{m[3]} {m[4]}" if m[3] and m[3].lower().rstrip("s") in ("pay", "sacrifice", "discard") \
        else f"{verb} {(m[3] + ' ') if m[3] else ''}{m[4]}"
    a, b = _cost(f"{verb} {m[2]}"), _cost(second)
    return [a, b] if a and b else None


def _cost(text: str):
    """The cost of "pay(s) {2}{U}", "pay(s) 3 life", "sacrifice(s) a|another <filter>", "sacrifice(s) two <filters>"
    or "discard(s) a [<filter>] card", else None."""
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
    m = re.fullmatch(r"sacrifices? (two|three|four|five|six|seven) ([\w -]+)", text, re.I)
    if m:                       # a counted cost: all of them or none (#330)
        from .cards.model import _num
        spec = _filter(m[2], plural=True)
        return {"sacrifice": spec, "other": False, "count": _num(m[1])} if spec else None
    m = re.fullmatch(r"discards? (?:a|an) (?:([\w -]+) )?card", text, re.I)
    if m:
        spec = _filter(m[1], plural=False) if m[1] else {}
        return {"discard": spec} if spec is not None else None
    return None


def _who_pays(payer: str, first):
    """The cx_unless payer code for the payer words and B's first effect, or None when the words have no fixed
    referent there: "they" is the player B names, "its controller" the controller of the object B names."""
    from .engine.state import TARGETED
    if payer in ("you", "opponent"):
        return payer
    if first.kind == "cx_players":
        who = first.data.get("who")
        return {"controller": "prev_controller", "that_player": "context", "opponents": "opponent",
                "target": "target"}.get(who) \
            if payer == "they" else None
    if payer == "they":
        return {"player": "target", "each_opponent": "opponent", "that_player": "context"}.get(first.target)
    if first.target == "prev":
        return "prev_controller"
    return "controller" if first.target in TARGETED and first.target != "player" else None


def _each_gate(first, costs):
    """"Each player <B> unless they <cost>": one cx_unless_each effect, so every player decides for themselves
    and B reaches only those who didn't pay. None for other bodies."""
    from .cards.model import Effect
    if first.kind == "lose_each" and not first.cond and not first.data:
        inner = [Effect("lose_life", first.amount, target="that_player")]
    elif first.kind == "cx_players" and first.data.get("who") == "each" and not first.cond \
            and set(first.data) == {"who", "effects"}:
        inner = list(first.data["effects"])
    else:
        return None
    return [Effect("cx_unless_each", data={"who": "each", "costs": costs, "effects": inner})]


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
    words = next((k for k in _PAYERS if rest.lower().startswith(k + " ")), None)
    costs = _costs(rest[len(words) + 1:]) if words else None
    if costs is None:           # "unless an opponent was dealt damage this turn": a condition, not a cost
        if any(e.kind == "cx_delay" for e in effects):
            return None         # the condition belongs to the delayed trigger's resolution, not to now
        cond = _if_cond(rest)
        return [dataclasses.replace(e, cond=_both(e.cond, _negate(cond))) for e in effects] if cond else None
    payer = _PAYERS[words]
    if payer == "they" and len(effects) == 1:
        each = _each_gate(effects[0], costs)
        if each:
            return each
    data = {}
    if payer == "any":
        who, data["against"] = "any", _against(effects)
        if data["against"] is None:
            return None
    else:
        who = _who_pays(payer, effects[0])
    if who is None:
        return None
    gate = Effect("cx_unless", data={"costs": costs, "payer": who, **data})
    unpaid = _code("unless_unpaid")
    return [gate] + [dataclasses.replace(e, cond=_both(e.cond, unpaid)) for e in effects]
