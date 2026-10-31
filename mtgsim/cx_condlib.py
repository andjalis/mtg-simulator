"""Shared condition library: one grammar for the "<condition>" of "If <condition>, X", intervening-if
triggers ("When ~ enters, if it was kicked, ..."), and "as long as <condition>" statics.

``parse(phrase)`` turns a condition phrase into an engine condition code, or "" when it doesn't know it.
Codes are either an existing engine name (``perm_left``, ``gained_life``, ``evidence``, ...) or a ``lib:``
code holding a small JSON list, evaluated by ``check(game, p, code, item)``.

The grammar is compositional, not one regex per card:

* counts of what a player controls, with a permanent filter: "you control two or more Gates",
  "you control no untapped lands", "an opponent controls more creatures than you",
  "you control an artifact and an enchantment", "you control a Desert or there is a Desert card in
  your graveyard";
* graveyard counts with a card filter: "there are five or more instant and/or sorcery cards in your
  graveyard";
* life, hand and poison comparisons, the monarch, whose turn it is, the starting player;
* turn history: creatures died, spells cast, life gained, attacks, a permanent left the battlefield;
* facts about the source: kicked, cast from hand, mana or X spent, counters on it, attacking.
"""
from __future__ import annotations

import json
import re

from .cards.model import NUMBERS

_NUM = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twenty)"
_WORDS = dict(NUMBERS, twenty=20)
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TYPES = ("artifact", "creature", "enchantment", "land", "planeswalker", "battle", "instant", "sorcery",
          "permanent", "spell", "card", "token")
_BASICS = ("plains", "island", "swamp", "mountain", "forest", "wastes")
_PLURAL_SUB = {"elves": "Elf", "dwarves": "Dwarf", "wolves": "Wolf", "plains": "Plains", "faeries": "Faerie",
               "zombies": "Zombie", "allies": "Ally", "mercenaries": "Mercenary", "fungi": "Fungus",
               "deserts": "Desert", "gates": "Gate"}


def _n(word: str) -> int:
    word = word.lower()
    return int(word) if word.isdigit() else _WORDS[word]


def _code(*parts) -> str:
    return "lib:" + json.dumps(list(parts), separators=(",", ":"))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_QUANT = (rf"(?P<q>another|no|exactly {_NUM}|at least {_NUM}|fewer than {_NUM}|more than {_NUM}|{_NUM} or more|"
          rf"{_NUM} or fewer|{_NUM} or less|{_NUM})")


def _quant(q: str):
    """(operator, number) for a quantity phrase."""
    q = q.lower()
    if q == "no":
        return "==", 0
    if q == "another":
        return ">=", 1
    m = re.fullmatch(rf"(exactly|at least|fewer than|more than) ({_NUM})", q)
    if m:
        return {"exactly": "==", "at least": ">=", "fewer than": "<", "more than": ">"}[m[1]], _n(m[2])
    m = re.fullmatch(rf"({_NUM}) or (more|fewer|less)", q)
    if m:
        return (">=" if m[2] == "more" else "<="), _n(m[1])
    return ">=", _n(q)


def _cmp(value: int, op: str, n: int) -> bool:
    return {">=": value >= n, "<=": value <= n, "==": value == n, "<": value < n, ">": value > n}[op]


def _word_spec(word: str, spec: dict, plural: bool = True) -> bool:
    """Add one filter word to spec; False when the word isn't a filter word."""
    low = word.lower()
    if low in ("other", "another"):
        spec["other"] = True
    elif low in ("tapped", "untapped"):
        spec["tapped"] = low == "tapped"
    elif low in ("legendary", "nonlegendary"):
        spec["legendary"] = low == "legendary"
    elif low in ("basic", "nonbasic"):
        spec["basic"] = low == "basic"
    elif low in ("nontoken",):
        spec["token"] = False
    elif low == "modified":
        spec["modified"] = True
    elif low in ("multicolored", "colorless", "monocolored"):
        spec["colorcount"] = low
    elif low in _COLORS:
        spec.setdefault("colors", []).append(_COLORS[low])
    elif low.startswith("non") and low[3:].rstrip("s") in _TYPES:
        spec.setdefault("not", []).append(low[3:].rstrip("s"))
    elif low.rstrip("s") in _TYPES or low in ("sorceries",):
        t = "sorcery" if low.startswith("sorcer") else low.rstrip("s")
        spec.setdefault("types", []).append(t)
    elif low in _PLURAL_SUB:
        spec.setdefault("sub", []).append(_PLURAL_SUB[low])
    elif low.rstrip("s") in _BASICS or low in _BASICS:
        spec.setdefault("sub", []).append(low.rstrip("s").capitalize() if low != "plains" else "Plains")
    elif word[:1].isupper() and word.isalpha():
        sub = word if not plural or not word.endswith("s") or word.endswith("ss") else word[:-1]
        spec.setdefault("sub", []).append(sub)
    else:
        return False
    return True


