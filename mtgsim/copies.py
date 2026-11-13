"""Copy effects: token copies of permanents, clones that enter as a copy, and copies of spells.

Rules text is matched by the patterns below, which mtgsim.cards adds to its own templates; the
engine hands the effect kinds in KINDS to resolve() here.

    Create a token that's a copy of target creature you control[, except ...].
    Create X tokens that are copies of target artifact or creature you control.
    For each nontoken creature you control, create a token that's a copy of that creature.
    Create a token that's a copy of ~.
    You may have ~ enter as a copy of any creature on the battlefield[, except ...].
    When you next cast an instant or sorcery spell this turn, copy that spell [twice].
    Copy target instant or sorcery spell you control.  /  (cast trigger) copy that spell.
    Targeted spell copies choose a spell on the stack, honoring controller, type, mana-value and target restrictions.

    ~ becomes a copy of target creature you control until end of turn.  (reverts in the cleanup step)
    Copy target activated or triggered ability you control [from a creature source] [X times].

Simplifications: the permanent to copy is picked when the effect resolves (so "target"
only checks hexproof on the opponent's permanents), the legend rule isn't modelled (so "except it
isn't legendary" changes nothing), and a token sacrificed "at the beginning of the next end step"
goes at its controller's end step.

This module imports mtgsim.cards and mtgsim.engine lazily, inside functions, because both import it.
"""
from __future__ import annotations

import dataclasses
import re

KINDS = {"copy_perm", "copy_spell", "copy_next_spell", "copy_sac", "become_copy", "copy_ability"}

_KW = (r"flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|"
       r"indestructible|menace|reach|defender|flash|prowess")
_COLOR_CODES = dict(zip(("white", "blue", "black", "red", "green"), "WUBRG"))
_COLORS = set(_COLOR_CODES) | {"colorless"}
_TYPES = {"artifact": "Artifact", "creature": "Creature", "enchantment": "Enchantment", "land": "Land",
          "planeswalker": "Planeswalker", "instant": "Instant", "sorcery": "Sorcery"}
_SAC_QUOTE = re.compile(r'"At the beginning of the end step, sacrifice ~\.?"\.?')
_N = r"(a|an|one|two|three|four|five|X)"


# ------------------------------------------------------------------ parsing

def _num(word: str):
    from .cards import _num as num
    return "x" if word == "X" else num(word)


_SUBJ = r"(?:it|he|she|they|the tokens?|the copy|each (?:token|copy)|those (?:tokens|creatures))"
_POSS = r"(?:its|his|her|their)"
_BE = r"(?:'s|'re| is| are| isn't| is not| aren't| are not)"
# Where one exception clause ends and the next begins: before a subject, or before a bare predicate
# that continues the previous subject ("it isn't legendary, is an artifact ..., and has myriad").
_CLAUSE_SPLIT = re.compile(rf"(?:,? and |, )(?=(?:{_SUBJ}|{_POSS} name|is|are|has|have|gains?|enters?)\b)", re.I)
_TYPE_WORD = {**_TYPES, **{k + "s": v for k, v in _TYPES.items()}}
_COUNTER = r"(?P<counter>\+1/\+1|loyalty|shield)"


_FIELD_KEYWORDS = {"exalted", "cascade", "storm", "flanking", "rebound", "undying", "persist", "split second"}


def _keywords(text: str):
    """"flying, trample, and haste" as a frozenset of engine keywords (changeling apart), or None."""
    from .cards.model import KEYWORDS
    words = [w.strip().lower() for w in re.split(r",? and |, ", text) if w.strip()]
    # Keywords the engine reads through Permanent.has(); the others also need CardDef fields or triggers.
    if not words or any((w not in KEYWORDS or w in _FIELD_KEYWORDS) and w != "changeling" for w in words):
        return None
    return frozenset(words)


