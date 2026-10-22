"""Static abilities of a permanent that change other creatures: general anthems and keyword grants.

    Other creatures you control have trample.         Attacking creatures you control have double strike.
    Sliver creatures you control have first strike.   All Sliver creatures have haste.
    White creatures get +1/+1.                        Creatures your opponents control get -1/-0.
    Other Goblin creatures you control get +1/+1 and have haste.
    Nontoken creatures you control get +1/+1 and have vigilance.

    ~ gets +1/+2 as long as you control a Plains.     ~ has flying as long as you control another Wizard.
    ~ gets +2/+2 and has trample as long as it's enchanted.

``parse_line`` is the last template a permanent's line is tried against (the narrower anthem fields in
face_lines come first), and records ``(scope, words, power, toughness, keywords)`` in ``CardDef.team_statics``:
scope is "mine", "theirs" or "all"; words are the adjectives before "creatures" (Other, colors, card types,
attacking / blocking / tapped, token / nontoken, a creature type). The engine asks ``pt_bonus`` and ``keyword``.
Commander creatures never exist in these games, so a "Commander creatures" line matches nothing.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_STATES = {"attacking", "blocking", "tapped", "untapped", "token", "nontoken", "multicolored", "monocolored",
           "colorless", "legendary", "nonlegendary", "commander"}
_TYPES = {"artifact": "Artifact", "enchantment": "Enchantment", "land": "Land", "nonartifact": "-Artifact"}
_KW = (r"flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|"
       r"reach|shroud|defender|fear|intimidate|shadow|horsemanship|flanking|infect|wither|prowess|ward \{\d+\}")
_LINE = re.compile(
    rf"(All |Other )?((?:[\w-]+ )*?)[Cc]reatures( you control| your opponents control)?"
    rf"(?: get ([+-]\d+)/([+-]\d+))?(?:(?:,? and)? (?:have|gain) ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*))?\.")


_SELF = re.compile(rf"~ (?:gets ([+-]\d+)/([+-]\d+)(?: and has ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*))?|"
                   rf"has ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*)) as long as (.+)\.")
_NOUNS = {"permanent", "creature", "artifact", "enchantment", "land", "planeswalker"}


def parse_line(line: str, st) -> bool:
    if not ({"Instant", "Sorcery"} & set(st.types)) and line:
        line = line.replace("−", "-")
        entry = _parse(line)
        if entry is not None:
            st.extra["team_statics"] = st.extra.get("team_statics", ()) + (entry,)
            return True
        desc = unblockable_by(line)
        if desc:
            st.extra["unblockable_by"] = st.extra.get("unblockable_by", ()) + (desc,)
            return True
        m = _SELF.fullmatch(line)
        cond = _condition(m[5]) if m else None
        if cond:
            kws = m[3] or m[4]
            if m[1]:
                st.extra["pt_if"] = st.extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
            for k in (re.split(r", and |, | and ", kws) if kws else ()):
                st.extra["cond_keywords"] = st.extra.get("cond_keywords", ()) + ((k.strip(), cond),)
            return True
    return False


def _condition(text: str):
    """The condition name for "as long as <text>", or None. Board conditions read ``desc_matches``."""
    m = re.fullmatch(r"you control (another |an? |(?:two|three|four) or more )(.+?)", text)
    if m and _desc_ok(m[2]):
        n = {"two": 2, "three": 3, "four": 4}.get(m[1].split()[0], 1)
        return f"ctl:{'other' if m[1] == 'another ' else ''}|{n}|{m[2]}"
    m = re.fullmatch(r"an opponent controls (?:an? )?(.+?)", text)
    if m and _desc_ok(m[1]):
        return f"oppctl:{m[1]}"
    simple = {"it's enchanted": "enchanted", "it's equipped": "equipped", "it's untapped": "untapped",
              "it's tapped": "tapped", "it has a +1/+1 counter on it": "p1", "you have no cards in hand": "hand<=0"}
    if text in simple:
        return simple[text]
    m = re.fullmatch(r"you have (\w+) or more cards in hand", text)
    if m and m[1] in ("two", "three", "four", "five", "seven"):
        return f"hand>={ {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'seven': 7}[m[1]] }"
    m = re.fullmatch(r"you have (\d+) or (?:less|fewer) life", text)
    if m:
        return f"life<={m[1]}"
    m = re.fullmatch(r"you have at least (\d+) life more than your starting life total", text)
    if m:
        return f"life>={20 + int(m[1])}"
    return None


_WITH = re.compile(rf"(.+?) with ({_KW}|power (\d+) or (less|greater))")


def _parts(desc: str):
    """("black or green creatures") -> ["black creatures", "green creatures"]: alternatives share the last noun."""
    parts = desc.split(" or ")
    noun = parts[-1].split()[-1]
    return [p if _words(p) is not None and len(p.split()) > 1 or p == parts[-1] or re.fullmatch(r"[A-Z]\w+", p)
            else f"{p} {noun}" for p in parts]


def _desc_ok(desc: str) -> bool:
    m = _WITH.fullmatch(desc)
    return all(_words(part) is not None for part in _parts(m[1] if m else desc))


def _words(part: str):
    words = [w for w in part.replace("-", " ").split() if w not in ("a", "an")]
    if not words:
        return None
    for w in words[:-1]:
        if not (w in _COLORS or w in ("untapped", "tapped", "nonland", "noncreature", "legendary", "basic",
                                       "nontoken", "token", "artifact", "enchantment", "creature", "snow")):
            return None
    last = words[-1]
    if not (last.rstrip("s") in _NOUNS or re.fullmatch(r"[A-Z][a-z]+", last)):
        return None
    return words


def desc_matches(perm, desc: str) -> bool:
    """Whether perm is "a(n) <desc>": "white creature", "untapped Island", "Plains or Forest", "artifact",
    "creatures with flying", "creatures with power 2 or less"."""
    m = _WITH.fullmatch(desc)
    if m:
        if m[3]:
            if (perm.power > int(m[3])) if m[4] == "less" else (perm.power < int(m[3])):
                return False
        elif not perm.has(m[2]):
            return False
        desc = m[1]
    return any(_part_matches(perm, _words(part)) for part in _parts(desc))


def unblockable_by(line: str):
    """The description in "~ can't be blocked by <desc>." (Walls, white creatures, creatures with flying), or None."""
    m = re.fullmatch(r"~ can't be blocked by (.+?)\.", line)
    return m[1] if m and _desc_ok(m[1]) else None


def _part_matches(perm, words) -> bool:
    card = perm.card
    noun = words[-1]
    n = noun.rstrip("s")
    if n in _NOUNS:
        if n == "creature" and not perm.is_creature or n not in ("permanent", "creature") and n.capitalize() not in card.types:
            return False
    elif noun not in card.subtypes and n not in card.subtypes:
        return False
    for w in words[:-1]:
        if w in _COLORS and _COLORS[w] not in card.colors or w == "untapped" and perm.tapped or \
                w == "tapped" and not perm.tapped or w == "nonland" and card.is_land or \
                w == "noncreature" and perm.is_creature or w == "legendary" and not card.legendary or \
                w == "basic" and not card.basic or w == "token" and not card.is_token or \
                w == "nontoken" and card.is_token or w == "snow" and "Snow" not in card.types or \
                w in ("artifact", "enchantment", "creature") and w.capitalize() not in card.types:
            return False
    return True


def condition(perm, cond: str):
    """Evaluate a condition from ``_condition`` for perm, or None if cond isn't one of ours."""
    p = perm.controller
    if cond.startswith("ctl:"):
        other, n, desc = cond[4:].split("|", 2)
        return sum(1 for x in p.battlefield if not (other and x is perm) and desc_matches(x, desc)) >= int(n)
    if cond.startswith("oppctl:"):
        foe = p.foe
        return foe is not None and any(desc_matches(x, cond[7:]) for x in foe.battlefield)
    if cond == "enchanted":
        return bool(perm.auras)
    if cond == "equipped":
        return bool(perm.equipment)
    if cond in ("untapped", "tapped"):
        return perm.tapped == (cond == "tapped")
    if cond == "p1":
        return perm.p1 > 0
    if cond.startswith("hand"):
        return len(p.hand) >= int(cond[6:]) if ">=" in cond else len(p.hand) <= int(cond[6:])
    if cond.startswith("life"):
        return p.life >= int(cond[6:]) if ">=" in cond else p.life <= int(cond[6:])
    return None


