"""Counters on several targets at once.

* "Put a <counter> counter on each of up to N [other] target <desc>" (also "N <counter> counters"): N effects with
  distinct targets, each picked from the same description by the selector grammar (``permanent_templates``). Fewer
  legal targets than N is fine ("up to"), as with every optional target.
* "~ enters with X <kind> counters on it." (plain X from the spell, any counter kind): ``etb_named_counters`` with the
  amount -1, which ``enter_battlefield`` reads as the X the permanent was cast with. "where X is ..." variants stay
  unmatched.
* "That player / That opponent / Its controller / You get N poison counters" (``cx_poison``): the player the trigger
  is about (``that_player``), the controller of the previous target (``that_controller``) or the caster.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_COUNTER = r"(?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?)"


def _num(word):
    return int(word) if word.isdigit() else _N[word]


def _singular(desc):
    """"creatures you control" -> "creature you control": the plural noun is the one before any "you control"."""
    head = re.fullmatch(r"(.+?)( you control| an opponent controls| you don't control)?", desc)[1]
    rest = desc[len(head):]
    words = head.split(" ")
    last = words[-1]
    words[-1] = "elf" if last == "elves" else last[:-1] if last.endswith("s") and not last.endswith("ss") else last
    return " ".join(words) + rest


def _each_of_up_to(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    count = _N.get(m[3])
    if count is None:
        return NO_MATCH
    out = []
    for _ in range(count):
        eff = build("add_counter", "up to one " + ("other " if m[4] else "") + "target " + _singular(m[5]),
                    amount=_num(m[1]), data={"counter": m[2], "distinct": True})
        if eff is None or eff.target == "group":
            return NO_MATCH
        out.append(eff)
    return out


# A legendary card's own pronoun: "put a +1/+1 counter on him / her" is "on ~" (never when another object is named).
SUBS = [
    (re.compile(r"(\bput (?:(?:a|an|one|two|three|four|five|x|\d+|that many) )?[^.,]*?counters? on) (?:him|her)\b(?!self)", re.I),
     lambda m: m[1] + " ~" if not re.search(r"target|that |enchanted|equipped|each ", m[1][4:], re.I) else m[0]),
]


def _poison(m):
    from .cards.model import Effect
    who = m[1].lower()
    target = "that_controller" if who == "its controller" else "self_player" if who == "you" else "that_player"
    return Effect("cx_poison", _num(m[2]), target="that_player" if who == "you" else target,
                  data={"who": "you"} if who == "you" else {})


def _per_counters(kind, **kw):
    def build(m):
        from .cards.model import Effect
        return Effect(kind, kw.get("amount", 1), target=kw.get("target", "none"),
                      data={"per": {"what": "ctr:" + m["kind"], "zone": "battlefield"}})
    return build


_ON = r"(?:~|it|this [a-z]+)"
_K = r"(?P<kind>[a-z]+(?:-[a-z]+)?)"
EFFECT_PATTERNS = [
    (rf"draw a card for each {_K} counter on {_ON}", _per_counters("draw")),
    (rf"you gain (\d+) life for each {_K} counter on {_ON}", lambda m: _per_counters("gain_life", amount=int(m[1]))(m)),
    (rf"(?:~|it) deals damage equal to the number of {_K} counters on {_ON} to "
     rf"(?P<t>any target|target creature|target player|target opponent)",
     lambda m: _per_counters("damage", target={"target creature": "creature", "any target": "any"}.get(
         m["t"], "player"))(m)),
    (rf"draw x cards and gain x life, where x is the number of {_K} counters on {_ON}",
     lambda m: [_per_counters("draw")(m), _per_counters("gain_life")(m)]),
    (r"(that player|that opponent|its controller|you) gets? (a|an|one|two|three|four|five|\d+) poison counters?",
     _poison),
    (rf"put (a|an|one|two|three|four|five) ({_COUNTER}) counters? on each of up to (two|three|four|five) "
     rf"(other )?target (.+)", _each_of_up_to),
]


def parse_line(line, extra, type_line=""):
    return entry_x_counters(line, extra) or counter_pt(line, extra, type_line)


def counter_pt(line, extra, type_line=""):
    """"~ / Equipped creature / Enchanted creature gets +N/+N for each <kind> counter on it / ~."."""
    m = re.fullmatch(r"(~|Equipped creature|Enchanted creature) gets ([+-]\d+)/([+-]\d+) for each "
                     r"([a-z]+(?:-[a-z]+)?) counter on (?:it|~|this [a-z]+)\.", line)
    if m is None or extra.get("pt_per"):
        return False
    if (m[1] == "Equipped creature" and "Equipment" not in type_line) or (
            m[1] == "Enchanted creature" and "Aura" not in type_line):
        return False
    extra["pt_per"] = "ctr:" + m[4]
    extra["pt_scale"] = (int(m[2]), int(m[3]))
    return True


def entry_x_counters(line, extra):
    m = re.fullmatch(r"~ enters with x ([a-z]+(?:-[a-z]+)?|[+-]\d+/[+-]\d+) counters on (?:it|him|her)\.", line, re.I)
    if m is None or extra.get("etb_named_counters") or extra.get("etb_counters"):
        return False
    if m[1].lower() == "+1/+1":
        extra["etb_counters"] = -1
    else:
        extra["etb_named_counters"] = (m[1].lower(), -1)
    return True


_W = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _distribute(m):
    """"Distribute N <kind> counters among one, two, or three target creatures": one optional distinct target per
    possible recipient; the first effect splits the N counters over the targets actually chosen (each gets at least
    one, the first ones get the remainder), the rest do nothing."""
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    total = _num(m[1])
    nums = [_W[w] for w in re.findall(r"one|two|three|four|five", m[3])]
    slots = min(total, total if "any number" in m[3] else max(nums))
    out = []
    for i in range(slots):
        eff = build("cx_distribute", "up to one " + ("other " if m[4] else "") + "target " + _singular(m[5]),
                    amount=total, data={"counter": m[2], "distinct": True, "slot": i})
        if eff is None or eff.target == "group":
            return NO_MATCH
        out.append(eff)
    return out


EFFECT_PATTERNS.append(
    (rf"distribute (a|an|one|two|three|four|five) ({_COUNTER}) counters? among (?:up to )?((?:any number of)|"
     rf"(?:(?:one|two|three|four|five)(?:,? (?:or |and )?(?:one|two|three|four|five))*)) (other )?target (.+)",
     _distribute))


def _remove(m):
    """"Remove [a counter / up to N counters / N <kind> counters / all [<kind>] counters] from <permanent(s)>"."""
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    amount, kind = (m[1] or "").lower(), (m[2] or "").lower()
    if m[3] is None and kind in ("", "all"):
        return NO_MATCH
    data = {"counter": kind if kind and kind != "any" else ""}
    if amount == "all":
        data["all"] = True
    n = 1 if amount in ("a", "an", "one", "all", "") else _N.get(amount.replace("up to ", ""), None)
    if n is None:
        n = int(amount.replace("up to ", "")) if amount.replace("up to ", "").isdigit() else None
    if n is None:
        return NO_MATCH
    eff = build("cx_remove_counters", m[4], amount=n, data=data)
    return eff if eff is not None else NO_MATCH


EFFECT_PATTERNS.append(
    (rf"(?:you may )?remove (a|an|one|two|three|four|five|up to (?:one|two|three|four|five)|\d+|all) "
     rf"(?:({_COUNTER}) )?(counters?)(?: of that kind)? from (it|~|target [^,]+|all [^,]+|each [^,]+)", _remove))


def _move(m):
    """"Move [a / N / all / any number of] <kind> counter(s) from <A> onto <B>": A or B is ~, or a target (the first
    target is picked by ``cx_move_src``, which does nothing itself; ``cx_move_counters`` then moves them)."""
    from .cards.model import NO_MATCH, Effect
    from .permanent_templates import build
    amount, kind, src = m[1].lower(), (m[2] or "").lower(), m[3]
    dst = re.sub(r"^(?:a second|one other) ", "another ", m[4]) if m[4].startswith(("a second", "one other")) else m[4]
    every = amount in ("all", "any number of")
    n = 1 if every else _N.get(amount) or (int(amount) if amount.isdigit() else None)
    if n is None or (src == "~" and dst == "~"):
        return NO_MATCH
    data = {"counter": kind if kind != "any" else "", "all": every, "from": "self" if src == "~" else "prev"}
    out = []
    if src != "~":
        eff = build("cx_move_src", src, data={"distinct": True})
        if eff is None or eff.target in ("group", "self", "prev"):
            return NO_MATCH
        out.append(eff)
    if dst == "~":
        out.append(Effect("cx_move_counters", n, target="self", data=data))
    else:
        eff = build("cx_move_counters", dst.replace("another target", "another target"), amount=n,
                    data=dict(data, distinct=True))
        if eff is None or eff.target in ("group", "self", "prev"):
            return NO_MATCH
        out.append(eff)
    return out


EFFECT_PATTERNS.append(
    (rf"(?:you may )?move (a|an|one|two|three|all|any number of) (?:({_COUNTER}) )?counters?(?: of that kind)? "
     rf"from (~|target [^,]+?) onto (~|(?:a second |another |one other )?target [^,]+)", _move))