def _filter(text: str, plural: bool = True):
    """A permanent/card filter from "other untapped legendary creatures with flying", or None."""
    text = text.strip()
    spec: dict = {}
    m = re.fullmatch(r"(.+?) with (?:power|mana value) (\d+) or (greater|more|less)", text)
    if m:
        key = "power" if "power" in text.split(" with ")[1] else "mv"
        spec[key] = [">=" if m[3] != "less" else "<=", int(m[2])]
        text = m[1]
    m = re.fullmatch(r"(.+?) with (flying|deathtouch|lifelink|trample|haste|vigilance|reach|menace|defender|"
                     r"first strike|double strike|hexproof|indestructible)", text)
    if m:
        spec["kw"] = m[2]
        text = m[1]
    m = re.fullmatch(r"(.+?) (?:with|that have) (?:a|one or more) (\+1/\+1|-1/-1|\w+) counters? on (?:it|them)", text)
    if m:
        spec["counter"] = m[2]
        text = m[1]
    any_of = re.fullmatch(r"(\w+) (?:and/or|or) (\w+)( .+)?", text)
    if any_of and any_of[1].lower().rstrip("s") in _TYPES + ("sorcerie",) and \
            any_of[2].lower().rstrip("s") in _TYPES + ("sorcerie",):
        a, b = (("sorcery" if w.lower().startswith("sorcer") else w.lower().rstrip("s")) for w in any_of.group(1, 2))
        spec["any"] = [a, b]
        text = (any_of[3] or "").strip()
        if not text:
            return spec
    words = text.split()
    if not words:
        return None
    for word in words:
        # Two-word subtypes are rare; planeswalker types: "a Vraska planeswalker".
        if not _word_spec(word, spec, plural):
            return None
    return spec


def _is_basic(card) -> bool:
    return "Basic" in getattr(card, "supertypes", ()) or card.name in ("Plains", "Island", "Swamp", "Mountain",
                                                                         "Forest", "Wastes")


def _card_ok(card, spec: dict, perm=None) -> bool:
    types = set(t.lower() for t in card.types)
    subs = set(card.subtypes)

    def has_type(t):
        if t in ("card", "spell"):
            return True
        if t == "permanent":
            return card.is_permanent if perm is None else True
        if t == "token":
            return bool(card.is_token)
        return t in types

    if any(not has_type(t) for t in spec.get("types", ())):
        return False
    if any(has_type(t) for t in spec.get("not", ())):
        return False
    if "any" in spec and not any(has_type(t) for t in spec["any"]):
        return False
    if any(s not in subs for s in spec.get("sub", ())):
        return False
    if spec.get("colors") and not all(c in card.colors for c in spec["colors"]):
        return False
    cc = spec.get("colorcount")
    if cc == "multicolored" and len(card.colors) < 2 or cc == "colorless" and card.colors or \
            cc == "monocolored" and len(card.colors) != 1:
        return False
    if "legendary" in spec and bool(card.legendary) != spec["legendary"]:
        return False
    if "basic" in spec and _is_basic(card) != spec["basic"]:
        return False
    if spec.get("token") is False and card.is_token:
        return False
    if "mv" in spec and not _cmp(card.cmc, *spec["mv"]):
        return False
    if perm is not None:
        if "tapped" in spec and bool(perm.tapped) != spec["tapped"]:
            return False
        if "creature" in spec.get("types", ()) and not perm.is_creature:
            return False
        if "power" in spec and not _cmp(perm.power, *spec["power"]):
            return False
        if "kw" in spec and not perm.has(spec["kw"]):
            return False
        if "counter" in spec and not perm.counters.get(spec["counter"], 0):
            return False
        if "toughness" in spec and not _cmp(perm.toughness, *spec["toughness"]):
            return False
        if spec.get("modified") and not (any(v > 0 for v in perm.counters.values()) or perm.auras or
                                         any(x.attached_to is perm for x in perm.controller.battlefield)):
            return False
    elif "power" in spec and not _cmp(int(card.power or 0), *spec["power"]):
        return False
    return True


