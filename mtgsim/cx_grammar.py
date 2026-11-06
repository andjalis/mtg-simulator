"""Compositional effect grammar: the fallback for sentences no template matches.

A sentence is read as subject + verb chain + duration and mapped onto the engine's existing effect kinds:

    Target creature you control gets +2/+0 and gains first strike until end of turn.
    Until end of turn, attacking creatures you control get +1/+0 and gain trample.
    Goblin creatures you control get +1/+1 and gain haste until end of turn.
    Target red or green creature loses flying and becomes black until end of turn.
    Up to two target creatures each get +1/+0 and gain menace until end of turn.
    Creatures target player controls can't block this turn.
    You may have target creature gain flying until end of turn.

Subjects: "~", "it" / "that creature", "[up to] N|one [other] target <noun phrase>", groups ("each/all <noun
phrase>", "<qualifiers> creatures|Zombies [you control] [with ...]") and "creatures target player controls". A
noun phrase is read by ``permanent_templates.selector`` or, failing that, by the trigger grammar's
``cx_events._object_subject`` (colour and type alternatives, "with/without ...", controller), whose matcher the
engine already uses for ``cx_desc`` targets. Verbs: gets +N/+N, gains / loses keywords, becomes COLOR (layer 5),
has base power and toughness N/N, can't attack / block / be blocked, attacks or blocks this combat if able.
Durations: "until end of turn" (prefix or suffix), or "this turn" / "this combat" for the restrictions; "until
your next turn" reaches here already rewritten by ``cx_next_turn``. A colour change with no duration is permanent.
Every word must be understood: anything else returns None, so the sentence stays ignored.
"""
from __future__ import annotations

import re

from .permanent_templates import _SUBTYPE_TYPES, keywords, selector

_SUBTYPE_NAMES = frozenset(_SUBTYPE_TYPES)

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_NUMBER = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_EOT = r"until end of turn"
_RESTRICT = {"can't block": "cant_block_now", "can't attack": "cant_attack_now", "can't be blocked": "unblockable",
             "attack": "must_attack_now", "block": "must_block_now"}
_VERB = r"(?:gets?|gains?|loses?|becomes?|has|have|can't|attacks?|blocks?)"
_SPLIT = re.compile(rf"(?:,? and |, )(?=(?:also )?{_VERB}\b)", re.I)
_PLURAL = r"\b(?:creatures|permanents|lands|artifacts|enchantments|[A-Z][a-z]+s|Elves|Dwarves|Wolves)\b"


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _desc(text: str, plural: bool):
    """A cx_events object spec for a noun phrase, or None (no self / host / other readings)."""
    from .cx_events import _object_subject
    first = text.split(" ", 1)[0]
    if first[:1].isupper() and _subtype(first) not in _SUBTYPE_TYPES:
        text = first.lower() + text[len(first):]            # sentence-initial capital, not a subtype
    spec = _object_subject(("one or more " if plural else "a ") + text)
    if spec is None or spec["self"] or spec["host"] or spec["other"]:
        return None
    # The trigger grammar reads any capitalised word as a subtype: only real subtypes count here.
    if any(w[:1].isupper() and _subtype(w) not in _SUBTYPE_TYPES for alt in spec["alts"] for w in alt):
        return None
    return spec


def _subtype(word: str) -> str:
    from .cx_events import _IRREGULAR
    word = _IRREGULAR.get(word, word)
    low = word.lower()
    return low if low in _SUBTYPE_NAMES or not low.endswith("s") or low.endswith("ss") else low[:-1]


def _noun(text: str, plural: bool):
    """{"selector": ...} or {"cx_desc": ...} for a noun phrase, or None."""
    spec = selector(text, plural=plural)
    if spec is not None:
        return {"selector": spec}
    other = re.match(r"(?:other|another) ", text, re.I)
    rest = text[other.end():] if other else text
    if _desc(rest, plural) is None:
        return None
    return dict({"cx_desc": rest, "plural": plural}, **({"other": True} if other else {}))