def _type_phrase(c: str, mods: dict) -> bool:
    """"it's a 4/4 black Zombie", "they're 3/3 Dragon creatures in addition to their other types", "it's
    legendary", "it's a 0/2 Thopter artifact creature with flying in addition to its other types".
    Without "in addition", the named colours, card types and subtypes replace the copied ones (rule 707.9b)."""
    m = re.fullmatch(rf"(?:{_SUBJ}(?:'s|'re| is| are)|is|are) (?:also )?(?:an? )?(?:(?P<p>\d+)/(?P<t>\d+) ?)?(?P<words>[\w' -]*?)"
                     rf"(?: with (?P<kw>[a-z ,]+?))?"
                     rf"(?P<add> in addition to {_POSS} other (?P<what>colors and types|colors and creature types|"
                     rf"types|creature types|card types|colors))?", c, flags=re.I)
    if not m:
        return False
    words = (m["words"] or "").split()
    if not (m["p"] or words):
        return False
    add = bool(m["add"])
    colors_add = add and "colors" in m["what"]
    types, subtypes, colors = set(), set(), set()
    legendary = None
    for w in words:
        lw = w.lower()
        if lw == "legendary":
            legendary = True
        elif lw == "token" or lw == "tokens":
            continue
        elif lw == "snow":
            mods["snow"] = True
        elif lw in _COLOR_CODES:
            colors.add(_COLOR_CODES[lw])
        elif lw == "colorless":
            colors.add("")
        elif lw in _TYPE_WORD:
            types.add(_TYPE_WORD[lw])
        elif w[0].isupper() and w.isalpha():
            subtypes.add(w)
        else:
            return False
    if (colors and add and not colors_add) or ("" in colors and len(colors) > 1):
        return False
    if m["kw"]:
        kws = _keywords(m["kw"])
        if kws is None:
            return False
        mods["keywords"] = mods.get("keywords", frozenset()) | kws
    if m["p"]:
        mods["pt"] = (int(m["p"]), int(m["t"]))
    if legendary:
        mods["legendary"] = True
    if colors:
        colors.discard("")
        mods["colors" if colors_add else "set_colors"] = frozenset(colors)
    if types:
        mods["types" if add else "set_types"] = frozenset(types)
    if subtypes:
        mods["subtypes" if add else "set_subtypes"] = frozenset(subtypes)
    return True


def parse_except(text: str, mods: dict | None = None) -> dict | None:
    """The changes in "..., except it has haste and it's a 1/1 Hero in addition to its other types",
    as a dict, or None if any clause isn't known (the whole copy clause is then left unmatched).

    Copiable changes (rule 707.9): pt, keywords, changeling, types / subtypes / colors (added),
    set_types / set_subtypes / set_colors (replacing), legendary (True/False), snow, keep_name.
    Entry changes, which are not copiable values: counters {kind: n | "x"}. And sac_end."""
    mods = dict(mods or {})
    text = text.strip().rstrip(".")
    if _SAC_QUOTE.search(text + "."):
        mods["sac_end"] = True
        text = _SAC_QUOTE.sub("", text + ".").strip().rstrip(".").strip()
        text = re.sub(r"(?:,? and|,)$", "", text).strip()
    if '"' in text or "." in text:
        return None
    for clause in _CLAUSE_SPLIT.split(text):
        c = clause.strip()
        if not c:
            continue
        if re.fullmatch(rf"(?:{_SUBJ}{_BE}|is|are|isn't|aren't) (?:not )?legendary", c, flags=re.I):
            mods["legendary"] = bool(re.fullmatch(rf"(?:{_SUBJ}(?:'s|'re| is| are)|is|are) legendary", c, flags=re.I))
            continue
        if re.fullmatch(rf"{_SUBJ}(?:'s| is) legendary in addition to {_POSS} other types", c, flags=re.I):
            mods["legendary"] = True
            continue
        if re.fullmatch(rf"{_POSS} name is ~", c, flags=re.I):
            mods["keep_name"] = True
            continue
        m = re.fullmatch(rf"(?:{_SUBJ} )?(?:has|have|gains?) (.+)", c, flags=re.I)
        if m:
            kws = _keywords(m[1])
            if kws is None:
                return None
            if "changeling" in kws:
                mods["changeling"] = True
                kws = kws - {"changeling"}
            if kws:
                mods["keywords"] = mods.get("keywords", frozenset()) | kws
            continue
        m = re.fullmatch(rf"(?:{_SUBJ} )?enters? with (?P<n>an|one|two|three|four|five|X) additional {_COUNTER} "
                         rf"counters? on (?:it|him|her|them)", c, flags=re.I)
        if m:
            n = "x" if m["n"] == "X" else _num(m["n"].lower())
            counters = dict(mods.get("counters", {}))
            counters[m["counter"]] = n
            mods["counters"] = counters
            continue
        if _type_phrase(c, mods):
            continue
        return None
    return mods


def _perm_copy(m, **data):
    from .cards import NO_MATCH, Effect
    mods = {}
    if "COPYHASTE" in m["flags"]:
        mods["keywords"] = frozenset({"haste"})
    if "COPYSACEND" in m["flags"]:
        mods["sac_end"] = True
    if m["exc"]:
        mods = parse_except(m["exc"], mods)
        if mods is None:
            return NO_MATCH
    return Effect("copy_perm", target=data.pop("target", "none"), data={**data, "mods": mods})