def _count_perms(player, spec, source=None) -> int:
    return sum(1 for x in player.battlefield
               if not (spec.get("other") and x is source) and _card_ok(x.card, spec, x))


# ---------------------------------------------------------------------------
# Phrase grammar
# ---------------------------------------------------------------------------

# Existing engine condition names for phrases other modules already evaluate.
_ALIASES = {
    "a permanent you controlled left the battlefield this turn": "perm_left",
    "you gained life this turn": "gained_life",
    "you've gained life this turn": "gained_life",
    "an opponent lost life this turn": "opp_lost_life",
    "evidence was collected": "evidence",
    "~ was bargained": "bargained",
    "it was bargained": "bargained",
    "the gift was promised": "gifted",
    "~ was cast": "cast",
    "you cast it": "cast",
    "you cast ~": "cast",
    "a creature died under your control this turn": "lib:[\"died_mine\"]",
    "you're the monarch": "lib:[\"monarch\"]",
    "you are the monarch": "lib:[\"monarch\"]",
    "there is no monarch": "lib:[\"no_monarch\"]",
    "it's your turn": "your_turn",
    "it's not your turn": "!your_turn",
    "it isn't your turn": "!your_turn",
    "you weren't the starting player": "lib:[\"not_starting\"]",
    "you were the starting player": "lib:[\"starting\"]",
    "it was kicked": "lib:[\"kicked\"]",
    "~ was kicked": "lib:[\"kicked\"]",
    "that spell was kicked": "lib:[\"ctx_kicked\"]",
    "you cast it from your hand": "lib:[\"from_hand\"]",
    "you cast ~ from your hand": "lib:[\"from_hand\"]",
    "~ was cast from your hand": "lib:[\"from_hand\"]",
    "~ is attacking": "lib:[\"src_attacking\"]",
    "it's attacking": "lib:[\"src_attacking\",\"it\"]",
    "~ is tapped": "source_tapped",
    "~ is untapped": "source_untapped",
    "it's untapped": "lib:[\"src_tapped\",false,\"it\"]",
    "it's tapped": "lib:[\"src_tapped\",true,\"it\"]",
    "~ is a creature": "lib:[\"src_creature\"]",
    "it's a creature": "lib:[\"src_creature\",\"it\"]",
    "~ is enchanted": "lib:[\"src_enchanted\"]",
    "~ is equipped": "lib:[\"src_equipped\"]",
    "you have the initiative": "initiative",
    "you have more life than an opponent": "lib:[\"life_vs_opp\",\">\"]",
    "an opponent has more life than you": "lib:[\"life_vs_opp\",\"<\"]",
    "you have less life than an opponent": "lib:[\"life_vs_opp\",\"<\"]",
    "you have more cards in hand than an opponent": "lib:[\"hand_vs_opp\",\">\"]",
    "you have more cards in hand than each opponent": "lib:[\"hand_vs_opp\",\">\"]",
    "you have more life than each opponent": "lib:[\"life_vs_opp\",\">\"]",
    "you have less life than each opponent": "lib:[\"life_vs_opp\",\"<\"]",
    "you have fewer cards in hand than each opponent": "lib:[\"hand_vs_opp\",\"<\"]",
    "an opponent has more cards in hand than you": "lib:[\"hand_vs_opp\",\"<\"]",
}

_RULES: list = []


def rule(pattern: str):
    def deco(fn):
        _RULES.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


@rule(rf"you control {_QUANT} (?P<f>.+?)")
def _you_control(m):
    op, n = _quant(m["q"])
    f = _filter(m["f"], _plural(m["q"]))
    if f is None:
        return ""
    if m["q"].lower() == "another":
        f = dict(f, other=True)
    return _code("ctl", "you", f, op, n)


@rule(rf"(?:an opponent|defending player|that player|target opponent) controls {_QUANT} (?P<f>.+?)")
def _opp_control(m):
    op, n = _quant(m["q"])
    f = _filter(m["f"], _plural(m["q"]))
    if f is None:
        return ""
    return _code("ctl", "opp", f, op, n)


