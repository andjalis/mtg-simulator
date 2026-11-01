"""Delayed actions "at the beginning of the next end step":

    Exile it at the beginning of the next end step.                    (a token, a reanimated creature, the target)
    At the beginning of the next end step, sacrifice it.               Its controller sacrifices it at ...
    Sacrifice them / the tokens / those tokens / the Devil tokens at the beginning of the next end step.
    Destroy ~ at the beginning of the next end step.                   Destroy that creature at ...
    Return it to its owner's hand at the beginning of the next end step.   Return that creature to your hand ...
    Return it to the battlefield tapped under its owner's control at the beginning of the next end step.
    At the beginning of the next end step, return that card to the battlefield ... with a +1/+1 counter on it.
    Discard three cards at the beginning of the next end step.         (any whole sentence the parser reads)

The rider turns the sentence into ``cx_delay``, which, as the ability resolves, picks the objects and puts a
``cx_delayed_do`` on ``game.delayed_end_step`` with them as context. "It" is the ability's last target, or else the
newest permanent that entered while the ability resolved (a token, a reanimated or put-onto-the-battlefield card);
"them" and "the tokens" are all the permanents that entered while it resolved. A returned card is the exiled card
of the target (or of ~); it comes back only if it is still in exile."""
from __future__ import annotations

import re

_WHEN = r"at the beginning of (?:the|your) next end step"
_ONE = (r"it|~|this creature|that creature|that token|the token|that card|the creature|that artifact|the artifact|"
        r"that permanent|that vehicle|that dragon|the exiled card")
_MANY = r"them|the tokens|those tokens|the [a-z]+ tokens"
_SUBJ = rf"(?P<s>{_ONE}|{_MANY})"
_ACTIONS = [
    (re.compile(rf"(?P<op>exile|sacrifice|destroy) {_SUBJ}", re.I), None),
    (re.compile(r"its controller (?P<op>sacrifices) (?P<s>it|that creature)", re.I), None),
    (re.compile(rf"return {_SUBJ} to (?:its owner's|your|their owner's|their owners') hand", re.I), "hand"),
    (re.compile(r"return (?P<s>it|~|that card|the exiled card) to the battlefield(?P<tapped> tapped)?"
                r"(?: under (?:its owner's|your) control)?(?: tapped)?(?P<counter> with a \+1/\+1 counter on it)?",
                re.I), "battlefield"),
]


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _who(subject: str) -> str:
    subject = subject.lower()
    if subject in ("~", "this creature"):
        return "self"
    if re.fullmatch(_MANY, subject):
        return "fresh"
    return "prev"


def action(text: str):
    """The cx_delay effect for one action sentence (without the timing words), or None."""
    text = text.strip().rstrip(".")
    for rx, op in _ACTIONS:
        m = rx.fullmatch(text)
        if not m:
            continue
        data = {"op": op or m["op"].lower().rstrip("s"), "who": _who(m["s"])}
        if op == "battlefield":
            data["tapped"] = bool(m["tapped"])
            data["counter"] = bool(m["counter"])
            if data["who"] == "fresh":
                return None
        return _effect("cx_delay", data=data)
    return None


_HASTE = re.compile(r"(?:it|the creature|the artifact|that [a-z]+) gains haste(?: until end of turn)?", re.I)


_BUSY = False