def _target_copy(m):
    # The current permanent selector handles noun phrases, not relative clauses.
    # Keep restrictions such as "that entered ... this turn" visible as gaps.
    if re.search(r"\b(?:that|which)\b", m["what"], re.I):
        from .cards import NO_MATCH
        return NO_MATCH
    n = _num(m["n"]) if m["n"] else 1
    scope = (m["scope"] or "").strip()
    return _perm_copy(m, what=m["what"], n=n, other=bool(m["other"]),
                      who="mine" if scope == "you control" else "opp" if scope else "any")


_EXCEPT = r"(?:, except (?P<exc>.+?))?(?P<flags>(?: COPY[A-Z]+)*)"
_MANY = rf"(?:a token that's a copy|(?P<n>{_N[1:-1]}) tokens that are copies)"


def _target_spell_copy(m):
    from .cards import Effect
    times = {"twice": 2, "two times": 2, "three times": 3, "four times": 4, "five times": 5}
    data = {"of": "target", "what": (m["what"] or "").strip(),
            "n": times.get((m["times"] or "").strip().lower(), 1),
            "controller": "mine" if m["mine"] else "opps" if m["opps"] else "any"}
    if m["limit"]:
        data["max_cmc"] = int(m["limit"])
    if m["not_cast"]:
        data["not_cast"] = True
    if m["targets_you"]:
        data["targets_you"] = True
    if m["color"]:
        data["mods"] = {"color_override": frozenset() if m["color"].lower() == "colorless"
                        else frozenset({_COLOR_CODES[m["color"].lower()]})}
    if m["nonlegendary"]:
        data["mods"] = {"legendary": False}
    return Effect("copy_spell", target="spell", data=data)


_SPELL_COPY = (r"copy target (?P<what>instant or sorcery |instant |sorcery |creature |artifact |permanent )?spell"
               r"(?P<mine> you control)?(?P<opps> an opponent controls)?"
               r"(?: with mana value (?P<limit>\d+) or less)?"
               r"(?P<not_cast> that wasn't cast)?(?P<targets_you> that targets you)?"
               r"(?P<times> (?:twice|two times|three times|four times|five times))?"
               r"(?:, except (?:that the copy is (?P<color>white|blue|black|red|green|colorless)|"
               r"(?P<nonlegendary>it isn't legendary if the spell is legendary)))?")

EFFECT_PATTERNS = [
    (rf"create {_MANY} of (?P<other>another )?target (?P<what>[\w ,-]+?)(?P<scope> you control| an opponent "
     rf"controls)?{_EXCEPT}", _target_copy),
    (rf"create {_MANY} of (?:~|this equipment|this artifact|this enchantment){_EXCEPT}",
     lambda m: _perm_copy(m, what="self", n=_num(m["n"]) if m["n"] else 1, target="self")),
    (rf"for each (?P<other>other )?(?P<what>[\w ,-]+?) you control, create a token that's a copy of that "
     rf"(?:creature|permanent|artifact){_EXCEPT}",
     lambda m: _perm_copy(m, what=m["what"], n=1, other=bool(m["other"]), who="mine", each=True)),
    (r"you may choose new targets for the cop(?:y|ies)", lambda m: None),
    (r"(?:you may )?copy (?:that spell|it)( twice)?(?: and you may choose new targets for the copy)?",
     lambda m: _effect("copy_spell", of="that", n=2 if m[1] else 1)),
    (_SPELL_COPY, _target_spell_copy),
    (r"when you (?:next cast an? (?P<a>instant or sorcery|creature) spell|cast your next (?P<b>instant or sorcery) "
     r"spell(?: with mana value (?P<cmc>\d+) or less)?) this turn, copy (?:that spell|it)(?P<twice> twice)?"
     r"(?:, except the copy isn't legendary)?(?: and you may choose new targets for the cop(?:y|ies))?",
     lambda m: _effect("copy_next_spell", what=m["a"] or m["b"], max_cmc=int(m["cmc"] or 99),
                       n=2 if m["twice"] else 1)),
    (r"(?P<may>you may have )?(?:~|it|this creature|this permanent|this land|this artifact|this enchantment) "
     r"becomes? a copy of (?:(?P<tgt>target|another target|another|up to one other target|up to one target) "
     r"(?P<kind>creature|land|permanent|artifact|enchantment|[A-Z][a-z]+)(?P<mine> you control)?|"
     r"(?P<that>that creature))(?P<until> until end of turn)?(?:, except (?P<exc>.+?))?(?P<until2> until end of turn)?",
     lambda m: _become(m)),
    (r"the \"legend rule\" doesn't apply to permanents you control this turn", lambda m: None),
    (r"copy target (?:activated or triggered|triggered|activated) ability you control(?: from an? "
     r"(?P<src>creature|artifact|enchantment|colorless) source)?(?: (?P<x>X) times| (?P<twice>twice))?",
     lambda m: _effect("copy_ability", creature=m["src"] == "creature", source=m["src"] or "",
                       n="x" if m["x"] else 2 if m["twice"] else 1)),
    (r"this ability can't be copied(?: and X can't be 0)?", lambda m: None),
    (r"copy the next spell you cast this turn when you cast it",
     lambda m: _effect("copy_next_spell", what="", max_cmc=99, n=1)),
    (r"copy the next (?P<what>instant or sorcery|instant|sorcery|creature) spell(?: with mana value "
     r"(?P<cmc>\d+) or less)? you cast this turn when you cast it",
     lambda m: _effect("copy_next_spell", what=m["what"], max_cmc=int(m["cmc"] or 99), n=1)),
]


