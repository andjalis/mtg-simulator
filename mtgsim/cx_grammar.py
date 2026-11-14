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

_PLAYERS = {"you": "you", "each player": "each", "players": "each", "each opponent": "opponents",
            "your opponents": "opponents", "that player": "that_player",
            "defending player": "defending", "that creature's controller": "controller",
            "that permanent's controller": "controller", "its controller": "controller", "its owner": "owner",
            "that creature's owner": "owner", "that spell's controller": "spell_controller"}


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
    if low in ("it", "that creature", "that permanent", "that land", "that artifact", "that enchantment",
               "that planeswalker"):
        return Subject("permanent", target="prev", text=text)
    m = re.fullmatch(r"(?:(each|all) )?(.+) target (player|opponent) controls", text, re.I)
    if m:           # "creatures target player controls", "each nonartifact creature target opponent controls"
        noun = _noun(m[2], plural=not (m[1] and m[1].lower() == "each"))
        if noun is None or "controller" in noun.get("selector", {}) or "you control" in m[2].lower():
            return None
        return Subject("group", target="player", data={"filter": "opp"} if m[3].lower() == "opponent" else {},
                       group=noun, text=text)
    m = re.fullmatch(r"target (.+) other than ~", text, re.I)
    if m:           # "target creature other than ~"
        found = subject("target " + m[1])
        if found is None or found.kind != "permanent" or found.copies != 1:
            return None
        found.data["other"] = True
        return found
    m = re.fullmatch(r"(?:(up to) )?(?:(a|one or two|one|two|three|four|five) )?(other |another )?target (.+?)( each)?",
                     text, re.I)
    if m and not (m[1] and not m[2]) and not (m[1] and m[2].lower() == "one or two"):
        n = 2 if m[2] and m[2].lower() == "one or two" else _NUMBER[m[2].lower()] if m[2] else 1
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
        if m[2] and m[2].lower() == "one or two":
            data["optional_from"] = 1       # the first target is required, the second optional
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

def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _split(s: str):
    """(subject text, verb chain) at the first registered verb head, or None."""
    _load()
    for m in _heads()[0].finditer(s):
        if m.start() > 0 and s[m.start() - 1] == " ":
            return s[:m.start() - 1], s[m.start():]
    return None


def parse_sentence(s: str):
    """Effects for one whole sentence, or None."""
    s = s.strip().rstrip(".").strip()
    s = re.sub(r"^(?:then |have )", "", s, flags=re.I)     # "have": the outer "you may" recursion keeps the choice
    _load()
    for rx, fn, _ in RIDERS:
        m = rx.fullmatch(s)
        if m:
            effects = fn(m, parse_sentence)
            if effects:
                return effects
    m = re.fullmatch(r"(.+?) for each (.+?)( until end of turn)?", s, re.I)
    if m and not re.search(r"\bfor each\b", m[2], re.I):
        return _for_each(m[1] + (m[3] or ""), m[2])
    duration = ""
    m = re.fullmatch(rf"{_EOT}, (.+)", s, re.I)
    if m:
        s, duration = m[1], "eot"
    m = re.fullmatch(rf"(.+) {_EOT}", s, re.I)
    if m:
        if duration:
            return None
        s, duration = m[1], "eot"
    m = re.fullmatch(r"(.+?) this (turn|combat)", s, re.I)
    if m and not duration:
        s, duration = m[1], m[2].lower()
    bare = _heads()[2]
    if bare is not None and bare.match(s):
        subj, chain = Subject("imperative", who="you", text=""), s
    else:
        split = _split(s)
        if split is None:
            return None
        subj, chain = subject(split[0]), split[1]
    if subj is None:
        return None
    parts = _clauses(chain, subj, duration)
    return None if parts is None else assemble(subj, parts)


_HELPS = ("pump", "grant", "gain_life", "draw", "cx_set_base")


def side(effects) -> str:
    """Whose side a chosen player should be on: "mine" when the effects only help, else "theirs"."""
    kinds = [e.kind for e in effects]
    if kinds and kinds[0] == "draw" and set(kinds) <= {"draw", "discard", "discard_random"}:
        return "mine"           # "draws two cards, then discards a card": card selection, wanted by its controller
    hurt = any(e.kind not in _HELPS or e.data.get("side") == "theirs" for e in effects)
    return "theirs" if hurt else "mine"


