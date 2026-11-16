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
    m = re.fullmatch(r"create (a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|X|\d+) of those tokens"
                     r"(?:, where X is (.+))?", text, re.I)
    if m:
        from .cards.clauses import _xq
        spec = _xq(m[2]) if m[2] else None
        if m[1].lower() == "x":
            return [Effect("token", 1, target=_SAME, data={"xq": spec})] if spec else None
        n = {"eleven": 11, "twelve": 12}.get(m[1].lower()) or _num(m[1])
        return [Effect("token", n, target=_SAME)] if n and not m[2] else None
    if re.fullmatch(r"(?:~|it|this spell) deals twice X damage to that (?:permanent|creature|player)", text, re.I):
        return [Effect("damage", target=_SAME, data={"x": True, "instead_multiplier": 2})]
    if re.fullmatch(r"return that card from (?:your|its owner's) graveyard to the battlefield", text, re.I):
        # Stitch Together: the same graveyard return, to the battlefield instead of the hand
        return [Effect("gy_move", target=_SAME, data={"dest": "bf", "instead_amount": True})]
    if re.fullmatch(r"that player mills twice that many cards", text, re.I):
        return [Effect("mill", target=_SAME, data={"instead_amount": True, "instead_multiplier": 2})]
    m = re.fullmatch(r"(?:those creatures|they) get ([+-]\d+)/([+-]\d+) until end of turn", text, re.I)
    if m:           # the replaced group pump with other numbers ("those creatures get +2/+2 until end of turn")
        return [Effect("cx_same_pt", int(m[1]), int(m[2]), target=_SAME, data={"instead_pt": True})]
    new, bad = _parse_effects(text[0].upper() + text[1:] + ".")
    if new and not bad:
        return new
    return _anaphor(text)


# "it", "that creature", ... after the verb: the object of the effect this one replaces
_ANAPHOR = re.compile(r"(?<=\S )(?:it|that creature|that permanent|the creature|the permanent)\b(?!')", re.I)


def _anaphor(text: str):
    """Effects for "exile it", "you may put that creature on top of its owner's library": the body read with
    "target creature" (or "target permanent") in the anaphor's place, its one targeted effect then aimed at the
    replaced effect's object (target "prev", marked ``cx_anaphor`` so ``resolve_instead`` checks there is one)."""
    from .cards import _parse_effects
    from .engine.state import TARGETED
    if len(_ANAPHOR.findall(text)) != 1:
        return None
    for noun in ("target creature", "target permanent"):
        new, bad = _parse_effects(_ANAPHOR.sub(noun, text, count=1)[0].upper() + _ANAPHOR.sub(noun, text, count=1)[1:]
                                  + ".")
        if not new or bad:
            continue
        aimed = [n for n, e in enumerate(new) if e.target in TARGETED]
        if len(aimed) != 1 or any(e.target not in ("none",) for n, e in enumerate(new) if n not in aimed) or \
                any(key in new[aimed[0]].data for key in ("optional_target", "distinct")):
            continue
        e = new[aimed[0]]
        data = {key: v for key, v in e.data.items() if key not in ("selector", "side")}   # chosen by the base
        new[aimed[0]] = dataclasses.replace(e, target="prev", filter="", data=dict(data, cx_anaphor=True))
        return new
    return None


def if_body(body: str):
    """(effects, unmatched) for the body of "If C, B": a "B instead" body is read by the "instead" riders, so no
    template takes "instead" for part of B (a token "with flying instead")."""
    from .cards import _parse_effects
    m = re.fullmatch(r"(.+?),? instead|instead,? (.+)", body.strip().rstrip("."), re.I)
    effects = _body(m[1] or m[2]) if m else None
    if effects:
        return _mark(effects), []
    return _parse_effects(body[0].upper() + body[1:] + ".")


def kicked_instead(base: list, text: str) -> bool:
    """"If this spell was kicked, B instead" for the kicked version's effects ``base`` (in place): B read like any
    "instead" body and tied to the instruction before it, gated on the kick (always true on the kicked cast)."""
    m = re.fullmatch(r"(.+?),? instead|instead,? (.+)", text.strip().rstrip("."), re.I)
    effects = _body(m[1] or m[2]) if m and base else None
    if not effects:
        return False
    merged = base + _mark(effects, 'lib:["kicked"]')
    # the kicked lines come without their sentence boundaries: only a lone base effect is surely "the one before"
    if resolve_instead(merged, [0, len(base)] if len(base) == 1 else None):
        return False
    base[:] = merged
    return True


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


