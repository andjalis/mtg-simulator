"""Referent-bound conditions for the "if <condition>," slot (#405): facts about the referenced object.

    If that creature has infect, ~ deals 3 damage to that creature's controller.
    If it was a Locus or Sphere land, put a +1/+1 counter on ~.
    If that spell has mana value 5 or greater, put a +1/+1 counter on ~.
    put a +1/+1 counter on that creature if its power is less than ~'s power.
    if it's not a token, ... / if it's renowned, ... / if that land was nonbasic, ...

The referent is bound by an explicit rule, never guessed: "it / that creature / that permanent / that land"
is the event object of the trigger or the previous effect's object (``prev``, then the resolving item's
``context``), "that spell" is the triggering or targeted spell (a ``StackItem``), "that card" is the card
the previous effect moved, exiled or revealed (``exiled_card`` / ``moved_card`` / ``link_card``).

The rules are ``RULES`` that ``cx_condlib`` appends to its phrase rules (after its own and cx_static_cond's,
so nothing already read changes meaning), and ``check`` evaluates their ``lib:`` codes from
``cx_condlib.check``. Predicates are read by the shared noun-phrase reader (``cx_condlib._filter``); a
predicate it doesn't know keeps the whole condition unread. Comparisons on the referent's power,
toughness or mana value against a number or against ~'s stat use the ``ref_stat`` / ``ref_stat_vs`` kinds.
"""
from __future__ import annotations

import re

_NUM = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twenty)"
_REF = r"(?P<ref>it|that creature|that card|that permanent|that land|that spell)"
# words that make a predicate a fact about something else, never a noun phrase about the referent
_NOT_A_FILTER = r"(?:turn|phase|step|time|graveyard|hand|library|exile|stack|battlefield)"

RULES: list = []


def rule(pattern: str):
    def deco(fn):
        RULES.append((pattern, fn))
        return fn
    return deco


def _refname(m) -> str:
    """"spell" for "that spell"; "prev" for "it" (which may also be the source itself: "When ~ dies, if it isn't
    a token"); "that" for "that creature / card / permanent / land", which never names the source. ("it" itself
    would be stripped as the legacy source-referent marker by cx_condlib.check.)"""
    ref = (m["ref"] or "it").lower()
    return {"that spell": "spell", "that card": "card", "it": "prev"}.get(ref, "that")


def _op(d: str) -> str:
    return ">=" if d.lower() in ("greater", "more") else "<="


def _or_list(f: str):
    """("A land", "B land") for "A or B land", else None."""
    m = re.fullmatch(r"([A-Za-z'-]+) or (?:a |an )?([A-Za-z'-]+)( .+)?", f)
    return (m[1] + (m[3] or ""), m[2] + (m[3] or "")) if m else None


def _specs(f: str):
    """The noun-phrase specs of a predicate: one, or two for an "A or B <noun>" list, or None."""
    from .cx_condlib import _filter
    f = f.replace(",", "").strip()
    one = _filter(f, plural=False)
    if one is not None:
        return [one]
    pair = _or_list(f)
    if pair:
        a, b = (_filter(part, plural=False) for part in pair)
        if a is not None and b is not None:
            return [a, b]
    return None


@rule(r"(?:its|that (?:creature|card|permanent|land|spell)'s) (?P<w>power|toughness) "
      r"(?:is|was|had) (?P<op>less|greater) than ~'s (?P=w)|"
      r"(?P<ref>it|that creature|that permanent) (?:has|had) (?P<w2>power|toughness) (?:is |was )?"
      r"(?P<op2>less|greater) than ~'s (?P=w2)")
def _stat_vs_src(m):
    """"its power is less than ~'s power" / "it had power greater than ~'s power"."""
    from .cx_condlib import _code
    w = (m["w"] or m["w2"]).lower()
    op = m["op"] or m["op2"]
    ref = "prev" if m[0].lower().startswith(("its ", "it ")) else "that"
    return _code("ref_stat_vs", w, "<" if op.lower() == "less" else ">", "~", w, ref)


@rule(rf"{_REF} has (?P<op>greater|less) (?P<w1>power|toughness)(?: or (?P<w2>power|toughness))? than ~")
def _has_stat_vs_src(m):
    """"that creature has greater power than ~" / "... greater power or toughness than ~"."""
    from .cx_condlib import _code
    op = "<" if m["op"].lower() == "less" else ">"
    codes = [_code("ref_stat_vs", m["w1"].lower(), op, "~", m["w1"].lower(), _refname(m))]
    if m["w2"]:
        codes.append(_code("ref_stat_vs", m["w2"].lower(), op, "~", m["w2"].lower(), _refname(m)))
    return codes[0] if len(codes) == 1 else _code("or", *codes)


@rule(rf"{_REF} has mana value (?P<n>{_NUM}) or (?P<d>less|fewer|greater|more)")
def _has_mv(m):
    """"that spell has mana value 5 or greater" / "it has mana value 3 or less"."""
    from .cx_condlib import _code, _n
    return _code("ref_stat", "mana value", _op(m["d"]), _n(m["n"]), _refname(m))