def assemble(subj: Subject, parts: list):
    """Effects for a one-shot subject and its Parts, or None."""
    if subj.kind in ("group", "player") and any(p.obj is not None for p in parts):
        return None
    if subj.kind == "group":
        inner = [_effect(p.kind, p.amount, p.amount2, target="self", data=p.data) for p in parts]
        data = dict(subj.data, group=subj.group, effects=inner, **_x_flag(parts))
        flt = data.pop("filter", "")
        if subj.target == "player":         # "creatures target player controls": the AI picks the player by side
            data["side"] = "theirs" if flt == "opp" else side(inner)
        return [_effect("cx_group", target=subj.target, filter=flt, data=data)]
    if subj.kind == "player":
        inner = [_effect(p.kind, p.amount, p.amount2, target="that_controller", data=p.data) for p in parts]
        if subj.who == "target" and subj.data.get("filter") == "opp":   # the only choice, whatever the verbs do
            return [_effect("cx_players", target="player", filter="opp",
                            data={"who": "target", "side": "theirs", "effects": inner, **_x_flag(parts)})]
        if subj.who == "target":
            if side(inner) == "theirs" and any(side([e]) == "mine" for e in inner):
                return None         # helps and hurts: which player the controller wants isn't clear
            return [_effect("cx_players", target="player", filter=subj.data.get("filter", ""),
                            data={"who": "target", "side": side(inner), "effects": inner, **_x_flag(parts)})]
        return [_effect("cx_players", data={"who": subj.who, "effects": inner, **_x_flag(parts)})]
    if subj.kind == "imperative" and any(p.obj is None for p in parts):
        return None             # an imperative verb names its own object
    out = []
    for i in range(subj.copies):
        placed = obj_since = False
        subj_i = subj
        if i >= subj.data.get("optional_from", subj.copies):
            subj_i = dataclasses.replace(subj, data=dict(subj.data, optional_target=True))
        for p in parts:
            if p.obj is not None:
                effects = _place(p, p.obj, subj_i)
                if effects is None:
                    return None
                out += effects
                obj_since = True
            elif not placed:
                out.append(_effect(p.kind, p.amount, p.amount2, target=subj.target, data=dict(subj_i.data, **p.data)))
                placed, obj_since = True, False
            elif subj.target == "permanent" and obj_since:
                return None     # "prev" would now mean the object's target, not the subject
            else:
                out.append(_effect(p.kind, p.amount, p.amount2, target="prev" if subj.target == "permanent"
                                   else subj.target, data=p.data))
    return out


def _x_flag(parts) -> dict:
    """{"x": True} when an inner Part's amount is the X paid: the wrapper then carries it, so the AI sizes X and
    Game.resolve puts X in the wrapper's amount, which cx_group / cx_players hand to those Parts."""
    return {"x": True} if any(p.data.get("x") for p in parts) else {}


def _place(p: Part, obj: Subject, subj: Subject):
    """Effects for a Part with its own object; the clause subject (if any) goes in data["source"]."""
    data = dict(p.data)
    if subj.kind != "imperative":
        data["source"] = subj.target
    if obj.kind == "group":
        inner = [_effect(p.kind, p.amount, p.amount2, target="self", data=data)]
        gdata = dict(obj.data, group=obj.group, effects=inner)
        flt = gdata.pop("filter", "")
        if obj.target == "player":
            gdata["side"] = "theirs" if flt == "opp" else side(inner)
        return [_effect("cx_group", target=obj.target, filter=flt, data=gdata)]
    if obj.kind == "player" and obj.who != "target":
        return [_effect(p.kind, p.amount, p.amount2, data=dict(data, who=obj.who))]
    if obj.kind == "host":
        return [_effect(p.kind, p.amount, p.amount2, target="host", data=data)]
    if obj.kind == "player" and "side" not in data:     # a target player: the AI picks one by side
        flt = obj.data.get("filter", "")
        data["side"] = "theirs" if flt == "opp" else side([_effect(p.kind, data=data)])
    first_optional = obj.data.get("optional_from", obj.copies)
    return [_effect(p.kind, p.amount, p.amount2, target=obj.target, filter=obj.data.get("filter", ""),
                    data=dict({k: v for k, v in obj.data.items() if k != "filter"},
                              **data, **({"optional_target": True} if i >= first_optional else {})))
            for i in range(obj.copies)]