def _become(m):
    """"~ becomes a copy of target creature [until end of turn][, except ...]". Without a duration the copy
    effect lasts indefinitely; "except it has this ability" keeps the ability that made it a copy (707.9a)."""
    from .cards import NO_MATCH, Effect
    exc = m["exc"] or ""
    this = False
    if exc:
        exc, n = re.subn(r"((?:,? and |, )?(?:it|he|she|they) (?:has|have) (?:[a-z ,]+? and )?)this ability$",
                         lambda x: x[1][:-5] if x[1].endswith(" and ") else "", exc)
        this = bool(n)
        exc = re.sub(r"(?:,? and|,)$", "", exc.strip()).strip()
    mods = parse_except(exc) if exc else {}
    if mods is None:
        return NO_MATCH
    if this:
        mods["this_ability"] = True
    kind = m["kind"] or "creature"
    eot = bool(m["until"] or m["until2"])
    other = m["that"] is None and m["tgt"] != "target" and m["tgt"] != "up to one target"
    data = {"what": kind, "who": "mine" if m["mine"] or m["tgt"] == "another" else "any", "other": other,
            "mods": mods, "eot": eot, "may": bool(m["may"]) or "up to one" in (m["tgt"] or "")}
    return Effect("become_copy", target="prev" if m["that"] else "none", data=data)


def _effect(kind, **data):
    from .cards import Effect
    return Effect(kind, data=data)


# Run before sentences are split: fold "It gains haste. Sacrifice it at the beginning of the next end
# step." into the copy sentence before it, and drop ability words in front of "When you next cast".
SUBS = [
    (re.compile(r"(create (?:a token that's a copy|\w+ tokens that are copies) of [^.\"]+?)\.(?: (?:That token|It|"
                r"The token) gains? haste\.)?( Sacrifice (?:it|that token|the token|them) at the beginning of the "
                r"next end step\.)", re.I),
     lambda m: f"{m[1]}{' COPYHASTE' if 'haste' in m[0][len(m[1]):] else ''} COPYSACEND."),
    (re.compile(r"(create (?:a token that's a copy|\w+ tokens that are copies) of [^.\"]+?)\. (?:That token|It) "
                r"gains haste\.", re.I), lambda m: f"{m[1]} COPYHASTE."),
    (re.compile(r"\b[A-Z]\w+ — (?=When you next cast)"), lambda m: ""),
]

_CLONE_KIND = r"(?:creature|artifact|enchantment|land|planeswalker|permanent)"
_CLONE = re.compile(
    r"(?:[A-Z][\w' ]+ — )?You may have ~ enter(?: the battlefield)?(?P<tapped> tapped)? as a copy of "
    rf"(?:any (?P<any>{_CLONE_KIND}(?: or {_CLONE_KIND})?) on the battlefield|"
    rf"an? (?P<ctl>{_CLONE_KIND}(?: or {_CLONE_KIND})?) (?P<who>you control|an opponent controls)|"
    r"(?:any|an?) (?P<gy>creature|land) card in a graveyard)(?:, except (?P<exc>.+?))?\."
    r"(?P<exile> When you do, exile that card\.)?")


_CAST_COPY = re.compile(
    r"(?:[A-Z][\w' ]+ — )?When you cast ~(?P<creature> while you control a creature)?, (?P<another>if you've cast "
    r"another spell this turn, )?(?:you may )?copy (?:it|~)(?P<x> X times)?(?P<life> if you gained life this turn)?\."
    r"(?: You may choose new targets for the cop(?:y|ies)\.)?")