_PT_KINDS = {"pump": 1, "pump_all": 1, "debuff_one": -1, "debuff": -1, "debuff_all": -1}


def _swap_pt(base, new):
    """The group pump ``base`` with the numbers of "those creatures get +A/+B ... instead", or None when base is no
    such pump or the signs don't fit its kind (a -N pump kind can't carry +N)."""
    from .engine.state import TARGETED
    inner = base
    if base.kind == "cx_group" and len(base.data.get("effects") or ()) == 1:
        inner = base.data["effects"][0]
    sign = _PT_KINDS.get(inner.kind)
    if sign is None or base.kind in ("pump", "debuff_one") and base.target in TARGETED:
        return None             # a single target is "that creature", not "those creatures"
    a, b = new.amount * sign, new.amount2 * sign
    if a < 0 or b < 0 or set(inner.data) - {"other", "keyword", "side"} or inner.data.get("keyword"):
        return None
    swapped = dataclasses.replace(inner, amount=a, amount2=b)
    if inner is not base:
        swapped = dataclasses.replace(base, data=dict(base.data, effects=[swapped]))
    target = "prev" if base.target in TARGETED else base.target
    return dataclasses.replace(swapped, target=target, cond=new.cond,
                               data=dict(swapped.data, cx_instead=True))


def _previous_sentence(effects, i, starts):
    """The index where the sentence before the one starting at effect ``i`` begins, or None (no such sentence, it
    gave no effects, or the "instead" sentence gave effects before ``i``)."""
    if not starts or i not in starts:
        return None
    n = max(x for x, st in enumerate(starts) if st == i)
    if n == 0 or starts[n - 1] == i:
        return None
    return starts[n - 1]


def _link(old, group):
    """``group`` with its references to "the replaced object" bound to the effects ``old`` of the sentence before,
    or None when a reference has nothing to bind to."""
    from .engine.state import TARGETED
    objects = [o for o in old if o.target != "none"]
    ref = objects[-1].target if objects else "none"
    out = []
    for g in group:
        if g.target == _SAME and not (len(old) == 1 and g.kind == old[0].kind):
            return None
        if g.target == "prev":
            if ref in ("host", "self"):
                g = dataclasses.replace(g, target=ref)
            elif ref not in TARGETED and ref != "prev":
                return None
        elif g.target == "that_player":
            if ref == "each_opponent" and g.kind == "lose_life" and not g.data.get("xq"):
                g = dataclasses.replace(g, kind="drain")    # "that player loses 3 life": the opponent, as drain
                g = dataclasses.replace(g, target="each_opponent")
            elif ref == "player":
                g = dataclasses.replace(g, target="prev")
            else:
                return None
        out.append(g)
    return out