def _singular(text: str) -> str:
    """"creatures you control" -> "creature you control" (the noun phrase of "N target creatures")."""
    return re.sub(r"\b(creature|permanent|artifact|land|enchantment)s\b", r"\1", text, count=1)


def subject(text: str):
    """(target, data, copies, group) for a subject phrase, or None.

    target is an Effect target; copies > 1 for "N target creatures each"; group is a cx_group data dict for a
    subject naming a set of permanents (target is then "none", or "player" for "creatures target player controls").
    """
    text = text.strip()
    low = text.lower()
    if low in ("~", "this creature", "this permanent"):
        return "self", {}, 1, None
    if low in ("it", "that creature", "that permanent"):
        return "prev", {}, 1, None
    m = re.fullmatch(r"creatures target (player|opponent) controls", low)
    if m:
        return "player", ({"filter": "opp"} if m[1] == "opponent" else {}), 1, {"selector": {"types_all": ["creature"]}}
    m = re.fullmatch(r"(?:(up to) )?(?:(a|one|two|three|four|five) )?(other |another )?target (.+?)( each)?", text, re.I)
    if m and not (m[1] and not m[2]):
        n = _NUMBER[m[2].lower()] if m[2] else 1
        if n == 1 and m[5]:
            return None
        noun = _noun(_singular(m[4]) if n > 1 else m[4], plural=False)
        if noun is None or n > 1 and _singular(m[4]) == m[4]:
            return None
        data = {k: v for k, v in noun.items() if k != "plural"}
        if m[3]:
            data["other"] = True
        if m[1]:
            data["optional_target"] = True
        if n > 1:
            data["distinct"] = True
        return "permanent", data, n, None
    m = re.fullmatch(r"(each|all) (.+)", text, re.I)
    words = m[2] if m else text
    if not m and not re.search(_PLURAL, words):
        return None         # a bare singular noun phrase is not a subject
    noun = _noun(words, plural=not (m and m[1].lower() == "each"))
    if noun is None:
        return None
    return "none", {}, 1, noun


def _keyword_list(text: str):
    kws = keywords(text.strip())
    if kws:
        return kws
    m = re.fullmatch(r"protection from (\w+)(?:,? and from (\w+))?", text.strip(), re.I)      # "... and from blue"
    if m:
        from .cards.model import KEYWORDS
        out = [f"protection from {c.lower()}" for c in m.groups() if c]
        return out if all(k in KEYWORDS for k in out) else None
    return None


def _colors(text: str):
    text = text.lower().strip()
    if text == "colorless":
        return frozenset()
    parts = re.split(r",? and |, ", text)
    if any(p not in _COLORS for p in parts):
        return None
    return frozenset(_COLORS[p] for p in parts)


