"""Compositional effect grammar: the fallback for sentences no template matches.

A sentence is read as subject + verb chain + duration; each verb phrase is handed to a registered verb parser,
which maps it onto the engine's existing effect kinds. See ``mtgsim/GRAMMAR.md`` for how to add a verb family.

    Target creature you control gets +2/+0 and gains first strike until end of turn.
    Until end of turn, attacking creatures you control get +1/+0 and gain trample.
    Up to two target creatures each get +1/+0 and gain menace until end of turn.
    Creatures target player controls can't block this turn.
    Each player discards a card, then draws a card.
    Other Elf creatures get +1/+1 and have forestwalk.                      (a static line)
    Creatures you control get +1/+0 until end of turn for each Elf you control.

This module owns the shared parts: subjects (``subject``), durations, splitting the verb chain, the verb registry
(``verb``), assembling Effects (one-shot) or static records, "for each" quantities and the noun-phrase matcher.
Verb families live in ``mtgsim/cx_grammar_<family>.py`` modules, found and imported automatically; their engine
kinds, when they need new ones, in ``mtgsim/engine/kinds/cx_grammar_<family>.py``.

Anything not understood word for word returns None, so the sentence stays ignored (never a false "full").
"""
from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import re
from dataclasses import dataclass, field

from .permanent_templates import _SUBTYPE_TYPES, keywords, selector

_SUBTYPE_NAMES = frozenset(_SUBTYPE_TYPES)
_NUMBER = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_EOT = r"until end of turn"
_PLURAL = r"\b(?:creatures|permanents|lands|artifacts|enchantments|[A-Z][a-z]+s|Elves|Dwarves|Wolves)\b"


# ---------------------------------------------------------------- the interface

@dataclass
class Subject:
    """Who a clause is about.

    kind:   "permanent"  one permanent: a target (target "permanent"), ~ ("self") or it / that creature ("prev")
            "group"      every permanent matching ``group`` when the effect resolves (target "none", or "player"
                         for "creatures target player controls")
            "player"     ``who`` names untargeted players: you, each, opponents, that_player, defending,
                         controller (of the previous target), owner
            "host"       enchanted / equipped creature
            "imperative" a sentence that starts with its verb ("Destroy target creature."): who "you"; the verb's
                         object (Part.obj) carries the target
    Players: who "target" (target "player", data filter "opp" for "target opponent") or an untargeted name.
    """
    kind: str
    target: str = "none"
    data: dict = field(default_factory=dict)
    copies: int = 1                  # "two target creatures each ..."
    group: dict | None = None        # {"selector": ...} or {"cx_desc": ..., "plural": ..., "other": ...}
    who: str = ""
    text: str = ""


@dataclass
class Clause:
    """One verb phrase as a verb parser sees it.

    verb:      the phrase, lower case, without the subject, a leading "also" or the duration ("gets +2/+0")
    subject:   the Subject
    duration:  "eot" (until end of turn), "turn" (this turn), "combat" (this combat), "" (none: a one-shot
               change that lasts, or a player action), "static" (a static ability line)
    text:      the phrase as written (original case)
    """
    verb: str
    subject: Subject
    duration: str
    text: str


@dataclass
class Part:
    """What one verb phrase does: an Effect kind with its amounts and data. The grammar adds targets.
    In a static clause only "pump" (P/T), "grant" (data["keyword"]) and "cx_temp_kw" (data["keywords"]) mean
    something; anything else makes the line unsupported."""
    kind: str
    amount: int = 0
    amount2: int = 0
    data: dict = field(default_factory=dict)
    obj: "Subject | None" = None     # the verb's own object ("deals 3 damage to any target"): placed like a subject


@dataclass(frozen=True)
class _Verb:
    rx: object
    parse: object
    subjects: tuple
    heads: tuple
    module: str


VERBS: list = []
RIDERS: list = []
_LOADED = []


def verb(pattern: str, *, heads, subjects=("permanent", "group")):
    """Register a verb parser: ``@verb(r"gets? ([+-]\\d+)/([+-]\\d+)", heads=("get", "gets"))``.

    pattern   fullmatched (case-insensitive) against Clause.verb
    heads     the words the phrase can start with; they split "gets +1/+1 and gains flying" into phrases
    subjects  the Subject kinds the verb takes
    The parser is called as ``parse(match, clause)`` and returns a list of Parts, or None to reject.
    """
    def register(fn):
        VERBS.append(_Verb(re.compile(pattern, re.I), fn, tuple(subjects), tuple(h.lower() for h in heads),
                           fn.__module__))
        _HEADS.clear()
        return fn
    return register


def rider(pattern: str):
    """Register a sentence rider: ``@rider(r"(?P<body>.+) unless (?P<who>.+) pays? (?P<cost>{.+})")``.

    pattern is fullmatched (case-insensitive) against the whole sentence (no final period) before the subject is
    split off. The parser is called as ``parse(match, inner)``; ``inner(text)`` parses a sub-sentence with the
    whole grammar (riders included) and returns its Effects or None. Return Effects, or None to reject."""
    def register(fn):
        RIDERS.append((re.compile(pattern, re.I), fn, fn.__module__))
        return fn
    return register


def _load():
    """Import every mtgsim/cx_grammar_<family>.py module once (they register their verbs)."""
    if _LOADED:
        return
    _LOADED.append(True)
    from . import __path__ as package
    for info in sorted(pkgutil.iter_modules(package), key=lambda i: i.name):
        if info.name.startswith("cx_grammar_"):
            importlib.import_module(f"{__package__}.{info.name}")


