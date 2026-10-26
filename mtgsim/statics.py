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


KINDS = {"pump_matching"}
_SPELL = rf"(All |Other )?((?:[\w-]+ )*?)(?:[Cc]reatures|(?P<sub>[A-Z][a-z]+(?:s|ves)))( you control| your opponents control)?" \
         rf"(?: get ([+-]\d+)/([+-]\d+))?(?:,? and)?(?: gain ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*))? until end of turn"


_NOT_SUBTYPES = {"Its", "Tokens", "Permanents", "Lands", "Artifacts", "Enchantments", "Planeswalkers", "Players", "Opponents"}


def _singular_sub(word: str) -> str:
    """"Elves" -> "Elf", "Zombies" -> "Zombie", "Allies" -> "Ally"."""
    return "Ally" if word == "Allies" else word[:-3] + "f" if word.endswith("ves") else word[:-1]


def _spell(m):
    from .cards import Effect, NO_MATCH
    if not (m[5] or m[7]) or m["sub"] and (m[2] or not m["sub"][0].isupper() or m["sub"] in _NOT_SUBTYPES):
        return NO_MATCH
    noun = f"{_singular_sub(m['sub'])} creatures" if m["sub"] else "creatures"
    pt = f" get {m[5]}/{m[6]}" if m[5] else ""
    entry = _parse(f"{(m[1] or '').capitalize()}{m[2]}{noun}{m[4] or ''}{pt}" + (f" and have {m[7]}." if m[7] else "."))
    return NO_MATCH if entry is None else Effect("pump_matching", data={"static": entry})


def _two_keywords(m):
    from .cards import Effect
    return [Effect("pump", int(m[1]), int(m[2]), target="creature"),
            Effect("grant", target="prev", data={"keyword": m[3]}), Effect("grant", target="prev", data={"keyword": m[4]})]


EFFECT_PATTERNS = [
    (_SPELL, _spell),     # "Blocking creatures get +7/+7 until end of turn", "White creatures you control get +2/+2 ..."
    (rf"target creature gets \+(\d+)/\+(\d+) and gains ({_KW}),? and ({_KW}) until end of turn", _two_keywords),
]


def resolve(game, p, eff, target, item):
    scope, words, pp, tt, kws = eff.data["static"]
    src = item.source if item is not None and item.source is not None else _Caster(p)
    for pl in game.players:
        for c in pl.creatures:
            if _matches(c, src, scope, words):
                c.pump_p += pp
                c.pump_t += tt
                c.temp_kw |= set(kws)


class _Caster:
    """Stands in for a spell's source: "you control" means its caster's creatures."""
    def __init__(self, controller):
        self.controller = controller


_SELF = re.compile(rf"~ (?:gets ([+-]\d+)/([+-]\d+)(?: and has ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*))?|"
                   rf"has ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*)) as long as (.+)\.")
_NOUNS = {"permanent", "creature", "artifact", "enchantment", "land", "planeswalker"}


def parse_line(line: str, st) -> bool:
    if not ({"Instant", "Sorcery"} & set(st.types)) and line:
        line = line.replace("−", "-").replace("Creature tokens you control", "Token creatures you control")
        line = re.sub(r"^Creature tokens get ", "Token creatures get ", line)
        line = re.sub(r"^(Other )?([A-Z][a-z]+) tokens you control", r"\1\2 token creatures you control", line)
        entry = _parse(line)
        if entry is not None:
            st.extra["team_statics"] = st.extra.get("team_statics", ()) + (entry,)
            return True
        entries = _plural_types(line)
        if entries:                                # "Attacking Vampires you control have ...", "Orcs and Goblins ..."
            st.extra["team_statics"] = st.extra.get("team_statics", ()) + entries
            return True
        m = re.fullmatch(rf"Each creature you control with a \+1/\+1 counter on it has ((?:{_KW})(?:(?:, |,? and )(?:{_KW}))*)\.",
                         line)
        if m:                                      # the wording of "Creatures you control with +1/+1 counters on them"
            kws = {k.strip() for k in re.split(r", and |, | and ", m[1])}
            st.extra["counter_team_keywords"] = st.extra.get("counter_team_keywords", frozenset()) | kws
            return True
        tax = _tax(line)
        if tax:
            st.extra["spell_tax"] = st.extra.get("spell_tax", ()) + (tax,)
            return True
        if line == "You may have ~ assign its combat damage as though it weren't blocked.":
            st.extra["assign_unblocked"] = True
            return True
        m = re.fullmatch(r"~ can't (attack or block|attack|block) alone\.", line)
        if m:
            st.extra["not_alone"] = tuple(w for w in ("attack", "block") if w in m[1])
            return True
        desc = unblockable_by(line)
        if desc:
            st.extra["unblockable_by"] = st.extra.get("unblockable_by", ()) + (desc,)
            return True
        m = re.fullmatch(r"(?:(?:Threshold|Delirium|Metalcraft|Hellbent) — )?As long as (.+?), (?:~|it) (gets|has) (.+)\.",
                         line)
        if m:                                      # "As long as ~ is equipped, it gets +1/+1": the other word order
            cond = m[1].replace("~ is ", "it's ").replace("~ has ", "it has ")
            line = f"~ {m[2]} {m[3]} as long as {cond}."
        line = re.sub(r"^(?:Threshold|Delirium|Metalcraft|Hellbent) — (?=~ )", "", line)
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