def parse_line(line: str) -> dict | None:
    """CardDef fields for a whole rules line about copies ("You may have ~ enter as a copy of ...",
    "When you cast ~, copy it."), or None."""
    m = _CAST_COPY.fullmatch(line)
    if m:
        cond = "creature" if m["creature"] else "another" if m["another"] else "gained_life" if m["life"] else ""
        return {"cast_copy": {"cond": cond, "n": "x" if m["x"] else 1}}
    m = _CLONE.fullmatch(line)
    if not m:
        return None
    mods = parse_except(m["exc"]) if m["exc"] else {}
    if mods is None:
        return None
    zone = "graveyard" if m["gy"] else "battlefield"
    who = {"you control": "mine", "an opponent controls": "opp"}.get(m["who"] or "", "any")
    kind = m["gy"] or m["any"] or m["ctl"]
    return {"clone": {"zone": zone, "who": who, "what": kind, "mods": mods, "tapped": bool(m["tapped"]),
                      "exile": bool(m["exile"])}}


# ------------------------------------------------------------------ the engine side

def fits(card, what: str, perm=None) -> bool:
    """Whether a card (or permanent) is one of "artifact or creature", "nonland permanent", "Elemental",
    "nontoken creature", "artifact token", "artifact, creature, or land" ..."""
    is_creature = perm.is_creature if perm is not None else card.is_creature
    for alt in re.split(r",? or |, ", what.strip()):
        ok = True
        for w in alt.split():
            lw = w.lower()
            if lw in ("permanent", "nonlegendary"):
                continue
            if lw == "token":
                ok &= card.is_token
            elif lw == "nontoken":
                ok &= not card.is_token
            elif lw == "nonland":
                ok &= not card.is_land
            elif lw == "noncreature":
                ok &= not is_creature
            elif lw == "nonartifact":
                ok &= not card.is_artifact
            elif lw.startswith("non-"):
                ok &= w[4:] not in card.subtypes
            elif lw == "creature":
                ok &= is_creature
            elif lw in _TYPES:
                ok &= _TYPES[lw] in card.types
            elif lw == "basic":
                ok &= card.basic
            elif w[0].isupper():
                ok &= w in card.subtypes or card.changeling
            else:
                ok = False
        if ok:
            return True
    return False


def score(card) -> float:
    return card.cmc + ((card.power or 0) + (card.toughness or 0)) / 2 + 0.5 * len(card.keywords)


def make_copy(card, mods: dict, token: bool = True, name: str | None = None):
    """A CardDef copying card, with the "except" changes."""
    from .cards import Effect, Trigger
    changes = {"is_token": token, "clone": None, "alt_costs": []}
    if name:
        changes["name"] = name
    changes.update(exception_changes(card, mods))
    if mods.get("sac_end"):
        changes["triggers"] = list(card.triggers) + [Trigger("end_step", [Effect("copy_sac", target="self")])]
    return dataclasses.replace(card, **changes)


def exception_changes(card, mods: dict) -> dict:
    """The CardDef fields the copiable "except" changes of mods set on a copy of card (rule 707.9)."""
    changes = {}
    types = mods["set_types"] if mods.get("set_types") else card.types
    if mods.get("pt"):
        changes["power"], changes["toughness"] = mods["pt"]
        types = types | {"Creature"}
    types = types | mods.get("types", frozenset())
    if types != card.types:
        changes["types"] = frozenset(types)
    if mods.get("set_subtypes") is not None:
        changes["subtypes"] = frozenset(mods["set_subtypes"])
    if mods.get("subtypes"):
        changes["subtypes"] = changes.get("subtypes", card.subtypes) | mods["subtypes"]
    if mods.get("set_colors") is not None:
        changes["color_override"] = frozenset(mods["set_colors"])
    elif mods.get("colors"):
        changes["color_override"] = card.colors | mods["colors"]
    if mods.get("keywords"):
        changes["keywords"] = card.keywords | mods["keywords"]
    if mods.get("changeling"):
        changes["changeling"] = True
    if "legendary" in mods:
        changes["legendary"] = mods["legendary"]
    if mods.get("snow"):
        changes["snow"] = True
    return changes


def entry_counters(mods: dict, x: int = 0) -> dict:
    """The counters "except it enters with N additional ... counters on it" puts on the copy as it enters.
    They are not copiable values, so they are not part of the copy's CardDef."""
    return {kind: (x if n == "x" else n) for kind, n in (mods or {}).get("counters", {}).items()
            if (x if n == "x" else n)}


def clone_entry_counters(card, front, x: int, counters: dict | None) -> dict | None:
    """enter_battlefield hook: a clone that entered as a copy (card is not front) gets the counters of its
    "except it enters with N additional ... counters on it" too, before its enter triggers are checked."""
    spec = getattr(front, "clone", None)
    extra = entry_counters(spec["mods"], x) if spec and card is not front else {}
    if not extra:
        return counters
    merged = dict(counters or {})
    for kind, n in extra.items():
        merged[kind] = merged.get(kind, 0) + n
    return merged