_SCALED = ("pump", "debuff_one", "gain_life", "lose_life", "draw", "discard", "mill")


def _for_each(rest: str, desc: str):
    """"<sentence> for each <thing>": the sentence with its amounts multiplied by the count, read through the
    ", where X is the number of ..." quantities (cards.clauses._xq)."""
    spec = _count_spec(desc)
    if spec is None:
        return None
    effects = parse_sentence(rest)
    if not effects:
        return None
    scaled = [e for e in effects for e in ([e] + list(e.data.get("effects", ())))
              if e.kind in _SCALED or e.data.get("scales")]
    if not scaled:
        return None
    return [dataclasses.replace(e, data=dict(e.data, xq=spec)) for e in effects]


_COUNT_STOPS = {"among", "in", "you", "you've", "your", "they've", "that", "with", "without", "of", "on", "from",
                "named", "attached", "they", "their", "who", "which", "beyond", "except", "removed", "destroyed",
                "exiled", "sacrificed", "put", "revealed", "discarded", "milled", "returned"}


def _count_spec(desc: str):
    """The X-quantity spec for "the number of <desc, made plural>", or None."""
    from .cards.clauses import _xq
    from .cx_events import _IRREGULAR
    plural = {v.lower(): k.lower() for k, v in _IRREGULAR.items()}
    words = desc.split()
    # the head noun is the word before the phrase's first preposition / relative ("basic land TYPE among lands you
    # control", "tapped ARTIFACT you control", "creature CARD in your graveyard"): only it is made plural, so a
    # loose "the number of <anything> you control" match on an earlier word can't stand in for the phrase (#373)
    head_at = next((j - 1 for j, w in enumerate(words) if j and w.lower() in _COUNT_STOPS), len(words) - 1)
    for i, w in enumerate(words):
        if i != head_at:
            continue
        low = w.lower()
        many = plural.get(low) or (low[:-1] + "ies" if low.endswith("y") and low[-2:-1] not in "aeiou"
                                   else low + "es" if low.endswith(("s", "x", "ch", "sh")) else low + "s")
        if w[:1].isupper():
            many = many.capitalize()
        phrase = " ".join(words[:i] + [many] + words[i + 1:])
        spec = _xq("the number of " + phrase)
        if spec is None:
            continue
        # the plural we made up names a thing: use the word as written ("soot counter": counters are stored "soot")
        spec = spec[:1] + tuple(w.lower() if isinstance(v, str) and v.lower() == many.lower() else v for v in spec[1:])
        if spec[0] == "count" and isinstance(spec[1], str) and \
                any(x in _COUNT_STOPS - {"you"} for x in spec[1].lower().split()):
            return None     # the loose "the number of ... you control" swallowed a phrase it can't count
        if spec[0] == "count" and isinstance(spec[1], str) and " " in re.sub(r"^other ", "", spec[1]):
            # an adjective the plain count can't read ("legendary creature"): the battlefield selector, or nothing
            from .permanent_templates import selector as perm_selector
            sel = perm_selector(phrase, plural=True)
            return ("selector", sel) if sel else None
        if spec[0] == "count" and isinstance(spec[1], str):
            # _xq singularises with a plain trailing "s" ("Elves" -> "Elve"): name the thing as written instead.
            head = " ".join(words[:i + 1])
            if re.sub(r"^other ", "", spec[1]) != re.sub(r"^other ", "", head):
                spec = (spec[0], head) + tuple(spec[2:])
        return spec
    return None


