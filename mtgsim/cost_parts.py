"""Activated-ability cost forms of the #859 cost slot that the base parsers don't read.

* Or-pair sacrifices: "Sacrifice another creature or an artifact", "Sacrifice an artifact or another creature",
  "Sacrifice another creature or a Treasure / an enchantment / token". They become the base parser's
  ``sacrifice`` cost ("other creature or artifact"), so planning, payment, the AI's victim choice and
  "the sacrificed creature" riders work unchanged. "another" excludes the source itself from both halves;
  that differs from the printed rule only when the source is also of the other half's type (Slaughter-Priest of
  Mogis, an enchantment, could sacrifice itself as "an enchantment" to give itself first strike, which no player
  would do).
* Counted sacrifices of a token subtype: "Sacrifice two Blood tokens", "Sacrifice two Eldrazi Scions"
  (``sac_sub``: N permanents you control with that subtype).
* Counted taps beyond the base rule's range or with "other": "Tap ten untapped Elves you control", "Tap two other
  untapped Halflings you control" (the base ``tap`` kind with ``other``).
* "Remove all / any number of <kind> counters from ~: ... that much damage / for each counter removed this way":
  read as "Remove X <kind> counters from ~: ... X ..." (``face_line``), whose engine removes every one of them and
  binds X to the number removed (#345). For "any number of" that is the AI's choice of all of them.

``face_line`` splits "{3}, {T} or {U}, {T}: <effect>" (the Shards) into two abilities with the same effect: rule
602.1b, either cost may be paid. Anything else stays ignored.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
      "nine": 9, "ten": 10}
_NUM = r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
_KINDS = {"token", "artifact", "creature", "treasure", "food", "land", "enchantment"}    # sacrifice_candidates'
_SUB_TOKENS = {"Blood", "Clue", "Food", "Treasure", "Servo", "Thopter", "Map", "Powerstone", "Incubator", "Gold",
               "Shard", "Junk", "Eldrazi Scion", "Eldrazi Spawn"}
KINDS = ("sac_sub",)


def _or_pair(desc: str):
    """"another creature or an artifact" -> "other creature or artifact", or None."""
    m = re.fullmatch(r"(another|an?) (\w+) or (?:(another|an?) )?(\w+)", desc)
    if not m or m[1] == m[3] == "another" or m[2].lower() == m[4].lower():
        return None
    other = "another" in (m[1], m[3])
    what = f"{m[2]} or {m[4]}"
    from .permanent_templates import selector
    if not ({m[2].lower(), m[4].lower()} <= _KINDS or selector(what) is not None):
        return None
    return ("other " if other else "") + what


def parse_part(part: str, extra: dict) -> bool:
    """One cost part (the last fallback of cx_costs.parse_part); True when it was read into ``extra``."""
    m = re.fullmatch(r"Sacrifice (.+)", part)
    if m and "sacrifice" not in extra:
        what = _or_pair(m[1])
        if what is not None:
            extra["sacrifice"] = what
            return True
    m = re.fullmatch(rf"Sacrifice {_NUM} ([A-Z][a-z]+(?: [A-Z][a-z]+)?)(?: tokens|s)", part)
    if m and _N[m[1]] >= 2 and m[2] in _SUB_TOKENS:
        extra["cx_costs"] = extra.get("cx_costs", ()) + (("sac_sub", _N[m[1]], {"sub": m[2]}),)
        return True
    m = re.fullmatch(rf"Tap {_NUM} (other )?untapped ([\w -]+?) you control", part)
    if m and (m[2] or _N[m[1]] > 7):
        from .cx_condlib import _filter
        n = _N[m[1]]
        spec = _filter(m[3], plural=n > 1)
        if spec is None:
            return False
        if m[2]:
            spec = dict(spec, other=True)
        extra["cx_costs"] = extra.get("cx_costs", ()) + (("tap", n, spec),)
        return True
    return False


# ---------------------------------------------------------------- engine side (cx_costs dispatch)

def _sub_pool(p, perm, spec):
    from .engine.policy import perm_value
    sub = spec["sub"]
    return sorted((x for x in p.battlefield if x is not perm and
                   (sub in x.card.subtypes or " ".join(sorted(x.card.subtypes)) == " ".join(sorted(sub.split())))),
                  key=perm_value)


def payable(game, p, perm, kind, n, spec) -> bool:
    return len(_sub_pool(p, perm, spec)) >= n


def pay_one(game, p, perm, kind, n, spec) -> bool:
    pool = _sub_pool(p, perm, spec)
    if len(pool) < n:
        return False
    for x in pool[:n]:
        game.sacrifice(x)
    return True


# ---------------------------------------------------------------- "<cost A> or <cost B>: <effect>"

_REMOVE = re.compile(r"(?P<cost>[^:\"]*\bRemove (?:all|X|any number of) (?P<k>[\w/+-]+) counters from ~)(?P<rest>: .+)")


def _removed_amount(line: str) -> str:
    """"Remove all <k> counters from ~: ... that much damage / -1/-1 for each <k> counter removed this way": the
    number removed is the ability's X, the same quantity "Remove X <k> counters from ~" already binds (#345)."""
    m = _REMOVE.fullmatch(line)
    if not m:
        return line
    k, rest = re.escape(m["k"]), m["rest"]
    rest = re.sub(rf", where X is the number of {k} counters removed this way\.", ".", rest)
    rest = re.sub(r"\b(deals|loses) that much (damage|life)\b", r"\1 X \2", rest)
    rest = re.sub(rf"gets -1/-1 until end of turn for each {k} counter removed this way\.",
                  "gets -X/-X until end of turn.", rest)
    cost = re.sub(r"Remove (?:all|any number of) ", "Remove X ", m["cost"])     # all: the engine removes every one
    new = cost + rest
    if new == line:
        return line
    from .cards.parse import _parse_ability
    body = re.sub(r"^[A-Z][\w' ]* — ", "", new)
    return new if _parse_ability(body, []) is not None else line


_OR_COST = re.compile(r"((?:\{[^}]+\}, )*\{[^}]+\}) or ((?:\{[^}]+\}, )*\{[^}]+\}): (.+)")


def face_line(st, line):
    """Two abilities for "{3}, {T} or {U}, {T}: <effect>" (Crystal Shard); the line unchanged otherwise."""
    line = _removed_amount(line)
    m = _OR_COST.fullmatch(line)
    if not m:
        return line
    from .cards.parse import _parse_ability
    parsed = [_parse_ability(f"{cost}: {m[3]}", st.approximations) for cost in (m[1], m[2])]
    if any(a is None for a in parsed):
        return line
    st.activated += parsed
    return None