_SPELL_WORDS = {"creature", "noncreature", "artifact", "nonartifact", "enchantment", "instant", "sorcery", "land",
                "multicolored", "colorless", "legendary", "planeswalker", *_COLORS}


def _tax(line: str):
    """("all" | "theirs" | "mine", alternatives, N) for "Noncreature spells cost {1} more to cast." and the like."""
    m = re.fullmatch(r"(?:([\w ]+?) )?[Ss]pells( your opponents cast| you cast)? cost \{(\d+|[WUBRG])\} more to cast\.", line)
    if not m:
        return None
    alts = tuple(a.strip().lower() for a in re.split(r" and | or |, ", m[1])) if m[1] else ("",)
    if not all(all(w in _SPELL_WORDS for w in a.split()) for a in alts if a):
        return None
    scope = {" your opponents cast": "theirs", " you cast": "mine"}.get(m[2] or "", "all")
    return scope, alts, int(m[3]) if m[3].isdigit() else m[3]       # a colour letter: the Leeches' "{R} more"


def _taxes(game, p, card):
    for pl in game.players:
        for x in pl.battlefield:
            for scope, alts, k in x.card.spell_tax:
                if scope == "theirs" and pl is p or scope == "mine" and pl is not p:
                    continue
                if any(_spell_is(card, a) for a in alts):
                    yield k


def spell_tax(game, p, card) -> int:
    """Generic mana added to card's cost when p casts it, from every permanent's spell taxes."""
    return sum(k for k in _taxes(game, p, card) if isinstance(k, int))


def colored_tax(game, p, card) -> list:
    """The coloured mana symbols added to card's cost ("Red spells you cast cost {R} more to cast.")."""
    return [k for k in _taxes(game, p, card) if isinstance(k, str)]


def _spell_is(card, words: str) -> bool:
    for w in words.split():
        if w in _COLORS and _COLORS[w] not in card.colors or w == "multicolored" and len(card.colors) < 2 or \
                w == "colorless" and card.colors or w == "noncreature" and card.is_creature or \
                w == "nonartifact" and card.is_artifact or w == "legendary" and not card.legendary or \
                w in ("creature", "artifact", "enchantment", "instant", "sorcery", "land", "planeswalker") \
                and w.capitalize() not in card.types:
            return False
    return True


def free_cast_condition(text: str):
    """"an opponent controls a Plains and you control a Mountain" -> "opp:Plains&you:Mountain", or None."""
    parts = []
    for clause in text.split(" and "):
        m = re.fullmatch(r"(an opponent|you) controls? an? (.+)", clause)
        if not m or not _desc_ok(m[2]):
            return None
        parts.append(f"{'opp' if m[1] == 'an opponent' else 'you'}:{m[2]}")
    return "&".join(parts)


def free_cast_allowed(p, opp, cond: str) -> bool:
    for part in cond.split("&"):
        who, desc = part.split(":", 1)
        if not any(desc_matches(x, desc) for x in (opp if who == "opp" else p).battlefield):
            return False
    return True


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
    m = re.fullmatch(r"(?:there are )?(seven|four|five|six|ten) or more cards (?:are )?in your graveyard", text)
    if m:
        return f"gy>={ {'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'ten': 10}[m[1]] }"
    if text == "there are four or more card types among cards in your graveyard":
        return "delirium"
    if text == "you have no cards in hand" or text == "you have one or fewer cards in hand":
        return "hand<=0" if "no" in text else "hand<=1"
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
                                       "nontoken", "token", "artifact", "enchantment", "creature", "snow")
                or re.fullmatch(r"[A-Z][a-z]+", w)):
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
                w in ("artifact", "enchantment", "creature") and w.capitalize() not in card.types or \
                w[:1].isupper() and w not in card.subtypes:
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
    if cond.startswith("gy>="):
        return len(p.graveyard) >= int(cond[4:])
    if cond == "delirium":
        return len({t for c in p.graveyard for t in c.types}) >= 4
    return None


def _plural_types(line: str):
    """Team statics that name creature types in the plural, one entry per type, or None."""
    m = re.fullmatch(r"(Other )?((?:[A-Za-z]+ )*?)([A-Z][a-z]+(?:s|ves))(?: and ([A-Z][a-z]+(?:s|ves)))?( you control| your "
                     r"opponents control)? (get|have) (.+)\.", line)
    if not m or m[3] in _NOT_SUBTYPES or m[4] in _NOT_SUBTYPES:
        return None
    out = ()
    for plural in filter(None, (m[3], m[4])):
        entry = _parse(f"{m[1] or ''}{m[2] or ''}{_singular_sub(plural)} creatures"
                       f"{m[5] or ''} {m[6]} {m[7]}.")
        if entry is None:
            return None
        out += (entry,)
    return out


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