def parse_fallback(s: str, effects: list) -> bool:
    """The _parse_effects hook: append the sentence's effects and return True, or return False."""
    if re.fullmatch(r"(?:it's|it is) still an? (land|planeswalker)\.?", s.strip(), re.I) and effects \
            and effects[-1].kind == "cx_animate" and not effects[-1].data.get("addition"):
        effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, still=s.split()[-1].rstrip(".").capitalize()))
        return True         # "~ becomes a 2/2 artifact creature until end of turn. It's still a land."
    those = re.fullmatch(r"(?:those creatures|they|those permanents) (.+)", s.strip().rstrip("."), re.I)
    if those and effects and effects[-1].kind in ("cx_group", "permanent_group"):
        # "Creatures your opponents control get -1/-1 until end of turn. Those creatures can't block this turn.":
        # the same members (fixed when the group resolves), so the new verbs join the group's inner effects.
        new = parse_sentence("Creatures " + those[1])
        if new and len(new) == 1 and new[0].kind == "cx_group" and new[0].target == "none":
            last = effects[-1]
            inner = list(last.data.get("effects") or [last.data["effect"]])
            effects[-1] = dataclasses.replace(last, data=dict({k: v for k, v in last.data.items() if k != "effect"},
                                                              effects=inner + list(new[0].data["effects"])))
            return True
    new = parse_sentence(s)
    rest = s.strip()[4:]
    if not new and re.match(r"you ", s.strip(), re.I) and _heads()[2] is not None and _heads()[2].match(rest):
        new = parse_sentence(rest)          # "You gain control of target creature": the imperative
    if not new:
        return False
    if any(e.kind == "damage" and e.target == "any" and e.data.get("other") for e in new):
        from .engine.state import TARGETED
        if any(e.target in TARGETED for e in effects):
            return False    # "any other target" can refer to an earlier target (Bond of Passion), not the source
    effects += new
    return True


# ---------------------------------------------------------------- static lines

def parse_static(line: str, st) -> bool:
    """A static ability granting a group (or the enchanted / equipped creature) P/T, keywords or a combat
    restriction, recorded where the engine reads them: advanced_rules["anthems"] and static_keyword_grants for a
    group, equip_bonus / equip_keywords for the host. Returns True when the line is consumed."""
    s = line.strip()
    if s.endswith(".") and not re.search(r'[:"]', s) \
            and re.search(r"\b(?:as long as|for each|where X is)\b|(?:^|, |— )during your turn\b", s, re.I):
        from .cx_static_gate import parse_line as gated          # "As long as C, <static>", "+1/+1 for each Q"
        return gated(s, st)
    if not s.endswith(".") or re.search(r'[:"]|\b(?:until|this turn|as long as|if(?! able)|for each|where|except)\b',
                                        s, re.I) or re.search(r"(?:^|, |— )during\b", s, re.I):
        return False            # conditions and durations ("During your turn, ...") are other lanes' statics
    s = re.sub(r"^[A-Z][\w' ,-]* — ", "", s[:-1])        # an ability word
    split = _split(s)
    if split is None:
        return False
    subj = subject(split[0])
    if subj is not None and subj.kind == "player" and subj.who in ("you", "opponents", "each"):
        parts = _clauses(split[1], subj, "static")       # "Your opponents can't cast creature spells."
        if not parts or any(p.kind != "cx_static" for p in parts):
            return False
        rules = st.extra.setdefault("advanced_rules", {})
        for p in parts:
            key = p.data["rule"] + "@players"
            rules[key] = tuple(rules.get(key, ())) + ((subj.who, p.data["value"]),)
        return True
    if subj is None or subj.kind not in ("group", "host", "permanent") or subj.target != "none" and subj.kind == "group" \
            or subj.kind == "permanent" and subj.target != "self":
        return False
    parts = _clauses(split[1], subj, "static")
    if parts is None or any(p.kind not in ("pump", "grant", "cx_temp_kw", "cx_static") for p in parts) \
            or sum(p.kind == "pump" for p in parts) > 1:
        return False
    if subj.kind == "permanent" and any(p.kind != "cx_static" for p in parts):
        return False            # "~ gets +1/+1" and "~ has flying" are other parsers' lines
    rules = st.extra.setdefault("advanced_rules", {})
    for p in [p for p in parts if p.kind == "cx_static"]:       # a rule a family reads with static_rules()
        key = p.data["rule"] + {"permanent": "", "host": "@host", "group": "@group"}[subj.kind]
        if subj.kind == "host" and (subj.text.lower().startswith("equipped") and "Equipment" not in st.type_line
                                    or subj.text.lower().startswith("enchanted") and not st.extra.get("aura")):
            return False
        value = (dict(subj.group["selector"]) if "selector" in subj.group else dict(subj.group), p.data["value"]) \
            if subj.kind == "group" else p.data["value"]
        rules[key] = tuple(rules.get(key, ())) + (value,)
    parts = [p for p in parts if p.kind != "cx_static"]
    if not parts:
        return True
    kws = tuple(k for p in parts if p.kind != "pump"
                for k in ([p.data["keyword"]] if p.kind == "grant" else sorted(p.data["keywords"])))
    pt = next(((p.amount, p.amount2) for p in parts if p.kind == "pump"), None)
    extra = st.extra
    if subj.kind == "host":
        if subj.text.lower().startswith("equipped") and "Equipment" not in st.type_line \
                or subj.text.lower().startswith("enchanted") and not extra.get("aura"):
            return False
        if pt:
            bp, bt = extra.get("equip_bonus", (0, 0))
            extra["equip_bonus"] = (bp + pt[0], bt + pt[1])
        if kws:
            extra["equip_keywords"] = frozenset(extra.get("equip_keywords", frozenset())) | set(kws)
        return True
    group = subj.group
    spec = group["selector"] if "selector" in group else dict(group)
    if _stat_conditioned(spec):
        return False    # "creatures with power 2 or less get +1/+1" would read its own result
    from .cards.model import KEYWORDS
    if _condition_keywords(spec) and any(k in KEYWORDS for k in kws):
        return False    # "creatures with flying have shroud" and a "with shroud ... flying" grant would read each other
    if pt:
        extra.setdefault("advanced_rules", {}).setdefault("anthems", []).append((spec, pt[0], pt[1]))
    if kws:
        extra["static_keyword_grants"] = extra.get("static_keyword_grants", ()) + ((spec, kws),)
    return True