@rule(r"(?:an opponent|defending player|that player) controls more (?P<f>.+?) than you")
def _opp_more(m):
    f = _filter(m["f"])
    return _code("ctl_vs", f, "<") if f is not None else ""


@rule(r"you control more (?P<f>.+?) than (?:an opponent|defending player|that player|each opponent)")
def _you_more(m):
    f = _filter(m["f"])
    return _code("ctl_vs", f, ">") if f is not None else ""


@rule(r"you control (?:fewer|less) (?P<f>.+?) than (?:an opponent|defending player|that player)")
def _you_fewer(m):
    f = _filter(m["f"])
    return _code("ctl_vs", f, "<") if f is not None else ""


@rule(rf"(?:there (?:are|is)|you have) {_QUANT} (?P<f>.+?) in your graveyard")
def _graveyard(m):
    op, n = _quant(m["q"])
    f = _filter(m["f"], _plural(m["q"]))
    if f is None:
        return ""
    return _code("gy", "you", f, op, n)


@rule(rf"{_QUANT} (?P<f>.+?) (?:are|is) in your graveyard")
def _graveyard2(m):
    return _graveyard(m)


@rule(rf"(?:an opponent|that player) has {_QUANT} (?P<f>.+?) in (?:their|his or her) graveyard")
def _opp_graveyard(m):
    f = _filter(m["f"])
    if f is None:
        return ""
    op, n = _quant(m["q"])
    return _code("gy", "opp", f, op, n)


@rule(rf"(?P<who>you|an opponent|that player|target player|defending player) (?:has|have) {_QUANT} "
      r"(?P<what>life|cards? in (?:hand|your hand|their hand)|poison counters?)")
def _resource(m):
    op, n = _quant(m["q"])
    what = "life" if m["what"] == "life" else "poison" if "poison" in m["what"] else "hand"
    return _code("res", _who(m["who"]), what, op, n)


@rule(rf"(?P<who>you|an opponent|that player|target player|defending player) (?:has|have) (?P<n>{_NUM}) or "
      r"(?P<dir>less|fewer|more|greater) life")
def _life_alt(m):
    return _code("res", _who(m["who"]), "life", ">=" if m["dir"] in ("more", "greater") else "<=", _n(m["n"]))


@rule(rf"you have at least (?P<n>{_NUM}) life more than your starting life total")
def _life_start(m):
    return _code("res", "you", "life", ">=", 20 + _n(m["n"]))


@rule(r"(?P<who>you have|an opponent has|that player has) no cards in (?:hand|their hand|your hand)")
def _empty_hand(m):
    return _code("res", _who(m["who"].split()[0] if not m["who"].startswith("an") else "an opponent"), "hand", "==", 0)


@rule(r"(?:a|another) creature died this turn")
def _died_any(m):
    return "creature_died"


@rule(r"(?:a|another) (?P<f>creature|nontoken creature) died under your control this turn")
def _died_mine(m):
    return _code("died_mine")


@rule(rf"you(?:'ve| have)? cast (?P<q>(?:{_NUM}|another)(?: or more)?) spells? this turn")
def _spells_turn(m):
    q = m["q"].replace("another", "two")
    op, n = _quant(q)
    return _code("spells", op, n)


@rule(rf"you(?:'ve| have)? gained (?P<n>{_NUM}) or more life this turn")
def _gained(m):
    return f"gained_life>={_n(m['n'])}"


@rule(rf"you attacked with (?P<n>{_NUM}) or more creatures this turn")
def _attacked(m):
    return _code("attacked", _n(m["n"]))


@rule(rf"creatures you control have total power (?P<n>{_NUM}) or (?:greater|more)")
def _total_power(m):
    return _code("total_power", _n(m["n"]))


@rule(rf"you control (?P<n>{_NUM}) or more creatures with different powers")
def _diff_powers(m):
    return _code("diff_powers", _n(m["n"]))


@rule(rf"at least (?P<n>{_NUM}) mana was spent to cast (?:it|~|that spell)")
def _mana_spent(m):
    return _code("mana", _n(m["n"]))


@rule(rf"x is (?P<n>{_NUM}) or (?:more|greater)")
def _x_more(m):
    return _code("x", _n(m["n"]))


@rule(rf"(?:~|it) has (?P<q>{_NUM}|{_NUM} or more|no) (?P<c>\+1/\+1|-1/-1|[a-z]+) counters? on it")
def _src_counters(m):
    op, n = _quant(m["q"])
    return _code("counters", m["c"], op, n, *_ref(m))


