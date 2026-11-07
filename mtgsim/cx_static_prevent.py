"""Static damage prevention over a source filter and a protected subject, optionally gated by a condition:

    If a red source would deal damage to you, prevent 2 of that damage.                  (Sphere of Fire)
    If an artifact would deal damage to you, prevent 2 of that damage.                   (Sphere of Purity)
    If a source would deal damage to you or a creature you control, prevent 1 of that damage.
    If a source would deal damage to a planeswalker you control, prevent 1 of that damage.
    As long as ~ is untapped, if a creature would deal combat damage to you, prevent 2 of that damage.
    During your turn, prevent all damage that would be dealt to ~.
    As long as you control a permanent of each color, prevent all damage that would be dealt to you.
    Prevent all noncombat damage that would be dealt to you and creatures you control.
    Prevent all combat damage that would be dealt to and dealt by ~.                     (Fog Bank)

Each line becomes ``cx_shields`` static rules (``advanced_rules["cx_prevent"]``), one per protected subject ("you or
a creature you control" is two rules), so prevention, "N of that damage" and the damage pipeline are the shields'
own. Two keys are added: ``cond`` (a ``cx_condlib`` code read from the static's source) and ``during`` ("yours" or
"not_yours"); ``gate_ok`` checks them from ``cx_shields._applies``. Lines ``cx_shields`` already reads never reach
this module (its hook runs later in the line parser).
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_PRE = r"(?:(?P<pre>During your turn|During turns other than yours|As long as (?P<al>.+?)), )?"
_COMBAT = r"(?P<c>combat |noncombat )?"
_IF = re.compile(rf"{_PRE}[Ii]f (?P<by>.+?) would deal {_COMBAT}damage to (?P<to>.+?), prevent (?:(?P<n>\d+) of )?that "
                 r"damage\.")
_IF_DEALT = re.compile(rf"{_PRE}[Ii]f {_COMBAT}damage would be dealt to (?P<to>.+?), prevent that damage\.")
_ALL = re.compile(rf"{_PRE}[Pp]revent all {_COMBAT}damage that would be dealt to (?P<to>.+?)(?: by (?P<by>.+?))?\.")
_BOTH = re.compile(rf"{_PRE}[Pp]revent all {_COMBAT}damage that would be dealt to and dealt by (?P<to>.+?)\.")
_BY_WORDS = {"a source": ("any",), "a source an opponent controls": ("opp",), "a source you don't control": ("opp",)}


def _by(text: str):
    """The source filter for "a red source", "an artifact", "a creature", "red sources", ..., or None."""
    text = text.strip()
    if text.lower() in _BY_WORDS:
        return _BY_WORDS[text.lower()]
    m = re.fullmatch(r"an? (white|blue|black|red|green) source", text, re.I)
    if m:
        return "group", {"colors": [_COLORS[m[1].lower()]]}
    m = re.fullmatch(r"an? (creature|artifact)", text, re.I)
    if m:
        return "group", {"types_all": [m[1].lower()]}
    from .cx_shields import _subject
    got = _subject(text, True)
    return got[0] if got and got[0][0] in ("group", "any", "you", "self", "host") else None


def _to(text: str):
    """Protected subjects: one per "A or B" / "A and B" part, or None."""
    from .cx_shields import _subject
    from .permanent_templates import selector
    parts = re.split(r" or | and |, ", text.strip())
    out = []
    for part in parts:
        low = part.lower()
        if low in ("you", "~", "enchanted creature", "equipped creature"):
            out.append(_subject(part, True)[0])
            continue
        spec = selector(part, plural=not re.match(r"(?:a|an|another) ", low))
        if spec is None or set(spec) - {"controller", "types_all", "subtypes", "other", "colors"}:
            return None
        out.append(("group", spec))
    return out or None


def parse_line(line: str, st) -> bool:
    both = _BOTH.fullmatch(line)
    m = both or _IF.fullmatch(line) or _IF_DEALT.fullmatch(line) or _ALL.fullmatch(line)
    if not m or not st.types or "Instant" in st.types or "Sorcery" in st.types or st.level_marks or \
            st.extra.get("_lvl_blocks"):
        return False        # a spell's one-shot line, or a Class / level-up ability that only applies at its level
    g = m.groupdict()
    by = _by(g["by"]) if g.get("by") else ("any",)
    to = _to(g["to"])
    if by is None or not to:
        return False
    gate: dict = {}
    pre = (g["pre"] or "").lower()
    if pre in ("during your turn", "during turns other than yours"):
        gate["during"] = "yours" if pre == "during your turn" else "not_yours"
    elif g["al"]:
        from .cx_condlib import as_static
        code = as_static(g["al"])
        if not code:
            return False
        gate["cond"] = code
    combat = {"combat ": True, "noncombat ": False}.get(g["c"])
    if both:
        gate["both"] = True             # damage dealt to it and damage dealt by it
    rules = tuple(dict({"combat": combat, "to": subject, "by": by}, **gate, **({"n": int(g["n"])} if g.get("n") else {}))
                  for subject in to)
    adv = st.extra.setdefault("advanced_rules", {})
    adv["cx_prevent"] = adv.get("cx_prevent", ()) + rules
    return True


def gate_ok(game, rule) -> bool:
    """cx_shields._applies: a static rule's "during your turn" / "as long as" gate."""
    turn = rule.get("during")
    if turn and (game.active is rule["owner"]) != (turn == "yours"):
        return False
    code = rule.get("cond")
    if code:
        from .cx_condlib import holds_for
        return bool(holds_for(rule["src"], code))
    return True