_HEADS: list = []


def _heads():
    """[head finder, chain splitter, imperative start]."""
    if not _HEADS:
        words = sorted({h for v in VERBS for h in v.heads}, key=len, reverse=True)
        alt = "|".join(re.escape(w) for w in words)
        _HEADS.append(re.compile(rf"(?:also )?(?:{alt})\b", re.I))
        _HEADS.append(re.compile(rf"(?:,? and |, (?:and )?|,? then )(?=(?:also )?(?:{alt})\b)", re.I))
        bare = sorted({h for v in VERBS if "imperative" in v.subjects for h in v.heads}, key=len, reverse=True)
        _HEADS.append(re.compile(rf"(?:{'|'.join(re.escape(w) for w in bare)})\b", re.I) if bare else None)
    return _HEADS


def parse_clause(clause: Clause):
    """The Parts for one verb phrase: the first registered parser that takes it, or None."""
    _load()
    for v in VERBS:
        if clause.subject.kind not in v.subjects:
            continue
        m = v.rx.fullmatch(clause.verb)
        if m:
            parts = v.parse(m, clause)
            if parts is not None:
                return parts
    return None


def _clauses(text: str, subj: Subject, duration: str):
    """Parts for a whole verb chain, or None."""
    parts = []
    for phrase in _heads()[1].split(text):
        verb_text = re.sub(r"^also ", "", phrase.strip(), flags=re.I)
        got = parse_clause(Clause(verb_text.lower(), subj, duration, verb_text))
        if not got:
            return None
        parts += got
    return parts or None


# ---------------------------------------------------------------- shared vocabulary for verb families

def keyword_list(text: str):
    """["flying", "first strike"] for "flying and first strike", or None for anything not a known keyword."""
    kws = keywords(text.strip())
    if kws:
        return kws
    m = re.fullmatch(r"protection from (\w+)(?:,? and from (\w+))?", text.strip(), re.I)      # "... and from blue"
    if m:
        from .cards.model import KEYWORDS
        out = [f"protection from {c.lower()}" for c in m.groups() if c]
        return out if all(k in KEYWORDS for k in out) else None
    return None


def count(word: str):
    """1 for "a" / "one" / "1", ..., or None."""
    from .cards.model import NUMBERS
    return NUMBERS.get(word.lower()) or (int(word) if word.isdigit() else None)


# ---------------------------------------------------------------- subjects

_PLAYERS = {"you": "you", "each player": "each", "each opponent": "opponents", "that player": "that_player",
            "defending player": "defending", "that creature's controller": "controller",
            "that permanent's controller": "controller", "its controller": "controller", "its owner": "owner",
            "that creature's owner": "owner"}


def _desc(text: str, plural: bool):
    """A cx_events object spec for a noun phrase, or None (no self / host / other readings)."""
    from .cx_events import _object_subject
    first = text.split(" ", 1)[0]
    if first[:1].isupper() and _subtype(first) not in _SUBTYPE_NAMES:
        text = first.lower() + text[len(first):]            # sentence-initial capital, not a subtype
    spec = _object_subject(("one or more " if plural else "a ") + text)
    if spec is None or spec["self"] or spec["host"] or spec["other"]:
        return None
    # The trigger grammar reads any capitalised word as a subtype: only real subtypes count here.
    if any(w[:1].isupper() and _subtype(w) not in _SUBTYPE_NAMES for alt in spec["alts"] for w in alt):
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
    """The Subject a phrase names, or None."""
    text = text.strip()
    low = text.lower()
    if low in _PLAYERS:
        return Subject("player", who=_PLAYERS[low], text=text)
    if low in ("target player", "target opponent"):
        return Subject("player", target="player", who="target", text=text,
                       data={"filter": "opp"} if low.endswith("opponent") else {})
    if low in ("enchanted creature", "equipped creature"):
        return Subject("host", target="host", text=text)
    if low in ("~", "this creature", "this permanent"):
        return Subject("permanent", target="self", text=text)
    if low in ("it", "that creature", "that permanent"):
        return Subject("permanent", target="prev", text=text)
    m = re.fullmatch(r"creatures target (player|opponent) controls", low)
    if m:
        return Subject("group", target="player", data={"filter": "opp"} if m[1] == "opponent" else {},
                       group={"selector": {"types_all": ["creature"]}}, text=text)
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
        return Subject("permanent", target="permanent", data=data, copies=n, text=text)
    m = re.fullmatch(r"(each|all) (.+)", text, re.I)
    words = m[2] if m else text
    if not m and not re.search(_PLURAL, words):
        return None         # a bare singular noun phrase is not a subject
    noun = _noun(words, plural=not (m and m[1].lower() == "each"))
    if noun is None:
        return None
    return Subject("group", group=noun, text=text)


_TARGETS = {"any target": "any", "target creature or planeswalker": "creature_pw",
            "target creature or player": "any", "target player or planeswalker": "player"}


def object_phrase(text: str):
    """The Subject a verb's object names ("any target", "target creature or planeswalker", "target player",
    "each creature you control", "that creature's controller", ...), or None. Read like subject()."""
    low = text.strip().lower()
    if low in _TARGETS:
        data = {"or_pw": True} if low == "target player or planeswalker" else {}
        return Subject("player" if _TARGETS[low] == "player" else "permanent", target=_TARGETS[low], data=data,
                       who="target" if _TARGETS[low] == "player" else "", text=text)
    return subject(text)


# ---------------------------------------------------------------- one-shot sentences