def resolve_instead(effects: list, starts=None) -> list:
    """Give the effects an "instead" group replaces the opposite condition, in place. Returns the sentences that
    could not be tied to what they replace (for the unmatched list). ``starts`` (where each sentence's effects
    begin) lets a group replace the whole sentence before it when no effect-by-effect match is found."""
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
        if len(group) == 1 and group[0].kind == "token" and group[0].target == _SAME and i and \
                effects[i - 1].kind in ("cx_token", "copy_perm") and not effects[i - 1].data.get("xq") and \
                not group[0].data.get("xq"):
            # "create five of those tokens instead" after a token kind that counts in its own way
            prior, n = effects[i - 1], group[0].amount
            data = dict(prior.data, n=n) if prior.kind == "copy_perm" else dict(prior.data)
            group = effects[i:j] = [dataclasses.replace(
                prior, amount=n if prior.kind == "cx_token" else prior.amount, cond=group[0].cond,
                target="prev" if prior.target in TARGETED else prior.target, data=dict(data, cx_instead=True))]
        if len(group) == 1 and group[0].data.get("instead_pt"):
            swapped = _swap_pt(effects[i - 1], group[0]) if i else None
            if swapped is None:
                bad.append("An \"instead\" effect without the effect it replaces.")
                del effects[i:j]
                continue
            group = effects[i:j] = [swapped]
            old, k = [effects[i - 1]], 1
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
        a = _previous_sentence(effects, i, starts) if not matches or any(
            g.target == "prev" and not (old and old[-1].target in set(TARGETED) | {"prev"}) for g in group) else None
        prior = effects[a:i] if a is not None else []
        shared = {g.kind for g in group} & {o.kind for o in prior} - {"pay_gate"}
        if prior and not any(o.cond or o.data.get("cx_instead") for o in prior) and not (len(prior) > 1 and shared):
            # (a kind shared with part of a longer sentence: "draw a card and gain 2 life. If C, gain 8 life
            # instead" replaces only that part, which the match above didn't find)
            # "If C, B instead" replaces the whole instruction before it: "create a 1/1 Insect token. If ..., create a
            # token that's a copy of ~ instead", "~ deals 2 damage to any target. If ..., exile it instead"
            linked = _link(prior, group)
            if linked is not None:
                group = effects[i:j] = linked
                old, k, matches = prior, i - a, True
        if any(g.data.get("cx_anaphor") for g in group) and not (
                old and [o for o in old if o.target != "none"] and
                [o for o in old if o.target != "none"][-1].target in set(TARGETED) | {"prev"}):
            matches = False     # "exile it instead" needs a chosen object to be "it"
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
            data = {key: v for key, v in g.data.items() if key not in ("cx_instead", "cx_anaphor")}
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
    m = re.fullmatch(r"pays? ((?:\{[\dWUBRGC]\})+) for each (.+)", text, re.I)
    if m:                       # "pay {1} for each card in your hand": that much mana per counted thing (#330)
        spec = _per_spec(m[2])
        return {"mana": parse_mana_cost(m[1].upper()), "per": spec[0], "it": spec[1]} if spec else None
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
    return _counted_cost(text)


def _per_spec(q: str):
    """(quantity spec, refers to "it") for "for each <q>", from the source controller's side, or None. "On it"
    is read as the source; unless() keeps that only when the gated effects act on the source itself."""
    from .cards.clauses import _xq
    it = bool(re.search(r"\bon it$", q))
    q = re.sub(r"\bon (?:it|this \w+)$", "on ~", q.strip())
    words = q.split()
    plurals = [" ".join(words[:i] + [words[i] + "s"] + words[i + 1:]) for i in range(len(words))
               if re.fullmatch(r"[a-z+/1-]*[a-rt-z]", words[i], re.I)]     # the head noun, wherever it is
    for cand in ["the number of " + x for x in [q] + plurals]:
        spec = _xq(cand)
        if spec is not None:
            return spec, it
    return None


_COUNT = r"(a|an|another|one|two|three|four|five)"


def _counted_cost(text: str):
    """The counted costs of #330, or None: "return(s) N [untapped] <filter> you control to (its|their) owner's
    hand", "tap(s) N untapped <filter> you control", "remove(s) N <kind> counter(s) from it", "exile(s) a card
    from your graveyard", "has ~ deal N damage to them" (the payer takes the damage from the source)."""
    from .cards.model import _num
    from .cx_condlib import _filter

    def count(word):
        return 1 if word.lower() in ("a", "an", "another") else _num(word)

    m = re.fullmatch(rf"returns? {_COUNT} (.+?) you control to (?:its|their) owners?'s? hands?", text, re.I)
    if m:
        spec = _filter(m[2], plural=count(m[1]) > 1)
        return {"bounce": spec, "count": count(m[1]), "other": m[1].lower() == "another"} if spec else None
    m = re.fullmatch(rf"taps? {_COUNT} untapped (.+?) you control", text, re.I)
    if m:
        spec = _filter(m[2], plural=count(m[1]) > 1)
        return {"tap": spec, "count": count(m[1]), "other": m[1].lower() == "another"} if spec else None
    m = re.fullmatch(rf"removes? {_COUNT} (\+1/\+1|-1/-1|[a-z]+) counters? from (?:it|~)", text, re.I)
    if m:
        return {"remove_counter": m[2].lower(), "count": count(m[1])}
    if re.fullmatch(r"exiles? a card from (?:your|their) graveyard", text, re.I):
        return {"exile_gy": {}}
    m = re.fullmatch(r"(?:has|have) (?:~|it) deal (\d+) damage to (?:them|you|him or her)", text, re.I)
    if m:
        return {"damage": int(m[1])}
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
    if any(c.get("it") for c in costs) and not all(e.kind in _HURTS_CONTROLLER for e in effects):
        return None             # "for each counter on it": "it" is the source only when B acts on the source
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
