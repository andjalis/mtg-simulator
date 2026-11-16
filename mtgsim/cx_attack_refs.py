"""Attack triggers whose body acts on the attackers that triggered it (#628):

    Whenever one or more creatures you control attack, they gain indestructible until end of turn.  (Angelic Guardian)
    Whenever you attack with eight or more creatures, those creatures get +4/+4 until end of turn.  (Champions from Beyond)
    Whenever you attack with one or more other creatures with flying, those creatures get +2/+2 ... (Lulu, Wild Hollyphant)
    Whenever you attack with one or more Insects, put a +1/+1 counter on each of them.             (Vrestin)

The body's "they / those creatures / each of them" names the head's description, so the line is rewritten with it:
"..., each other attacking creature you control with flying gets +2/+2 until end of turn." The grammar reads that
as a group of your attacking creatures matching the description, fixed when the trigger resolves; the private
sentence "DECLAREDATTACKERS." after it narrows the group to creatures declared as attackers this turn, so a creature
put onto the battlefield attacking before the trigger resolves (Hero of Bladehold's tokens, myriad) is not one of
"them". The one difference left is a declared attacker that stopped matching the description in response (lost
flying, was removed from combat), which no longer gets the bonus.
Only heads about your own attacking creatures are read; "attack you" and "one or more creatures attack" (anyone's)
stay unread.
"""
from __future__ import annotations

import re

_KW = r"(?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|menace|reach)"
_HEAD = re.compile(
    rf"(Whenever (?:you attack with (?:one or more|\w+ or more) (?P<other1>other )?(?P<what1>creatures|[A-Z][a-z]+s)"
    rf"(?P<with1> with {_KW})?|one or more (?P<other2>other )?creatures you control attack)), (?P<body>.+)")
_VERB = {"get": "gets", "gain": "gains", "have": "has", "can't": "can't", "lose": "loses"}
_SUBJ = re.compile(r"(?:they|those creatures|each of them|each of those creatures) (get|gain|have|can't|lose) (.+)",
                   re.I)
_PUT = re.compile(r"(put [^.]+? on) (?:each of them|each of those creatures|them)\.", re.I)
DECLARED = "DECLAREDATTACKERS"     # cx_group_refs.parse: the group before it is the declared attackers only
_PLURAL = re.compile(r"\b(?:they|them|their|those)\b", re.I)


def _subtype(word: str):
    from .permanent_templates import _CREATURE_SUBTYPES
    one = word[:-1]
    return one if one.lower() in _CREATURE_SUBTYPES else None


def rewrite(line: str) -> str:
    """The line with the attackers named, or the line unchanged."""
    m = _HEAD.fullmatch(line.strip())
    if m is None:
        return line
    if m["what1"]:
        what = "creature" if m["what1"] == "creatures" else _subtype(m["what1"])
        if what is None:
            return line
        desc = f"{m['other1'] or ''}attacking {what} you control{m['with1'] or ''}"
    else:
        desc = f"{m['other2'] or ''}attacking creature you control"
    body = m["body"]
    s = _SUBJ.fullmatch(body.rstrip("."))
    if s:
        if _PLURAL.search(s[2]):
            return line
        return f"{m[1]}, each {desc} {_VERB[s[1].lower()]} {s[2]}. {DECLARED}."
    p = _PUT.fullmatch(body)
    if p and not _PLURAL.search(p[1]):
        return f"{m[1]}, {p[1]} each {desc}. {DECLARED}."
    return line