def candidates(game, p, eff, source=None) -> list:
    """The permanents eff could copy."""
    d = eff.data
    if eff.target == "self":
        return [source] if source is not None else []
    who = d.get("who", "mine")
    pool = [x for pl in game.players for x in pl.battlefield
            if (who == "any" or (x.controller is p) == (who == "mine")) and game.targetable(x, p)]
    return [x for x in pool if fits(x.card, d.get("what", "permanent"), x)
            and not (d.get("other") and x is source)]


def value(game, me, eff, source=None) -> float:
    """What eff is worth to me now, or -1 when it would do nothing."""
    k, d = eff.kind, eff.data
    if k == "copy_perm":
        cands = candidates(game, me, eff, source)
        if not cands:
            return -1 if eff.target != "self" else 1.0
        n = d.get("n", 1)
        n = 1 if n == "x" else n          # X isn't known before casting
        best = sorted((score(x.card) for x in cands), reverse=True)
        v = sum(best) if d.get("each") else best[0] * max(n, 1)
        return v / 2 if d.get("mods", {}).get("sac_end") else v
    if k == "become_copy":
        if source is None:      # the AI asks without a source: the permanent whose ability this is
            source = next((x for x in me.battlefield for a in list(x.card.activated) + list(x.card.triggers)
                           if any(e is eff for e in a.effects)), None)
        if source is None or eff.target == "prev":
            return -1 if source is None else 1.0
        cands = [x for x in candidates(game, me, eff, source) if x is not source]
        gain = max((score(x.card) for x in cands), default=0) - score(source.card)
        return gain if gain > 0 else -1
    if k == "copy_ability":
        return 2.0 if _abilities(game, me, eff) else -1
    if k == "copy_spell":
        if d.get("of") == "target":
            return max((i.card.cmc for i in spell_targets(game, me, eff)), default=-1)
        return 2.0
    if k == "copy_next_spell":
        return 1.0 if any(_spell_fits(c, d.get("what")) and c.cmc <= d.get("max_cmc", 99)
                          for c in me.hand if not c.is_land) else -1
    return 0.0


def _abilities(game, p, eff, item=None) -> list:
    """The activated or triggered abilities on the stack that eff could copy."""
    return [i for i in game.stack if not i.is_spell and i.controller is p and i is not item
            and not any(e.kind == "copy_ability" for e in i.effects)
            and (not eff.data.get("creature") or (i.source is not None and i.source.is_creature))
            and _source_fits(i.source, eff.data.get("source", ""))]


def _source_fits(src, kind: str) -> bool:
    """"from an artifact / enchantment / colorless source" (Tawnos, Weaver of Harmony, Abstruse Archaic)."""
    if not kind or kind == "creature":
        return True
    if src is None:
        return False
    return not src.card.colors if kind == "colorless" else kind.title() in src.card.types


def revert_next_turn(game, p):
    """advanced_templates.begin_turn: "becomes a copy ... until your next turn" ends as p's turn begins."""
    keep = []
    for who, perm, before, copied in getattr(game, "copy_next_turn", []):
        if who is not p:
            keep.append((who, perm, before, copied))
        elif perm in perm.controller.battlefield and perm.copiable_card is copied:
            perm.card = before
    game.copy_next_turn = keep


def revert(perm):
    """End of turn: a permanent that became a copy is itself again."""
    if getattr(perm, "copy_revert", None) is not None:
        perm.card, perm.copy_revert = perm.copy_revert, None


def _spell_fits(card, what) -> bool:
    if card is None:
        return False
    if what == "instant or sorcery":
        return card.is_instant or card.is_sorcery
    return {"instant": card.is_instant, "sorcery": card.is_sorcery, "creature": card.is_creature,
            "artifact": card.is_artifact, "permanent": card.is_permanent}.get(what or "", True)


def spell_targets(game, p, eff):
    """The spells a targeted copy can legally select, including opposing spells and copies."""
    d = eff.data
    ctrl = d.get("controller")
    return [s for s in game.stack if s.is_spell and _spell_fits(s.card, d.get("what"))
            and (ctrl == "any" or (ctrl == "mine") == (s.controller is p))
            and (not d.get("not_cast") or s.kind == "copy")
            and (not d.get("targets_you") or any(t is p for t in s.targets))
            and ("max_cmc" not in d or s.card.cmc + getattr(s, "x", 0)
                 * (s.card.mana_cost.get("X", 0) if isinstance(s.card.mana_cost, dict) else 0) <= d["max_cmc"])]


