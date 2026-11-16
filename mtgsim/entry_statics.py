"""#630: statics that change how a group of permanents enters.

    Nonbasic lands your opponents control enter tapped.                         (Archon of Emeria)
    Creatures and nonbasic lands your opponents control enter tapped.           (Thalia, Heretic Cathar)
    Artifacts and lands enter tapped.                                           (Root Maze)
    Each other creature you control enters with an additional +1/+1 counter on it.   (Renata)
    Colorless creatures you control enter with two additional +1/+1 counters on them. (Curator Beastie)
    Each planeswalker you control enters with an additional loyalty counter on it.   (Oath of Gideon)

Recorded on the source as ``advanced_rules["entry_tapped"]`` ((filter specs, scope),) with scope "opp" / "you" /
"all", and ``advanced_rules["entry_counters"]`` ((filter specs, counter kind, amount, other),). The filters are the
condition library's card filters, read on the entering permanent. ``Game.enter_battlefield`` asks ``tapped`` and
``counters`` for every permanent that enters (replacement effects, CR 614.1c/d: the permanent enters that way).
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}
_TYPES = {"creatures": "creature", "lands": "land", "artifacts": "artifact", "enchantments": "enchantment",
          "planeswalkers": "planeswalker", "permanents": "permanent", "battles": "battle"}
_TAPPED = re.compile(r"(?P<g>[\w, -]+?) (?:(?P<who>your opponents control|you control) )?enter tapped\.")
_COUNTERS = re.compile(r"(?:Each )?(?P<other>other )?(?P<g>[\w -]+?) you control enters? with (?P<n>an|a|one|two|three) "
                       r"additional (?P<k>\+1/\+1|-1/-1|loyalty) counters? on (?:it|them)\.")


def _singular(text: str):
    """"Creatures and nonbasic lands" -> "creature and nonbasic land"; None for a plural it can't singularise."""
    from .cx_condlib import _PLURAL_SUB
    words = []
    for w in text.split():
        low = w.lower()
        if low in _TYPES:
            words.append(_TYPES[low])
        elif low in _PLURAL_SUB:
            words.append(_PLURAL_SUB[low])
        elif w[0].isupper() and w.endswith("s") and low not in ("nonbasic",) and len(words) == len(text.split()) - 1:
            words.append(w[:-1])                 # a subtype last: "Dragons" (not "Elves": _PLURAL_SUB handles those)
        else:
            words.append(w)
    return " ".join(words)


def _specs(group: str, plural: bool):
    from .cx_flash_perm import specs_for
    g = group.strip()
    if re.search(r"\b[Nn]on-[A-Z]", g):
        return None             # "Non-Phyrexian": a negated subtype the card filter doesn't read
    g = g[0].lower() + g[1:] if g.split()[0].lower() in _TYPES or g.split()[0].lower() in (
        "nonbasic", "colorless", "nontoken", "legendary", "each") else g
    g = re.sub(r"^each ", "", g, flags=re.I)
    if plural:
        g = _singular(g)
    return specs_for(g) or None


def parse_line(line: str, st) -> bool:
    line = re.sub(r"^[A-Z][\w' ]+ — ", "", line) if line.count(" — ") == 1 else line     # an ability word
    m = _TAPPED.fullmatch(line)
    if m and not m["g"].lower().startswith(("~", "it ", "they ")):
        specs = _specs(m["g"], plural=True)
        if not specs:
            return False
        scope = {"your opponents control": "opp", "you control": "you", None: "all"}[m["who"]]
        rules = st.extra.setdefault("advanced_rules", {})
        rules["entry_tapped"] = tuple(rules.get("entry_tapped", ())) + ((specs, scope),)
        return True
    m = _COUNTERS.fullmatch(line)
    if m:
        plural = line.split(" you control ")[1].startswith("enter ")
        specs = _specs(m["g"], plural=plural)
        if not specs:
            return False
        rules = st.extra.setdefault("advanced_rules", {})
        rules["entry_counters"] = tuple(rules.get("entry_counters", ())) + (
            (specs, m["k"].lower(), _N[m["n"].lower()], bool(m["other"])),)
        return True
    return False


def _sources(game, key):
    for pl in game.players:
        for x in pl.battlefield:
            if not x.abilities_suppressed and key in x.card.advanced_rules:
                yield x


def tapped(game, perm) -> bool:
    from .cx_condlib import _card_ok
    for src in _sources(game, "entry_tapped"):
        for specs, scope in src.card.advanced_rules["entry_tapped"]:
            if scope == "opp" and perm.controller is src.controller or scope == "you" and perm.controller is not \
                    src.controller:
                continue
            if any(_card_ok(perm.card, s, perm) for s in specs):
                return True
    return False


def counters(game, p, perm):
    from .cx_condlib import _card_ok
    for src in list(_sources(game, "entry_counters")):
        if src.controller is not p:
            continue
        for specs, kind, n, other in src.card.advanced_rules["entry_counters"]:
            if other and src is perm:
                continue
            if any(_card_ok(perm.card, s, perm) for s in specs):
                perm.counters[kind] = perm.counters.get(kind, 0) + n