def _parse(line: str):
    m = _LINE.fullmatch(line)
    if not m or not (m[4] or m[6]):
        return None
    words = tuple(w for w in m[2].split())
    for w in words:
        if not (w.lower() in _COLORS or w.lower() in _STATES or w.lower() in _TYPES or re.fullmatch(r"[A-Z][\w-]+", w)):
            return None
    scope = {" you control": "mine", " your opponents control": "theirs"}.get(m[3] or "", "all")
    if m[1] == "Other ":
        words = ("Other",) + words
    kws = frozenset(k.strip() for k in re.split(r", and |, | and ", m[6])) if m[6] else frozenset()
    if any(k.startswith("ward") for k in kws):
        return None
    return scope, words, int(m[4] or 0), int(m[5] or 0), kws


def _matches(perm, source, scope: str, words) -> bool:
    if not perm.is_creature:
        return False
    mine = perm.controller is source.controller
    if scope == "mine" and not mine or scope == "theirs" and mine:
        return False
    card = perm.card
    for w in words:
        lw = w.lower()
        if w == "Other":
            if perm is source:
                return False
        elif lw in _COLORS:
            if _COLORS[lw] not in card.colors:
                return False
        elif lw in _TYPES:
            t = _TYPES[lw]
            if (t[1:] in card.types) if t.startswith("-") else (t not in card.types):
                return False
        elif lw in ("attacking", "blocking"):
            game = getattr(perm.controller, "_game", None)
            if game is None or not (perm in game.attackers if lw == "attacking"
                                    else any(perm in bl for bl in game.blocks.values())):
                return False
        elif lw in ("tapped", "untapped"):
            if perm.tapped != (lw == "tapped"):
                return False
        elif lw in ("token", "nontoken"):
            if card.is_token != (lw == "token"):
                return False
        elif lw == "multicolored":
            if len(card.colors) < 2:
                return False
        elif lw == "monocolored":
            if len(card.colors) != 1:
                return False
        elif lw == "colorless":
            if card.colors:
                return False
        elif lw in ("legendary", "nonlegendary"):
            if card.legendary != (lw == "legendary"):
                return False
        elif lw == "commander":
            return False
        elif w not in card.subtypes and not (w.endswith("s") and w[:-1] in card.subtypes):
            return False
    return True


def _sources(perm):
    for pl in (perm.controller, perm.controller.foe):
        for x in (pl.battlefield if pl is not None else ()):
            if x.card.team_statics:
                yield x


def pt_bonus(perm) -> tuple:
    bp = bt = 0
    for x in _sources(perm):
        for scope, words, p, t, _ in x.card.team_statics:
            if (p or t) and _matches(perm, x, scope, words):
                bp += p
                bt += t
    return bp, bt


def keyword(perm, kw: str) -> bool:
    return any(kw in kws and _matches(perm, x, scope, words)
               for x in _sources(perm) for scope, words, _, _, kws in x.card.team_statics)