def verb(text: str, timed: bool):
    """[(kind, amount, amount2, data)] for one verb phrase, or None. timed: an until-end-of-turn duration applies.

    A restriction phrase carries its own " this turn" / " this combat" when the sentence ends that way."""
    t = re.sub(r"^also ", "", text.strip().lower())
    m = re.fullmatch(r"gets? ([+-]\d+)/([+-]\d+)", t)
    if m and timed:
        p, q = int(m[1]), int(m[2])
        if p <= 0 and q <= 0:
            return [("debuff_one", -p, -q, {})]
        return [("pump", p, q, {})]
    m = re.fullmatch(r"gains? (.+)", t)
    if m and timed:
        kws = _keyword_list(m[1])
        return [("grant", 0, 0, {"keyword": k}) for k in kws] if kws else None
    m = re.fullmatch(r"loses? (.+)", t)
    if m and timed:
        kws = _keyword_list(m[1])
        return [("cx_lose_kw", 0, 0, {"keyword": k, "side": "theirs"}) for k in kws] if kws else None
    m = re.fullmatch(r"becomes? (.+?)( in addition to its other colors)?", t)
    if m:
        cols = _colors(m[1])
        if cols is None or not cols and m[2]:
            return None
        op = "add_colors" if m[2] else "set_colors"
        return [("cx_color", 0, 0, {"colors": "".join(sorted(cols)), "op": op, "eot": timed, "side": "theirs"})]
    m = re.fullmatch(r"(?:has|have) base power and toughness (\d+)/(\d+)", t)
    if m and timed:
        return [("cx_set_base", int(m[1]), int(m[2]), {})]
    m = re.fullmatch(r"(can't attack or block|can't block|can't attack|can't be blocked)( this turn| this combat)?", t)
    if m and (timed or m[2]):
        words = ["can't attack", "can't block"] if m[1] == "can't attack or block" else [m[1]]
        return [("cx_temp_kw", 0, 0, {"keywords": frozenset({_RESTRICT[w]}),
                                      "side": "mine" if w == "can't be blocked" else "theirs"}) for w in words]
    m = re.fullmatch(r"(attack|block)s? this (?:turn|combat) if able", t)
    if m:
        return [("cx_temp_kw", 0, 0, {"keywords": frozenset({_RESTRICT[m[1]]}), "side": "theirs"})]
    return None


def parse_sentence(s: str):
    """Effects for one whole sentence, or None."""
    s = s.strip().rstrip(".").strip()
    s = re.sub(r"^(?:then |you may have |have )", "", s, flags=re.I)
    timed = False
    m = re.fullmatch(rf"{_EOT}, (.+)", s, re.I)
    if m:
        s, timed = m[1], True
    m = re.fullmatch(rf"(.+) {_EOT}", s, re.I)
    if m:
        if timed:
            return None
        s, timed = m[1], True
    restrict = ""
    m = re.fullmatch(r"(.+?)( this turn| this combat)", s, re.I)
    if m and not timed and not re.search(r"\bif able$", s, re.I):
        s, restrict = m[1], m[2].lower()
    head = re.match(rf"(.+?) ((?:also )?{_VERB}\b.*)", s, re.I)
    if head is None:
        return None
    subj = subject(head[1])
    if subj is None:
        return None
    target, data, copies, group = subj
    built = []
    for part in _SPLIT.split(head[2]):
        if restrict and not re.match(r"(?:also )?can't", part, re.I):
            return None
        effs = verb(part + restrict, timed)
        if effs is None:
            return None
        built += effs
    if group is not None:
        inner = [_effect(k, a, b, target="self", data=d) for k, a, b, d in built]
        return [_effect("cx_group", target=target, data=dict(data, group=group, effects=inner))]
    out = []
    for _ in range(copies):
        for i, (k, a, b, d) in enumerate(built):
            if i == 0:
                out.append(_effect(k, a, b, target=target, data=dict(data, **d)))
            else:
                out.append(_effect(k, a, b, target="prev" if target == "permanent" else target, data=d))
    return out


def group_members(game, p, data, source, player=None):
    """The permanents a cx_group names, fixed as the effect resolves (CR 611.2c)."""
    from .permanent_templates import matches
    group = data["group"]
    pool = player.battlefield if player is not None else [x for pl in game.players for x in pl.battlefield]
    if "selector" in group:
        return [x for x in pool if matches(game, x, group["selector"], p, source)]
    from .cx_events import _obj_match
    spec = _desc(group["cx_desc"], group["plural"])

    class _Viewer:              # _obj_match reads "you control" from the viewer's controller
        controller = p
        power = getattr(source, "power", 0)
    return [x for x in pool if not (group.get("other") and x is source) and _obj_match(game, spec, _Viewer, x)]


def parse_fallback(s: str, effects: list) -> bool:
    """The _parse_effects hook: append the sentence's effects and return True, or return False."""
    new = parse_sentence(s)
    if not new:
        return False
    effects += new
    return True