@rule(rf"there are (?P<q>{_NUM} or more|no) (?P<c>\+1/\+1|-1/-1|[a-z]+) counters on ~")
def _src_counters2(m):
    return _src_counters(m)


@rule(rf"(?:~|it)(?:'s| is| has)? (?:power|toughness) (?:is )?(?P<n>{_NUM}) or (?P<d>greater|more|less)")
def _src_power(m):
    return _code("src_power", ">=" if m["d"] != "less" else "<=", _n(m["n"]), *_ref(m))


@rule(r"(?:it's|it is|that creature is|that permanent is) (?P<q>a|an) (?P<f>[\w ,/-]+?)")
def _prev_is(m):
    """"Target creature gets +2/+2. If it's a Vampire, ...": the object the previous effect targeted."""
    if m["f"].lower().endswith(("card", "spell", "token")) or re.search(r"\b(?:turn|phase|step|time)\b", m["f"]):
        return ""
    f = _filter(m["f"].replace(",", ""), plural=False)
    return _code("prev_is", f) if f is not None else ""


@rule(r"(?:it's|it is|that creature is) (?P<w>legendary|tapped|untapped|attacking|blocking|equipped|enchanted)")
def _prev_state(m):
    w = m["w"].lower()
    spec = {"legendary": True} if w == "legendary" else {"tapped": w == "tapped"} if w in ("tapped", "untapped") else \
        {"state": w}
    return _code("prev_is", spec)


@rule(r"(?:it|that creature|that card|that permanent) was (?P<q>a|an) (?P<f>[\w ,/-]+?)")
def _prev_was(m):
    """Last-known information of the referent: "if it was a creature card", "if that creature was a Human"."""
    f = _filter(m["f"].replace(",", ""), plural=False)
    return _code("prev_is", f) if f is not None else ""


@rule(rf"(?:its|that card's|that creature's|that spell's|that permanent's) mana value (?:was|is) (?P<n>{_NUM}) or "
      r"(?P<d>less|fewer|greater|more)|(?:it|that card) had mana value (?P<n2>\d+) or (?P<d2>less|greater)")
def _prev_mv(m):
    n, d = (m["n"], m["d"]) if m["n"] else (m["n2"], m["d2"])
    return _code("prev_is", {"mv": [">=" if d in ("greater", "more") else "<=", _n(n)]})


@rule(rf"(?:it|that creature) had (?P<q>{_NUM}|{_NUM} or more|no) (?P<c>\+1/\+1|-1/-1|[a-z]+) counters? on it")
def _had_counters(m):
    op, n = _quant(m["q"])
    return _code("counters", m["c"], op, n, "it")


@rule(r"(?:it|that creature) had counters on it")
def _had_any_counters(m):
    return _code("any_counters", "it")


@rule(rf"(?:its|that creature's) (?P<w>power|toughness) (?:is|was) (?P<n>{_NUM}) or (?P<d>greater|more|less)")
def _prev_power(m):
    return _code("prev_is", {m["w"].lower(): [">=" if m["d"] != "less" else "<=", _n(m["n"])]})


@rule(r"this is the (?P<n>second|third|fourth|fifth) time this ability has resolved this turn")
def _nth_resolution(m):
    return _code("nth_resolve", {"second": 2, "third": 3, "fourth": 4, "fifth": 5}[m["n"].lower()])


def _ref(m) -> tuple:
    """("it",) when the phrase says "it": the trigger's referent (the creature it triggered on) before the source."""
    return ("it",) if m[0].lower().startswith("it") or " on it" in m[0].lower() and "~" not in m[0] else ()


def _plural(q: str) -> bool:
    return q.lower() not in ("a", "an", "one", "another", "exactly one")


# ---------------------------------------------------------------------------
# Turn history: "if <event> this turn", reusing the trigger-event grammar (cx_events)
# ---------------------------------------------------------------------------