@rule(rf"{_REF} has (?P<w>power|toughness) (?P<n>{_NUM}) or (?P<d>greater|more|less)")
def _has_stat(m):
    """"that creature has power 7 or greater"."""
    from .cx_condlib import _code, _n
    return _code("ref_stat", m["w"].lower(), _op(m["d"]), _n(m["n"]), _refname(m))


@rule(rf"(?:its|that [\w' ]+?s) (?P<w>power|toughness|mana value) is "
      rf"(?:exactly (?P<n>{_NUM})|(?P<d>greater|less) than (?P<n2>{_NUM}))")
def _stat_exact(m):
    """"its power is exactly 20" / "its power is greater than 0"."""
    from .cx_condlib import _code, _n
    ref = "prev" if m[0].lower().startswith("its ") else "that"
    if m["n"]:
        return _code("ref_stat", m["w"].lower(), "==", _n(m["n"]), ref)
    return _code("ref_stat", m["w"].lower(), ">" if m["d"].lower() == "greater" else "<", _n(m["n2"]), ref)


@rule(rf"{_REF}(?:'s| is| isn't| is not| was| wasn't) (?P<not>not )?(?P<q>a|an) (?P<f>[\w ,/-]+)")
def _ref_is(m):
    """"it isn't a land card" / "that land was a snow land" / "it's a creature spell" / "it was a Locus or
    Sphere land": a noun-phrase predicate of the referent, optionally negated and optionally an "A or B"
    list. The negative form uses ref_not_is, which is false (the effect doesn't fire) when the referent
    cannot be resolved at all."""
    from .cx_condlib import _code
    if re.search(_NOT_A_FILTER, m["f"], re.I):
        return ""
    specs = _specs(m["f"])
    if not specs:
        return ""
    neg = bool(m["not"]) or re.search(r"(?:isn't|is not|wasn't)", m[0], re.I) is not None
    ref = _refname(m)
    if neg:
        codes = [_code("ref_not_is", spec, ref) for spec in specs]
        return _code("and", *codes) if len(codes) > 1 else codes[0]
    kind = "ref_card_is" if ref == "card" else "prev_is"
    codes = [_code(kind, spec) for spec in specs]
    return _code("or", *codes) if len(codes) > 1 else codes[0]


@rule(rf"{_REF} (?:is|was) (?:(?P<c1>white|blue|black|red|green) or (?P<c2>white|blue|black|red|green)|"
      rf"(?P<f>nonbasic|nonlegendary|legendary|snow|basic|tapped|untapped))")
def _ref_bare_adj(m):
    """"that land was nonbasic" / "that card is legendary" / "that permanent was blue or black": a bare
    adjective or colour pair, no article."""
    from .cx_condlib import _code, _filter
    if m["c1"]:
        colors = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
        return _code("ref_card_is" if _refname(m) == "card" else "prev_is", {"any_color": [colors[m["c1"].lower()], colors[m["c2"].lower()]]})
    spec = _filter(m["f"].lower(), plural=False)
    return _code("ref_card_is" if _refname(m) == "card" else "prev_is", spec) if spec else ""


@rule(rf"(?P<ref>it|that creature|that permanent) (?:has|had) (?P<q>no|a|an|one|one or more|{_NUM} or more|{_NUM}) "
      rf"(?P<c>\+1/\+1|-1/-1|\+1/\+0|[a-z]+) counters? on it")
def _ref_counters(m):
    """"it had no counters on it" / "that creature has three or more +1/+0 counters on it"."""
    from .cx_condlib import _code, _quant
    q = m["q"].lower()
    op, n = ("==", 0) if q == "no" else _quant("one" if q in ("a", "an", "one") else q)
    if m["ref"].lower() == "it":
        return _code("counters", m["c"].lower(), op, n, "it")
    return _code("prev_is", {"counters": [m["c"].lower(), op, n]})


@rule(r"(?P<ref>it|that creature|that permanent) (?:has|had) (?P<q>no |a |an |one )?counters? on it")
def _ref_any_counters(m):
    """"it had a counter on it" / "it has no counters on it": any counter at all, read as the library's
    any_counters (the previous effect's object, then the trigger's object, then ~)."""
    from .cx_condlib import _code
    code = _code("any_counters", "it")
    return "!" + code if m["q"] and m["q"].startswith("no") else code


@rule(r"(?P<ref>that card|it|that creature|that permanent)(?:'s| is) (?P<z>on the battlefield|exiled|in your hand|"
      r"in your graveyard|in a graveyard)")
def _ref_zone(m):
    """"that card is exiled" / "that card is on the battlefield": which zone the referent card is in now."""
    from .cx_condlib import _code
    return _code("ref_zone", m["z"].lower(), _refname(m))


@rule(r"(?P<ref>it|that creature|that permanent) is enchanted or equipped")   # not "was": no LKI of attachments
def _ref_ench_equip(m):
    from .cx_condlib import _code
    return _code("or", _code("prev_is", {"state": "enchanted"}), _code("prev_is", {"state": "equipped"}))