def _stat_conditioned(spec) -> bool:
    if "stat" in spec and spec["stat"][0] != "mana value" or "base_pt" in spec:
        return True
    if "cx_desc" in spec:
        desc = _desc(spec["cx_desc"], spec["plural"])
        return desc is None or any(w[0] in ("power>=", "power<=", "tough>=", "power>self", "power=tough")
                                   for w in desc["with"])
    return False


def _condition_keywords(spec) -> set:
    """The keywords a group's membership depends on ("creatures with flying")."""
    if "keyword" in spec:
        return {spec["keyword"][0]}
    if "cx_desc" in spec:
        desc = _desc(spec["cx_desc"], spec["plural"])
        return {w[1] for w in desc["with"] if w[0] in ("kw", "nokw")} if desc else set()
    return set()


# ---------------------------------------------------------------- AI values

AI_VALUES: dict = {}


def ai_value(*kinds):
    """Register how good one inner effect of a grammar group / player effect is for the AI:
    ``@ai_value("destroy")`` on ``fn(game, me, eff, obj) -> float``. obj is a group member (Permanent) or a named
    player (Player); return the value for ``me`` (positive good, signed by whose obj is). HeuristicAI sums it over
    a cx_group's members or a cx_players's players and casts above a sweep bar."""
    def register(fn):
        for k in kinds:
            AI_VALUES[k] = fn
        return fn
    return register


_COMBAT = ("pump", "grant", "cx_lose_kw", "cx_temp_kw")


