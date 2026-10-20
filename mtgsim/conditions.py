"""Reusable Oracle conditions, independent of the effect or trigger they guard.

Conditions use the existing string interface. Structured conditions have a ``cc:``
JSON payload; unknown wording returns an empty string and remains in coverage.
Turn observations are stamped with the game turn, so neither player carries an
opponent-turn event into the following turn.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

_N = r"(?:a|an|no|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|twenty|\d+)"
_TYPES = {"Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"}
_PERMANENT_TYPES = _TYPES - {"Instant", "Sorcery", "Kindred"}


def _n(word):
    from .cards import _num
    return 0 if word.lower() == "no" else _num(word)


def code(op, *args):
    return "cc:" + json.dumps((op,) + args, separators=(",", ":"))


@lru_cache(maxsize=4096)
def _decode(value):
    return json.loads(value[3:])


def negate(cond):
    return code("not", cond)


def both(a, b):
    return code("all", a, b) if a and b else a or b


def _desc(text):
    """Accept only descriptions our shared permanent matcher understands."""
    words = []
    for word in text.split():
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif word.endswith("s") and not word.endswith("ss") and word != "Plains":
            word = word[:-1]
        if word.lower() in {"permanent", "token", "nontoken", "legendary", "nonlegendary", "nonland", "noncreature",
                            "nonartifact", "attacking", "tapped", "untapped", "outlaw"} | {t.lower() for t in _TYPES}:
            words.append(word.lower())
        elif re.fullmatch(r"[A-Z][a-zA-Z-]+", word):
            words.append(word)
        else:
            return ""
    return " ".join(words)


@lru_cache(maxsize=4096)
def parse(phrase):
    """Recognize an entire condition. Never discard an unrecognized qualifier."""
    phrase = phrase.strip()
    low = phrase.lower()
    simple = {
        "you attacked this turn": "attacked_turn", "a creature died this turn": "creature_died",
        "a creature died under an opponent's control this turn": "opp_creature_died",
        "an opponent controls more lands than you": "opp_more_lands",
        "you sacrificed a permanent this turn": "sacrificed_turn",
        "you gained life this turn": "gained_life", "you gained and lost life this turn": "gained_and_lost",
        "you gained or lost life this turn": code("life_changed"),
        "an opponent lost life this turn": "opp_lost_life", "you descended this turn": "descended",
        "you cast it": "cast", "the gift was promised": "gifted", "the gift wasn't promised": "!gifted",
        "it's your turn": code("your_turn"), "it is your turn": code("your_turn"),
        "it's not your turn": negate(code("your_turn")),
        "a permanent left the battlefield under your control this turn": code("left"),
        "a nonland permanent left the battlefield this turn": code("event", "nonland_left", "any", 1),
        "a spell was warped this turn": code("event", "warped", "any", 1),
        "you haven't cast a spell from your hand this turn": negate(code("event", "cast_hand", "mine", 1)),
        "~ is attacking": code("attacking"), "it's attacking": code("attacking"),
    }
    if low in simple:
        return simple[low]
    m = re.fullmatch(r"(?:~|it|this spell|the spell) was (bargained|kicked)", low)
    if m:
        return m[1] if m[1] == "bargained" else code("kicked")
    m = re.fullmatch(r"(?:~|it) was cast from (a graveyard|anywhere other than your hand)", low)
    if m:
        return code("cast_zone", "graveyard" if m[1] == "a graveyard" else "not_hand")
    m = re.fullmatch(r"\{([WUBRG])\}\{\1\} was spent to cast it", phrase)
    if m:
        return "spent:" + m[1]
    m = re.fullmatch(r"you(?:'ve| have)? gained (" + _N + r") or more life this turn", low)
    if m:
        return "gained_life>=" + str(_n(m[1]))
    m = re.fullmatch(r"you control a creature with power (\d+) or greater", low)
    if m:
        return "power_ge:" + m[1]
    m = re.fullmatch(r"you control (another|an?|" + _N + r")( or more| or fewer)? (.+)", phrase, re.I)
    if m:
        desc = _desc(m[3])
        if desc:
            return code("control", desc, 1 if m[1].lower() == "another" else _n(m[1]),
                        "le" if (m[2] or "").lower() == " or fewer" else "ge", m[1].lower() == "another")
    m = re.fullmatch(r"there are (" + _N + r")( or more| or fewer)? (card types among cards|permanent types among cards|"
                     r"(?:(?:[\w-]+ )*)cards) in your graveyard", phrase, re.I)
    if m:
        what = m[3]
        if "types among" in what.lower():
            return code("grave_types", _n(m[1]), "le" if (m[2] or "").lower() == " or fewer" else "ge",
                        what.lower().startswith("permanent"))
        desc = what[:-5].strip()
        desc = _desc(desc) if desc else ""
        if desc or what.lower() == "cards":
            return code("zone_count", "graveyard", desc, _n(m[1]),
                        "le" if (m[2] or "").lower() == " or fewer" else "ge")
    m = re.fullmatch(r"you have (" + _N + r")( or more| or fewer)? cards in (?:your )?(hand|graveyard|library)", low)
    if m:
        return code("zone_count", m[3], "", _n(m[1]), "ge" if m[2] == " or more" else "le" if m[2] == " or fewer" else "eq")
    m = re.fullmatch(r"(?:your life total is|you have) (" + _N + r")( or more| or less| or fewer)?(?: life)?", low)
    if m:
        return code("life", _n(m[1]), "ge" if m[2] == " or more" else "le" if m[2] else "eq")
    m = re.fullmatch(r"x is (\d+)( or more| or greater| or less| or fewer)?", low)
    if m:
        return code("x", int(m[1]), "ge" if m[2] in (" or more", " or greater") else "le" if m[2] else "eq")
    m = re.fullmatch(r"(?:it|~) has (" + _N + r") or more ([\w+/ -]+) counters on it", low)
    if m:
        return "counters:" + m[2] + ">=" + str(_n(m[1]))
    m = re.fullmatch(r"(" + _N + r")( or more)? (nonland permanents?|artifacts?|lands?) entered the battlefield under your control this turn", low)
    if m:
        return code("event", {"nonland": "nonland_entered", "artifact": "artifact_entered", "land": "land_entered"}[m[3].split()[0].rstrip("s")], "mine", _n(m[1]))
    # Conjunction/disjunction is accepted only if *every* component is known.
    for sep, op in ((" or ", "any"), (" and ", "all")):
        for match in re.finditer(sep, phrase):
            a, b = parse(phrase[:match.start()]), parse(phrase[match.end():])
            if a and b:
                return code(op, a, b)
    return ""


def leading(text):
    """Split a leading If clause, preserving unknown text for normal coverage."""
    m = re.fullmatch(r"(?:then )?if (.+?), (.+)", text, re.I | re.S)
    if m:
        cond = parse(m[1])
        if cond:
            return cond, m[2]
    return None


def observe(game, p, event, amount=1):
    if getattr(p, "_condition_turn", None) != game.turn:
        p._condition_turn, p._condition_events = game.turn, {}
    p._condition_events[event] = p._condition_events.get(event, 0) + amount


def events(game, p, event):
    return getattr(p, "_condition_events", {}).get(event, 0) if getattr(p, "_condition_turn", None) == game.turn else 0


def _compare(actual, n, cmp):
    return actual >= n if cmp == "ge" else actual <= n if cmp == "le" else actual == n


def bind_counts(game, player, effects, item):
    """Calculate a variable graveyard target limit at announcement and recheck it on resolution."""
    import dataclasses
    return [dataclasses.replace(e, data={**e.data, "bound_x": game.x_quantity(player, e.data["cmc_xq"], item, None)})
            if "cmc_xq" in e.data else e for e in effects]


def _fits(game, perm, desc):
    from .copies import fits
    words = desc.split()
    if "attacking" in words:
        words.remove("attacking")
        if perm not in game.attackers:
            return False
    for state in ("tapped", "untapped"):
        if state in words:
            words.remove(state)
            if perm.tapped != (state == "tapped"):
                return False
    if "outlaw" in words:
        words.remove("outlaw")
        if not (perm.card.changeling or set(perm.card.subtypes) & {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}):
            return False
    return not words or fits(perm.card, " ".join(words), perm)


def evaluate(game, p, cond, item=None, prev=None):
    """Evaluate a recognized condition; legacy string conditions use Game's checks."""
    from .cards import Effect
    if not cond.startswith("cc:"):
        return game.check_cond(p, Effect("condition", cond=cond), item, prev)
    op, *args = _decode(cond)
    src = getattr(item, "source", None)
    if op in ("all", "any"):
        values = (evaluate(game, p, c, item, prev) for c in args)
        return all(values) if op == "all" else any(values)
    if op == "not":
        return not evaluate(game, p, args[0], item, prev)
    if op == "your_turn":
        return game.active is p
    if op == "life_changed":
        return p.life_gained_turn > 0 or p.lost_life_turn
    if op == "left":
        return p.perm_left_turn
    if op == "event":
        event, scope, n = args
        return sum(events(game, who, event) for who in (game.players if scope == "any" else (p,))) >= n
    if op == "control":
        desc, n, cmp, other = args
        return _compare(sum(x is not src or not other for x in p.battlefield if _fits(game, x, desc)), n, cmp)
    if op == "grave_types":
        n, cmp, permanent = args
        types = set().union(*(c.types for c in p.graveyard)) if p.graveyard else set()
        return _compare(len(types & (_PERMANENT_TYPES if permanent else _TYPES)), n, cmp)
    if op == "zone_count":
        from .copies import fits
        zone, desc, n, cmp = args
        return _compare(sum(not desc or fits(c, desc) for c in getattr(p, zone)), n, cmp)
    if op == "life":
        return _compare(p.life, *args)
    if op == "x":
        return _compare(getattr(item, "x", getattr(src, "entered_x", 0)), *args)
    if op == "kicked":
        return bool(getattr(item, "kicked", False) or getattr(src, "kicked", False))
    if op == "cast_zone":
        zone = getattr(item, "cast_zone", getattr(src, "cast_zone", ""))
        return zone == "graveyard" if args[0] == "graveyard" else bool(zone and zone != "hand")
    if op == "attacking":
        return src is not None and src in game.attackers
    raise ValueError(f"Unknown condition operation {op!r}")