_HIST_HEADS: dict = {}       # present-tense trigger head -> (raw events, matcher spec)
_SUBJ_Q = rf"(?P<q>a|an|{_NUM} or more|one or more)"     # "another" would count the source itself
_PAST = [
    (rf"{_SUBJ_Q} (?P<s>.+?) entered(?: the battlefield)? under your control", "{q} {s} you control enters"),
    (rf"{_SUBJ_Q} (?P<s>.+?) entered(?: the battlefield)?", "{q} {s} enters"),
    (rf"{_SUBJ_Q} (?P<s>.+?) died under your control", "{q} {s} you control dies"),
    (rf"{_SUBJ_Q} (?P<s>.+?) died", "{q} {s} dies"),
    (rf"{_SUBJ_Q} (?P<s>.+?) left the battlefield under your control", "{q} {s} you control leaves the battlefield"),
    (rf"{_SUBJ_Q} (?P<s>.+?) left the battlefield", "{q} {s} leaves the battlefield"),
    (rf"you(?:'ve| have)? cast {_SUBJ_Q} (?P<s>.+?)", "you cast {q} {s}"),
    (rf"you(?:'ve| have)? sacrificed {_SUBJ_Q} (?P<s>.+?)", "you sacrifice {q} {s}"),
    (r"you(?:'ve| have)? discarded (?P<q>a|one or more) (?P<s>cards?)", "you discard a card"),
    (r"you(?:'ve| have)? cycled (?P<q>a|one or more) (?P<s>cards?)", "you cycle a card"),
]


def _history(phrase: str) -> str:
    """A code for "<something happened> this turn", or ""."""
    m = re.fullmatch(r"(.+?) this turn", phrase.strip(), re.I)
    if not m:
        return ""
    body, negate = m[1], False
    neg = re.fullmatch(r"you haven't (cast|sacrificed|discarded|cycled) (.+)", body, re.I)
    if neg:
        body, negate = f"you {neg[1]} {neg[2]}", True
    for pat, template in _PAST:
        pm = re.fullmatch(pat, body, re.I)
        if not pm:
            continue
        q = pm["q"].lower()
        count = 1
        qm = re.fullmatch(rf"({_NUM}) or more", q)
        if qm:
            count = _n(qm[1])
        sub = pm["s"]
        if count > 1 or q == "one or more":
            # singular subject for the head: "two or more creatures" -> "a creature"
            sub = re.sub(r"(\w+?)(?:ies)$", r"\1y", sub) if sub.endswith("ies") else re.sub(r"s\b", "", sub, count=1)
            q = "a" if not re.match(r"[aeiou]", sub, re.I) else "an"
        head = template.format(q=q, s=sub)
        from .cx_events import compile_head
        got = compile_head("Whenever " + head)
        if got is None:
            continue
        _HIST_HEADS[head] = got
        code = _code("hist", head, count)
        return "!" + code if negate else code
    return ""


def record(game, p, event, source=None, context=None, subject=None):
    """Engine hook (Game.fire): count every registered turn-history head this event matches, per player."""
    if not _HIST_HEADS:
        return
    if event == "perm_to_gy" and source is not None or event == "any_cast" and context is not p:
        return
    hist = getattr(game, "_condlib_hist", None)
    if hist is None or hist[0] != game.turn:
        hist = game._condlib_hist = (game.turn, {})
    from .cx_events import _match
    for head, (raws, spec) in _HIST_HEADS.items():
        if event not in raws:
            continue
        for pl in game.players:
            try:
                ok = _match(game, spec, event, _Watcher(pl), p, source, context, subject)
            except Exception:       # a matcher that needs a real permanent: this head can't count the event
                ok = False
            if ok is not False:
                key = (head, pl.name)
                hist[1][key] = hist[1].get(key, 0) + 1


class _Watcher:
    """Stands in for the permanent that would own the trigger: only its controller matters here."""
    def __init__(self, controller):
        self.controller = controller
        self.card = None


def _who(word: str) -> str:
    word = word.lower()
    if word == "you":
        return "you"
    if word in ("that player", "target player"):
        return "ctx"
    return "opp"


