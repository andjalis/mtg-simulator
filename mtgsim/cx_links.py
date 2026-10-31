"""Linked results: "You may <action>. If you do, <reward>." (and "If you don't, ...") for any action the
effect templates already parse, not only the fixed sacrifice/discard/pay gates.

The parser emits ``link_start`` (decides whether the optional action is taken and snapshots the game),
the action's own effects gated on ``lib:["link_taken"]``, then ``link_check``, which sets ``item.gate_paid``
when the action was taken *and* changed the game. That is the outcome record behind "if you do": a
sacrifice with nothing to sacrifice, an exile whose target left, or a mill of an empty library doesn't
pay out. The reward sentence keeps the existing ``paid`` / ``!paid`` conditions.

Simplification: whether the AI takes the action is a small heuristic (``decide``): costs are paid when
they are cheap (a spare permanent to sacrifice, two or more cards to discard, at least 8 life), every
other action is taken.
"""
from __future__ import annotations

import dataclasses
import re


TAKEN = 'lib:["link_taken"]'
_COSTS = {"sacrifice", "sacrifice_self", "sac_own", "sac_filtered", "tap_own", "discard", "discard_choice",
          "discard_hand", "lose_life", "mill", "damage", "drain", "destroy", "exile", "exile_permanent", "wrath",
          "bounce"}


def Effect(*args, **kwargs):
    from .cards.model import Effect as _Effect
    return _Effect(*args, **kwargs)
_FOLLOW = re.compile(r"\s*(?:if you do|when you do|if you don't|if you didn't)\b", re.I)


def parse_may_link(s: str, following: str):
    """Effects for "you may ACTION" when the next sentence is "If you do/don't, ...", else None."""
    if not _FOLLOW.match(following or ""):
        return None
    m = re.fullmatch(r"you may (.+)", s, re.I)
    if not m:
        return None
    from .cards import _parse_effects
    body = m[1]
    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if bad or not new:
        new, bad = _parse_effects("You " + body + ".")
    if bad or not new or any(e.cond or e.kind in ("pay_gate", "link_start") for e in new):
        return None
    if not any(e.kind in _COSTS for e in new):
        return None             # the plain "you may" gate (always taken) already covers it
    kinds = tuple(e.kind for e in new)
    return ([Effect("link_start", data={"kinds": kinds})] + [dataclasses.replace(e, cond=TAKEN) for e in new]
            + [Effect("link_check")])


def decide(game, p, kinds) -> bool:
    """Whether the AI takes a "you may" action that a reward depends on."""
    from .engine.policy import perm_value
    if ("sac_own" in kinds or "sac_filtered" in kinds) and not any(x.card.is_token or (not x.card.is_land and perm_value(x) <= 2)
                                        for x in p.battlefield):
        return False
    if ("discard" in kinds or "discard_choice" in kinds or "discard_hand" in kinds) and len(p.hand) < 2:
        return False
    if "lose_life" in kinds and p.life < 8:
        return False
    return True


def snapshot(game):
    """A cheap fingerprint of everything an action can change."""
    out = [len(game.stack)]
    for pl in game.players:
        out += [pl.life, len(pl.hand), len(pl.library), len(pl.graveyard), len(pl.exile),
                tuple(sorted(pl.counters.items())),
                tuple((id(x), x.tapped, tuple(sorted(x.counters.items())), x.attached_to is not None)
                      for x in pl.battlefield)]
    return tuple(out)


# ---------------------------------------------------------------------------
# Actions that "you may ... If you do" leads use as costs
# ---------------------------------------------------------------------------

_NUM = r"(?:a|an|one|two|three|four|five|\d+)"


def _sacrifice(m):
    from .cx_condlib import _filter
    other = m["q"].lower() == "another"
    spec = _filter(m["f"], plural=False)
    if spec is None or not (set(spec) - {"other"}):
        return None
    spec = dict(spec, other=True) if other else spec
    return Effect("sac_filtered", data={"spec": spec})


def _tap_own(m):
    from .cx_condlib import _filter, _n
    spec = _filter(m["f"], plural=_n(m["n"]) > 1)
    if spec is None:
        return None
    if m["other"]:
        spec = dict(spec, other=True)
    return Effect("tap_own", amount=_n(m["n"]), data={"spec": spec})


EFFECT_PATTERNS = [
    (r"sacrifice (?P<q>a|an|another) (?P<f>(?!creature$|land$)[\w ,/-]+?)", _sacrifice),
    (rf"tap (?P<n>{_NUM}) (?P<other>other )?untapped (?P<f>[\w ,/-]+?) you control", _tap_own),
    (r"tap (?P<n>another|an?) (?P<other>)untapped (?P<f>[\w ,/-]+?) you control",
     lambda m: _tap_own({"n": "one", "f": m["f"], "other": "other"} if m["n"] == "another" else
                        {"n": "one", "f": m["f"], "other": ""})),
    (r"pay (?P<n>\d+) life", lambda m: Effect("lose_life", amount=int(m["n"]))),
]


# ---------------------------------------------------------------------------
# "Look at the top card of your library. If it's a land card, put it onto the battlefield. Otherwise, ..."
# ---------------------------------------------------------------------------

_PEEK = re.compile(r"(?P<how>look at|reveal) the top card of your library", re.I)
_REF_IF = re.compile(r"if (?:it's|it is|that card is) (?:a|an) (?P<f>[\w ,/-]+?) card, (?P<body>.+)", re.I)
_OTHERWISE = re.compile(r"otherwise, (?P<body>.+)", re.I)
_REF_BODY = re.compile(r"(?:you may )?(?:reveal it and )?put (?:it|that card) (?P<dest>into your hand|onto the battlefield"
                       r"(?: tapped)?(?: under your control)?|into your graveyard|on the bottom of your library)", re.I)


def _ref_body(body: str):
    from .cards import _parse_effects
    m = _REF_BODY.fullmatch(body.strip().rstrip("."))
    if m:
        dest = m["dest"].lower()
        where = ("hand" if "hand" in dest else "battlefield" if "battlefield" in dest else
                 "graveyard" if "graveyard" in dest else "bottom")
        return [Effect("ref_move", data={"to": where, "tapped": "tapped" in dest})]
    new, bad = _parse_effects(body[0].upper() + body[1:].rstrip(".") + ".")
    if bad or not new or any(e.cond for e in new):
        return None
    return new


def _since_peek(effects):
    for i in range(len(effects) - 1, -1, -1):
        if effects[i].kind == "peek_top":
            return effects[i + 1:]
    return None


def parse_ref(s: str, effects):
    """The top-card reveal sequence, sentence by sentence; None when s isn't part of one."""
    m = _PEEK.fullmatch(s)
    if m:
        return [Effect("peek_top", data={"reveal": m["how"].lower() == "reveal"})]
    after = _since_peek(effects)
    if after is None:
        return None
    m = _REF_IF.fullmatch(s)
    if m:
        from .cx_condlib import _filter, _code
        spec = _filter(m["f"].replace(",", "") + " card", plural=False)
        body = _ref_body(m["body"])
        if spec is None or body is None:
            return None
        cond = _code("ref_card", spec)
        return [dataclasses.replace(e, cond=cond) for e in body]
    m = _OTHERWISE.fullmatch(s)
    if m:
        conds = list(dict.fromkeys(e.cond for e in after if e.cond.startswith('lib:["ref_card"')))
        body = _ref_body(m["body"])
        if not conds or body is None:
            return None
        from .cx_condlib import _code
        cond = _code("and", *["!" + c for c in conds])
        return [dataclasses.replace(e, cond=cond) for e in body]
    return None