@rule(r"(?P<ref>it|that creature)(?:'s| is) (?P<w>renowned|monstrous)")
def _ref_flag(m):
    """"if it's renowned": the renown / monstrosity flag on the referent, not the source."""
    from .cx_condlib import _code
    return _code("ref_flag", m["w"].lower(), _refname(m))


@rule(r"(?P<ref>that creature|that permanent|it) is another (?P<f>[\w -]+)")
def _ref_another(m):
    """"that creature is another Hero": the referent has that type/subtype too and isn't ~ itself (Wakandan
    Royal Guard can target itself)."""
    from .cx_condlib import _code
    specs = _specs(m["f"])
    return _code("and", _code("prev_is", specs[0]), _code("ref_not_src", "that")) \
        if specs and len(specs) == 1 else ""


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

KINDS = {"ref_stat", "ref_stat_vs", "ref_not_is", "ref_flag", "ref_zone", "ref_not_src", "ref_card_is"}


def _ref_obj(item, source, prev, ref):
    """The bound referent: a targeted/trigger object, else the item's context, else the card the previous
    effect moved or revealed, else (for "it" only) the source. "spell" only ever binds a StackItem; "that
    creature / card / ..." never falls back to the source (#356: no guessed referents)."""
    from .engine.state import Permanent, StackItem
    if ref == "card":
        # "that card": the one card the previous effect moved or revealed (referent.remember_card), never a guess
        for attr in ("referent_card", "exiled_card", "moved_card", "link_card"):
            card = getattr(item, attr, None) if item is not None else None
            if card is not None:
                return card
        return None
    cands = [prev, getattr(item, "context", None) if item is not None else None]
    if ref == "spell":
        for o in cands:
            if isinstance(o, StackItem):
                return o
        ts = getattr(item, "target_spell", None) if item is not None else None
        return ts if isinstance(ts, StackItem) else None
    for o in cands:
        if isinstance(o, Permanent):
            return o
    for o in cands:
        if isinstance(o, StackItem):
            return o
    for attr in ("exiled_card", "moved_card", "link_card"):
        card = getattr(item, attr, None) if item is not None else None
        if card is not None:
            return card
    return source if ref == "prev" else None


def _stat(obj, what: str, item=None) -> int:
    from .engine.state import Permanent, StackItem
    if what == "mana value":
        if isinstance(obj, StackItem):
            card = obj.card
            if card is None:
                return 0
            x = getattr(obj, "x", 0)
            return card.cmc + x * (card.mana_cost.get("X", 0) if isinstance(card.mana_cost, dict) else 0)
        if isinstance(obj, Permanent):
            return obj.card.cmc
        return getattr(obj, "cmc", 0)
    if isinstance(obj, Permanent):
        return getattr(obj, what)
    return int(getattr(obj, what, 0) or 0)


def check(game, p, kind, args, item=None, source=None, prev=None):
    """cx_condlib.check for the kinds registered here; None for any other kind."""
    from .cx_condlib import _card_ok, _cmp
    if kind == "ref_stat":
        what, op, n, ref = args
        obj = _ref_obj(item, source, prev, ref)
        return obj is not None and _cmp(_stat(obj, what, item), op, n)
    if kind == "ref_stat_vs":
        what, op, ref2, what2, ref = args
        obj = _ref_obj(item, source, prev, ref)
        other = source if ref2 == "~" else None
        if obj is None or other is None:
            return False
        return _cmp(_stat(obj, what, item), op, _stat(other, what2, item))
    if kind == "ref_not_is":
        from .engine.state import Permanent, StackItem
        spec, ref = args
        obj = _ref_obj(item, source, prev, ref)
        if obj is None:
            return False        # an unresolvable referent: the negative condition doesn't fire
        if isinstance(obj, Permanent):
            return not _card_ok(obj.card, spec, obj)
        if isinstance(obj, StackItem):
            obj = obj.card
        return not (obj is not None and hasattr(obj, "types") and _card_ok(obj, spec))
    if kind == "ref_flag":
        w, ref = args
        obj = _ref_obj(item, source, prev, ref)
        return obj is not None and bool(getattr(obj, w, False))
    if kind == "ref_zone":
        from .engine.state import Permanent
        zone, ref = args
        obj = _ref_obj(item, source, prev, ref)
        if obj is None:
            return False
        if isinstance(obj, Permanent):
            return zone == "on the battlefield" and obj in obj.controller.battlefield
        if zone == "on the battlefield":
            return any(perm.card is obj or perm.card == obj for pl in game.players for perm in pl.battlefield)
        if zone == "exiled":
            return any(obj in pl.exile for pl in game.players)
        if zone == "in your hand":
            return obj in p.hand
        return any(obj in pl.graveyard for pl in game.players)
    if kind == "ref_card_is":
        card = _ref_obj(item, source, prev, "card")
        return card is not None and hasattr(card, "types") and _card_ok(card, args[0])
    if kind == "ref_not_src":
        obj = _ref_obj(item, source, prev, args[0])
        return obj is not None and obj is not source
    return None