def member_value(game, me, eff, obj):
    """(value for me, combat_only) of one inner effect on one member or player: a registered ai_value, else the
    built-in values for the core families."""
    from .ai import life_value, perm_value
    from .engine.state import Permanent
    _load()
    fn = AI_VALUES.get(eff.kind)
    if fn is not None:
        return fn(game, me, eff, obj), False
    mine = getattr(obj, "controller", obj) is me
    sign = 1.0 if mine else -1.0
    a, b = eff.amount, eff.amount2
    if isinstance(obj, Permanent):
        if not obj.is_creature:
            return 0.0, False
        if eff.kind == "debuff_one":
            if obj.toughness - obj.damage <= b and not obj.has("indestructible"):
                return -sign * (perm_value(obj) + 1), False            # it dies
            return -sign * 0.3 * a, False
        if eff.kind == "cx_set_base":
            return sign * 0.5 * ((a - obj.power) + (b - obj.toughness)), False
        if eff.kind in _COMBAT:
            helps = eff.kind in ("pump", "grant") or eff.data.get("side") == "mine"
            if helps and mine and obj.can_attack():
                return 0.5 * (a + (1 if eff.kind != "pump" else 0)), True
            if not helps and not mine:
                return 0.4, True
            return 0.0, True
        return 0.0, False
    if eff.kind == "draw":
        return sign * 1.5 * a, False
    if eff.kind == "gain_life":
        return sign * (life_value(obj.life + a) - life_value(obj.life)), False
    if eff.kind == "lose_life":
        return -sign * (life_value(obj.life) - life_value(obj.life - a)), False
    if eff.kind == "discard":
        return -sign * (0.8 if mine else 1.0) * min(a, len(obj.hand)), False
    if eff.kind == "mill":
        return -sign * 0.1 * a, False
    return 0.0, False


# ---------------------------------------------------------------- static rules (cx_static / cx_rule_turn Parts)

def static_rules(game, perm, rule: str) -> list:
    """Every value of a family rule that applies to perm now: its own static (Part("cx_static", data={"rule": r,
    "value": v}) on "~"), its Aura's or Equipment's ("enchanted / equipped creature ..."), a group static whose
    group it is in, and this turn's one-shots (Part("cx_rule_turn", ...))."""
    from .permanent_templates import matches
    out = []
    if not getattr(perm, "abilities_suppressed", False):
        out += list(perm.card.advanced_rules.get(rule, ()))
    for x in list(getattr(perm, "auras", ())) + list(getattr(perm, "equipment", ())):
        out += list(x.card.advanced_rules.get(rule + "@host", ()))
    if game is not None:
        for pl in game.players:
            for x in pl.battlefield:
                for spec, value in x.card.advanced_rules.get(rule + "@group", ()):
                    if not x.abilities_suppressed and matches(game, perm, spec, x.controller, x):
                        out.append(value)
        out += [v for turn, r, v in getattr(perm, "cx_rules_turn", ()) if r == rule and turn == game.turn]
        from .cx_static_gate import rules as gated_rules     # "as long as C, ~ can't be blocked"
        out += gated_rules(game, perm, rule)
    return out


def player_rules(game, player, rule: str) -> list:
    """Every value of a family rule that applies to a player now: statics on permanents naming them ("you",
    "your opponents", "players", relative to the permanent's controller) and this turn's (cx_player_rule)."""
    out = []
    for pl in game.players:
        for x in pl.battlefield:
            if x.abilities_suppressed:
                continue
            for who, value in x.card.advanced_rules.get(rule + "@players", ()):
                if who == "each" or (who == "you") == (player is x.controller):
                    out.append(value)
    out += [v for turn, r, v, who in getattr(game, "cx_player_rules", ()) if r == rule and who is player
            and turn == game.turn]
    return out


# ---------------------------------------------------------------- engine side: who a subject names

def _defending_player(game, item):
    """The player the relevant attacker is attacking (a planeswalker: its controller; a battle: its
    protector), or None when the item names no attacker. Shared with ai.py through battles.py."""
    from .battles import defending_player
    return defending_player(game, item)


def event_spell(context) -> bool:
    """An any_cast trigger's context is the cast spell (a StackItem); "that player" is its caster."""
    from .engine.state import StackItem
    return isinstance(context, StackItem)