def resolve(game, p, eff, target, item=None):
    k, d = eff.kind, eff.data
    source = item.source if item is not None else None
    if k == "copy_sac":
        if target is not None and target in target.controller.battlefield:
            game.log(f"sacrifices {target.card.name} (copy)", target.controller)
            game.sacrifice(target)
    elif k == "copy_perm":
        cands = candidates(game, p, eff, target if eff.target == "self" else source)
        if eff.target == "self" and not cands and source is not None:
            cands = [source]     # last known information: the source has left the battlefield
        if not cands:
            return
        n = d.get("n", 1)
        if n == "x":
            n = getattr(item, "x", 0)
        chosen = cands if d.get("each") else [max(cands, key=lambda x: score(x.card))]
        for perm in chosen:
            for _ in range(n):
                game.enter_battlefield(p, make_copy(perm.copiable_card, d.get("mods", {})),
                                       counters=entry_counters(d.get("mods"), getattr(item, "x", 0)) or None)
            game.log(f"creates {n} token cop{'y' if n == 1 else 'ies'} of {perm.card.name}", p)
    elif k == "become_copy":
        perm = source
        if perm is None or perm not in perm.controller.battlefield:
            return
        if eff.target == "prev":
            # "that creature": its copiable values as it last existed, even after it died or was exiled
            from .engine.state import Permanent
            best = target if isinstance(target, Permanent) and target is not perm else None
        else:
            cands = [x for x in candidates(game, p, eff, perm) if x is not perm]
            best = max(cands, key=lambda x: score(x.card), default=None)
        if best is not None and d.get("may") and score(best.copiable_card) <= score(perm.card):
            best = None               # "you may": keep the better current form
        if best is None:
            return
        mods = d.get("mods", {})
        own = perm.copy_revert if getattr(perm, "copy_revert", None) is not None else perm.copiable_card
        name = getattr(perm.front, "name", own.name) if mods.get("keep_name") else None
        new = make_copy(best.copiable_card, mods, token=own.is_token, name=name)
        if mods.get("this_ability"):
            new = _with_ability(new, perm.copiable_card, eff)
        before = own
        if d.get("until_next_turn"):
            perm.copy_revert = None   # reverts when p's next turn begins (revert_next_turn), not at cleanup
        elif d.get("eot", True):
            if getattr(perm, "copy_revert", None) is None:
                perm.copy_revert = perm.copiable_card
        else:
            perm.copy_revert = None   # a lasting copy effect: nothing to revert to at cleanup
        perm.card = new
        if d.get("until_next_turn"):
            game.copy_next_turn = [e for e in getattr(game, "copy_next_turn", []) if e[1] is not perm]
            game.copy_next_turn.append((p, perm, before, perm.copiable_card))
        game.log(f"{own.name} becomes a copy of {best.card.name}" + (" until end of turn" if d.get("eot", True)
                                                                      else ""), p)
    elif k == "copy_ability":
        from .engine import StackItem
        found = _abilities(game, p, eff, item)
        if not found:
            return
        orig = found[-1]
        n = d.get("n", 1)
        n = getattr(item, "x", 0) if n == "x" else n
        for _ in range(n):
            targets = game.auto_targets(p, orig.effects)
            targets = [t if t is not None else old for t, old in zip(targets, orig.targets)]
            cp = StackItem(p, list(orig.effects), targets, source=orig.source, name=orig.name, context=orig.context,
                           kind=orig.kind)
            cp.x = getattr(orig, "x", 0)
            game.stack.append(cp)
        game.log(f"copies {orig.name} x{n}", p)
    elif k == "copy_spell":
        spell = None
        if d.get("of") == "that":
            from .engine import StackItem
            spell = item.context if item is not None and isinstance(item.context, StackItem) else getattr(item, "target_spell", None)
        else:
            spell = target if any(target is s for s in spell_targets(game, p, eff)) else None
        if spell is not None and spell in game.stack and spell.card is not None:
            for _ in range(d.get("n", 1)):
                copy_spell(game, p, spell, mods=d.get("mods"))
    elif k == "copy_next_spell":
        game.copy_next = [c for c in getattr(game, "copy_next", []) if c[2] == game.turn]
        game.copy_next.append((p, d, game.turn))
        game.log("will copy the next matching spell this turn", p)


def _with_ability(new, old, eff):
    """new plus the triggered or activated ability of old whose effects include eff ("except it has this
    ability"). The ability becomes part of the copiable values (rule 707.9a)."""
    for trig in old.triggers:
        if any(e is eff for e in trig.effects) and not any(t is trig for t in new.triggers):
            return dataclasses.replace(new, triggers=list(new.triggers) + [trig])
    for act in old.activated:
        if any(e is eff for e in act.effects) and not any(a is act for a in new.activated):
            return dataclasses.replace(new, activated=list(new.activated) + [act])
    return new