def parse_rider(sentence: str, effects: list) -> bool:
    """"<action> at the beginning of the next end step" or "At the beginning of the next end step, <action>".

    Also "That creature gains haste." after an untargeted put-onto-the-battlefield effect (Sneak Attack): the newest
    permanent that entered while the ability resolved gains haste."""
    global _BUSY
    s = sentence.strip().rstrip(".")
    if _BUSY or not (_HASTE.fullmatch(s) or re.search(_WHEN, s, re.I)):
        return False
    from .cards.parse import _parse_effects
    _BUSY = True
    try:
        new, bad = _parse_effects(s + ".")        # a wording the parser already reads keeps its parse
    finally:
        _BUSY = False
    if new and not bad:
        return False
    if _HASTE.fullmatch(s) and effects and effects[-1].target == "none" and effects[-1].kind not in ("token",
                                                                                                     "copy_token"):
        effects.append(_effect("cx_fresh_grant", data={"keyword": "haste"}))
        return True
    m = re.fullmatch(rf"(?P<a>.+?) {_WHEN}", s, re.I) or re.fullmatch(rf"{_WHEN}, (?P<a>.+)", s, re.I)
    if not m:
        return False
    body = m["a"]
    eff = action(body)
    if eff is None:
        if re.search(r"\b(?:it|them|that|those|this way)\b", body, re.I):
            return False
        new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
        if bad or not new or any(e.target not in ("none", "self", "you", "") for e in new):
            return False
        eff = _effect("cx_delay", data={"op": "effects", "who": "none", "effects": new})
    if effects and effects[-1].kind == "token" and eff.data["op"] in ("exile", "sacrifice") and \
            eff.data["who"] != "self":
        return False                  # the token line's own "end" rider (cards/parse.py)
    effects.append(eff)
    return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _fresh(game, item):
    from .engine.state import Permanent
    start = getattr(item, "cx_start", None)
    if start is None:
        return []
    found = [x for pl in game.players for x in pl.battlefield
             if isinstance(x, Permanent) and (getattr(x, "rules_timestamp", 0) or 0) > start]
    return sorted(found, key=lambda x: x.rules_timestamp)


def schedule(game, p, eff, prev, item):
    from .engine.state import Permanent
    data = eff.data
    op, who = data["op"], data["who"]
    source = item.source if item is not None else None
    if op == "effects":
        game.delayed_end_step.append((p, list(data["effects"]), source, None))
        return
    if op == "battlefield":
        perm = prev if isinstance(prev, Permanent) else source if who != "fresh" else None
        if who == "self":
            perm = source
        if not isinstance(perm, Permanent) or perm in perm.controller.battlefield:
            return
        objs = [perm.front]
    elif who == "self":
        objs = [source] if isinstance(source, Permanent) else []
    elif who == "fresh":
        objs = _fresh(game, item)
    else:
        fresh = _fresh(game, item)
        objs = [prev] if isinstance(prev, Permanent) else fresh[-1:]
    if not objs:
        return
    game.delayed_end_step.append((p, [_effect("cx_delayed_do", data=dict(data))], source, tuple(objs)))


def _return(game, p, card, data):
    owner = getattr(card, "owner", None) or p
    if card not in owner.exile:
        return
    owner.exile.remove(card)
    perm = game.enter_battlefield(owner, card, tapped=data.get("tapped", False),
                                  counters={"+1/+1": 1} if data.get("counter") else None)
    if perm is not None:
        game.log(f"{card.name} returns to the battlefield", owner)


def act(game, p, eff, item):
    from .engine.state import Permanent
    data = eff.data
    objs = item.context if item is not None and isinstance(item.context, tuple) else ()
    op = data["op"]
    for obj in objs:
        if op == "battlefield":
            _return(game, p, obj, data)
            continue
        if not isinstance(obj, Permanent) or obj not in obj.controller.battlefield:
            continue
        if op == "exile":
            game.leave_battlefield(obj, "exile")
        elif op == "sacrifice":
            game.sacrifice(obj)
        elif op == "destroy":
            game.destroy(obj)
        elif op == "hand":
            game.leave_battlefield(obj, "hand")


def fresh_grant(game, p, eff, prev, item):
    from .engine.state import Permanent
    perm = prev if isinstance(prev, Permanent) else (_fresh(game, item)[-1:] or [None])[0]
    if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
        game.resolve(p, _effect("grant", data={"keyword": eff.data["keyword"]}), perm, item)