def players(game, p, who, item, prev, target=None):
    """The players a cx_players subject names as it resolves (the defending player is the one the attacker
    attacks; the opponent when no attacker is in play). who "target": the chosen player (target)."""
    opp = game.opponent(p)
    if who == "target":
        return [target] if target in game.players else []
    if who == "you":
        return [p]
    if who == "each":
        return list(game.players)
    if who == "defending":
        return [_defending_player(game, item) or opp]
    if who == "opponents":
        return [opp]
    if who == "that_player":
        context = item.context if item is not None else None
        context = context.controller if event_spell(context) else context
        if context not in game.players and item is not None:
            # no event player: "Target player reveals their hand. ~ deals damage to that player ..." is the player
            # this spell or ability chose (Inquisition)
            context = next((t for t in getattr(item, "targets", ()) or () if t in game.players), None)
        return [context] if context in game.players else []
    if who == "spell_controller":       # a cast trigger's spell, a spell this one targeted, or the one it targets
        from .engine.state import StackItem
        spell = (item.context if item is not None and isinstance(item.context, StackItem) else
                 prev if isinstance(prev, StackItem) else getattr(item, "target_spell", None))
        if isinstance(spell, StackItem):
            return [spell.controller]
        context = item.context if item is not None else None
        return [context] if context in game.players else []     # any_cast / "becomes the target of a spell": its controller
    if who in ("controller", "owner"):
        from .engine.state import Permanent
        if isinstance(prev, Permanent):
            return [prev.controller if who == "controller" else prev.owner]
        return [prev] if who == "controller" and prev in game.players else []
    return []


_HURTS = ("destroy", "exile_permanent", "bounce", "tap", "stun", "debuff_one", "debuff", "cx_lose_kw",
          "cant_block_turn", "damage", "oring", "shrink")
_HELPS_OBJ = ("pump", "grant", "untap_prev", "p1_counters", "regenerate", "cx_set_base", "unblockable")


def auto_side(game, eff) -> str:
    """The side for an effect whose own meaning is neutral (a colour change): read from the effects that follow
    it on the same object ("becomes red and gains haste", "becomes blue. Untap that creature."). Hurting ->
    "theirs", helping -> "mine", otherwise "theirs"."""
    for effects in _effect_lists(getattr(game, "target_source", None)):
        index = next((i for i, e in enumerate(effects) if e is eff), None)
        if index is None:
            continue
        for later in effects[index + 1:]:
            if later.target != "prev":
                break
            if later.kind in _HURTS or later.data.get("side") == "theirs":
                return "theirs"
            if later.kind in _HELPS_OBJ or later.data.get("side") == "mine":
                return "mine"
        break
    return "theirs"


def _effect_lists(source):
    if isinstance(getattr(source, "effects", None), list):     # a StackItem
        yield source.effects
        return
    card = getattr(source, "card", source)
    if card is None:
        return
    yield getattr(card, "spell_effects", [])
    for mode in getattr(card, "modes", None) or []:
        yield mode
    for holder in list(getattr(card, "activated", [])) + list(getattr(card, "triggers", [])):
        yield holder.effects


def group_members(game, p, data, source, player=None):
    """The permanents a cx_group names, fixed as the effect resolves (CR 611.2c)."""
    from .permanent_templates import matches
    group = data["group"]
    pool = player.battlefield if player is not None else [x for pl in game.players for x in pl.battlefield]
    if "selector" in group:
        return [x for x in pool if matches(game, x, group["selector"], p, source)]
    return [x for x in pool if desc_matches(game, x, group, p, source)]


def desc_matches(game, permanent, spec, controller, source) -> bool:
    """permanent_templates.matches for a selector carrying a cx_desc noun phrase."""
    if spec.get("other") and permanent is source:
        return False
    desc = _desc(spec["cx_desc"], spec["plural"])
    if desc is None:
        return False
    from .cx_events import _obj_match
    return _obj_match(game, desc, _Viewer(controller, source), permanent)


class _Viewer:
    """Who reads a noun phrase: "you control" is its controller, "greater power than ~" the source's power
    (read only when asked: a static's own P/T may depend on the phrase)."""
    def __init__(self, controller, source):
        self.controller, self._source = controller, source

    @property
    def power(self):
        return getattr(self._source, "power", 0)