def copy_spell(game, p, spell, *, mods=None):
    """Put a copy of spell (a StackItem) on the stack under p's control, with new targets where better."""
    from .engine import StackItem
    card = spell.card
    if card.is_permanent:
        face = getattr(card, "cast_face", None) or game._origin(card)[0]
        card = dataclasses.replace(face, is_token=True)
    if mods:
        card = dataclasses.replace(card, **mods)
    # Keep legal spell targets. Retargeting a copied copy spell to the original copy spell itself
    # would otherwise make the default policy create copies forever.
    preset = [t if e.target == "spell" and game.legal_target(p, e, t) else None
              for e, t in zip(spell.effects, spell.targets)]
    targets = game.auto_targets(p, spell.effects, preset=preset)
    targets = [t if t is not None else old for t, old in zip(targets, spell.targets)]
    copy = StackItem(p, list(spell.effects), targets, card=card, name=f"copy of {spell.card.name}", kind="copy")
    copy.x = getattr(spell, "x", 0)
    game.stack.append(copy)
    game.log(f"copies {spell.card.name}" + (f" -> {targets}" if any(targets) else ""), p)
    game.fire(p, "spell_copied", subject=copy.card)     # "whenever you cast or copy ..." (cx_events)
    game.check_ward(copy)


def on_cast(game, p, item):
    """A spell was just cast: "when you cast ~, copy it", and "when you next cast ... this turn, copy it"."""
    counts = getattr(game, "spells_cast", {})
    if counts.get("turn") != game.turn:
        counts = {"turn": game.turn}
    before = counts.get(p.name, 0)
    item.storm_count = sum(counts.get(who.name, 0) for who in game.players)
    counts[p.name] = before + 1
    game.spells_cast = counts
    spec = getattr(item.card, "cast_copy", None)
    if spec:
        cond = spec["cond"]
        if (cond == "creature" and not p.creatures) or (cond == "another" and not before) or \
                (cond == "gained_life" and not p.life_gained_turn):
            pass
        else:
            for _ in range(getattr(item, "x", 0) if spec["n"] == "x" else spec["n"]):
                copy_spell(game, p, item)
    pending = [c for c in getattr(game, "copy_next", []) if c[2] == game.turn]
    keep = []
    for who, d, turn in pending:
        if who is p and _spell_fits(item.card, d.get("what")) and item.card.cmc <= d.get("max_cmc", 99):
            for _ in range(d.get("n", 1)):
                copy_spell(game, p, item)
        else:
            keep.append((who, d, turn))
    game.copy_next = keep


def wants_spell(effects) -> bool:
    """Whether a cast trigger's effects copy "that spell" (so the trigger needs the spell as context)."""
    return any((e.kind == "copy_spell" and e.data.get("of") == "that") or e.cond.startswith("mana") or e.kind == "increment"
               for e in effects)


def clone_on_enter(game, p, card):
    """The card a clone enters as: (card to use, card that goes to the graveyard later)."""
    spec = card.clone
    if not spec:
        return card, card
    if spec["zone"] == "graveyard":
        pool = [(c, pl) for pl in game.players for c in pl.graveyard if fits(c, spec["what"])]
        choice = max(pool, key=lambda t: score(t[0]), default=None)
        if choice is None:
            return card, card
        src, owner = choice
        if spec["exile"]:
            owner.graveyard.remove(src)
            owner.exile.append(src)
        src_card = src
    else:
        mods = spec["mods"]
        legends = {x.card.name for x in p.battlefield if x.card.legendary}
        pool = [x for pl in game.players for x in pl.battlefield
                if (spec["who"] == "any" or (pl is p) == (spec["who"] == "mine")) and fits(x.card, spec["what"], x)
                # a legendary copy of a legend you already control would be lost to the legend rule
                and not (mods.get("legendary", x.copiable_card.legendary) and not mods.get("keep_name")
                         and x.copiable_card.name in legends)]
        best = max(pool, key=lambda x: score(x.card), default=None)
        if best is None:
            return card, card
        src_card = best.copiable_card
    copied = make_copy(src_card, spec["mods"], token=card.is_token,
                       name=card.name if spec["mods"].get("keep_name") else None)
    if spec["tapped"]:
        copied = dataclasses.replace(copied, enters_tapped=True)
    game.log(f"{card.name} enters as a copy of {src_card.name}", p)
    return copied, card