def _plain(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", phrase.strip().rstrip(",.")).replace("’", "'")
    low = phrase.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    for rx, build in _RULES:
        m = rx.fullmatch(phrase)
        if m:
            code = build(m)
            if code:
                return code
    return ""


def parse(phrase: str) -> str:
    """The condition code for a phrase, or ""; tries "A or B" and "A and B" when the whole doesn't parse."""
    code = _plain(phrase) or _history(phrase)
    if code:
        return code
    for joiner, kind in ((" or ", "or"), (" and ", "and")):
        pieces = phrase.split(joiner)
        for i in range(1, len(pieces)):
            left, right = joiner.join(pieces[:i]), joiner.join(pieces[i:])
            # "you control an artifact and an enchantment": the subject carries over.
            if re.match(r"(?:a|an|another|\d|one|two|three)\b", right.strip(), re.I):
                subject = re.match(r"(you control|an opponent controls) ", left, re.I)
                if subject:
                    right = subject[0] + right
            a, b = _plain(left), _plain(right)
            if a and b:
                return _code(kind, a, b)
    return ""


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _game_of(p):
    return getattr(p, "_game", None)


def _source(item):
    return getattr(item, "source", None) if item is not None else None


def _player_for(game, p, who, item):
    if who == "you":
        return p
    if who == "ctx":
        ctx = getattr(item, "context", None)
        from .engine.state import Player
        if isinstance(ctx, Player):
            return ctx
    return game.opponent(p) if game is not None else None


def _kicked(game, item, source) -> bool:
    if source is not None and getattr(source, "kicked", False):
        return True
    card = getattr(item, "card", None)
    origin = getattr(card, "origin", None) if card is not None else None
    return bool(origin and origin[1] == "kicker") or bool(getattr(item, "kicks", 0))


def check(game, p, code: str, item=None, source=None, prev=None):
    """True/False for a condition this library owns, None otherwise."""
    if not code.startswith("lib:"):
        return None
    if game is None:
        game = _game_of(p)
    data = json.loads(code[4:])
    kind, args = data[0], data[1:]
    if source is None:
        source = _source(item)
    if kind in ("or", "and"):
        results = [_eval_any(game, p, sub, item, source, prev) for sub in args]
        return any(results) if kind == "or" else all(results)
    if kind == "ctl":
        who, spec, op, n = args
        pl = _player_for(game, p, who, item)
        return pl is not None and _cmp(_count_perms(pl, spec, source), op, n)
    if kind == "ctl_vs":
        spec, op = args
        opp = game.opponent(p)
        return _cmp(_count_perms(p, spec), op, _count_perms(opp, spec))
    if kind == "gy":
        who, spec, op, n = args
        pl = _player_for(game, p, who, item)
        return pl is not None and _cmp(sum(_card_ok(c, spec) for c in pl.graveyard), op, n)
    if kind == "res":
        who, what, op, n = args
        pl = _player_for(game, p, who, item)
        if pl is None:
            return False
        value = pl.life if what == "life" else len(pl.hand) if what == "hand" else pl.counters.get("poison", 0)
        return _cmp(value, op, n)
    if kind == "life_vs_opp":
        return _cmp(p.life, args[0], game.opponent(p).life)
    if kind == "hand_vs_opp":
        return _cmp(len(p.hand), args[0], len(game.opponent(p).hand))
    if kind == "link_taken":                 # cx_links: the optional action of "you may ... If you do" was taken
        return bool(getattr(item, "link_taken", False))
    if kind == "ref_card":                   # cx_links: the looked-at card is still where it went, and matches
        return linked_zone(p, item) is not None and _card_ok(item.link_card, args[0])
    if kind == "hist":
        head, n = args
        if head not in _HIST_HEADS:
            from .cx_events import compile_head
            got = compile_head("Whenever " + head)
            if got is None:
                return False
            _HIST_HEADS[head] = got
        hist = getattr(game, "_condlib_hist", None)
        return hist is not None and hist[0] == game.turn and hist[1].get((head, p.name), 0) >= n
    if kind == "any_counters":
        from .engine.state import Permanent
        ctx = getattr(item, "context", None)
        obj = prev if isinstance(prev, Permanent) else ctx if isinstance(ctx, Permanent) else source
        return obj is not None and any(v > 0 for v in obj.counters.values())
    if kind == "nth_resolve":
        if item is None:
            return False
        count = getattr(item, "_resolve_count", None)
        if count is None:
            counts = getattr(game, "_condlib_resolves", None)
            if counts is None or counts[0] != game.turn:
                counts = game._condlib_resolves = (game.turn, {})
            key = (id(source), item.name)
            count = counts[1][key] = counts[1].get(key, 0) + 1
            item._resolve_count = count
        return count == args[0]
    if kind == "prev_is":
        from .engine.state import Permanent
        obj = prev if isinstance(prev, Permanent) else getattr(item, "context", None)
        spec = args[0]
        if prev is None and not isinstance(obj, Permanent):
            prev = getattr(item, "exiled_card", None)
        if not isinstance(obj, Permanent):
            # a card target ("return target creature card ... If it's an Angel"): its printed characteristics
            return prev is not None and hasattr(prev, "types") and not spec.get("state") and _card_ok(prev, spec)
        state = spec.get("state")
        if state == "attacking":
            return obj in getattr(game, "attackers", ())
        if state == "blocking":
            return any(obj in v for v in getattr(game, "blocks", {}).values()) if isinstance(
                getattr(game, "blocks", None), dict) else False
        if state == "equipped":
            return any(x.attached_to is obj for pl in game.players for x in pl.battlefield)
        if state == "enchanted":
            return bool(obj.auras)
        return _card_ok(obj.card, spec, obj)
    if kind == "monarch":
        return getattr(game, "monarch", None) is p
    if kind == "no_monarch":
        return getattr(game, "monarch", None) is None
    if kind in ("starting", "not_starting"):
        return (game.players[0] is p) == (kind == "starting")
    if kind == "kicked":
        return _kicked(game, item, source)
    if kind == "ctx_kicked":
        ctx = getattr(item, "context", None)
        return _kicked(game, ctx, getattr(ctx, "source", None))
    if kind == "from_hand":
        if source is not None and hasattr(source, "cast_from_hand"):
            return bool(source.cast_from_hand)
        return bool(getattr(item, "cast_from_hand", False))
    if args and args[-1] == "it":
        args = args[:-1]
        ctx = getattr(item, "context", None)
        from .engine.state import Permanent
        if isinstance(ctx, Permanent):
            source = ctx
    if kind == "src_attacking":
        return source is not None and source in getattr(game, "attackers", ())
    if kind == "src_tapped":
        return source is not None and bool(getattr(source, "tapped", False)) == args[0]
    if kind == "src_creature":
        return source is not None and getattr(source, "is_creature", False)
    if kind == "src_enchanted":
        return source is not None and bool(getattr(source, "auras", ()))
    if kind == "src_equipped":
        return source is not None and any(x.attached_to is source for x in source.controller.battlefield)
    if kind == "src_power":
        return source is not None and _cmp(getattr(source, "power", 0), *args)
    if kind == "died_mine":
        return bool(p.creature_died_turn)
    if kind == "spells":
        return _cmp(game.spells_cast_turn(p), *args)
    if kind == "attacked":
        return p.attacked_with >= args[0]
    if kind == "total_power":
        return sum(max(0, x.power) for x in p.creatures) >= args[0]
    if kind == "diff_powers":
        return len({x.power for x in p.creatures}) >= args[0]
    if kind == "mana":
        spent = getattr(source, "mana_spent", None) if source is not None else None
        if spent is None:
            spent = getattr(item, "mana_spent", 0)
        return spent >= args[0]
    if kind == "x":
        x = getattr(item, "x", None)
        if not x and source is not None:
            x = getattr(source, "entered_x", 0)
        return (x or 0) >= args[0]
    if kind == "counters":
        name, op, n = args
        return source is not None and _cmp(source.counters.get(name, 0), op, n)
    return False


def _eval_any(game, p, code, item, source, prev=None):
    """Evaluate a sub-code that may be a library code or an existing engine condition name."""
    owned = check(game, p, code, item, source, prev)
    if owned is not None:
        return owned
    from .cards.model import Effect
    return game.check_cond(p, Effect("lib", cond=code), item, prev)


def linked_zone(p, item):
    """The zone holding the card cx_links remembered (top of library, or in exile / the graveyard), or None."""
    card = getattr(item, "link_card", None)
    if card is None:
        return None
    zone = getattr(item, "link_zone", "library")
    if zone == "library":
        return p.library if p.library and p.library[-1] is card else None
    cards = p.exile if zone == "exile" else p.graveyard
    return cards if any(c is card for c in cards) else None


def as_static(phrase: str) -> str:
    """A code for "as long as <phrase>" statics: always a ``lib:`` code, so ``Permanent.condition`` routes it here."""
    code = parse(phrase)
    if not code or code.startswith("lib:"):
        return code
    return _code("and", code)


def holds(perm, code: str) -> bool:
    """Static ("as long as") use: evaluated from the permanent's own point of view."""
    p = perm.controller
    game = _game_of(p)
    if game is None:
        return False

    class _Src:
        source = perm
        context = None
    return bool(_eval_any(game, p, code, _Src, perm))
