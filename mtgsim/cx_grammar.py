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

import dataclasses
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
        return [("cx_color", 0, 0, {"colors": "".join(sorted(cols)), "op": op, "eot": timed, "side": "auto"})]
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
    m = re.fullmatch(r"(.+?) for each (.+?)( until end of turn)?", s, re.I)
    if m and not re.search(r"\bfor each\b", m[2], re.I):
        return _for_each(m[1] + (m[3] or ""), m[2])
    players = parse_players(s)
    if players is not None:
        return players
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
        if target == "player":      # "creatures target player controls": the AI picks the player by side
            data = dict(data, side=_side(inner))
        return [_effect("cx_group", target=target, data=dict(data, group=group, effects=inner))]
    out = []
    for _ in range(copies):
        for i, (k, a, b, d) in enumerate(built):
            if i == 0:
                out.append(_effect(k, a, b, target=target, data=dict(data, **d)))
            else:
                out.append(_effect(k, a, b, target="prev" if target == "permanent" else target, data=d))
    return out


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
    scaled = [e for e in effects for e in ([e] + list(e.data.get("effects", ()))) if e.kind in _SCALED]
    if not scaled:
        return None
    return [dataclasses.replace(e, data=dict(e.data, xq=spec)) for e in effects]


def _count_spec(desc: str):
    """The X-quantity spec for "the number of <desc, made plural>", or None."""
    from .cards.clauses import _xq
    from .cx_events import _IRREGULAR
    plural = {v.lower(): k.lower() for k, v in _IRREGULAR.items()}
    words = desc.split()
    for i, w in enumerate(words):
        low = w.lower()
        many = plural.get(low) or (low[:-1] + "ies" if low.endswith("y") and low[-2:-1] not in "aeiou"
                                   else low + "es" if low.endswith(("s", "x", "ch", "sh")) else low + "s")
        if w[:1].isupper():
            many = many.capitalize()
        spec = _xq("the number of " + " ".join(words[:i] + [many] + words[i + 1:]))
        if spec is None:
            continue
        if spec[0] == "count" and isinstance(spec[1], str):
            # _xq singularises with a plain trailing "s" ("Elves" -> "Elve"): name the thing as written instead.
            head = " ".join(words[:i + 1])
            if re.sub(r"^other ", "", spec[1]) != re.sub(r"^other ", "", head):
                spec = (spec[0], head) + tuple(spec[2:])
        return spec
    return None


# ---------------------------------------------------------------- player subjects

_PLAYERS = {"you": "you", "each player": "each", "each opponent": "opponents", "that player": "that_player",
            "defending player": "defending", "that creature's controller": "controller",
            "that permanent's controller": "controller", "its controller": "controller", "its owner": "owner",
            "that creature's owner": "owner"}
_PLAYER_VERB = r"(?:gain|lose|draw|discard|mill)s?"
_PLAYER_SPLIT = re.compile(rf"(?:,? and |, (?:and )?|,? then )(?={_PLAYER_VERB}\b)", re.I)


def _count(word: str):
    from .cards.model import NUMBERS
    return NUMBERS.get(word.lower()) or (int(word) if word.isdigit() else None)


def _player_verb(text: str):
    """(kind, amount) for one player verb phrase, or None."""
    m = re.fullmatch(r"(gain|lose)s? (\w+) life", text, re.I)
    if m and _count(m[2]):
        return ("gain_life" if m[1].lower() == "gain" else "lose_life", _count(m[2]))
    m = re.fullmatch(r"(draw|discard|mill)s? (a|an|one|two|three|four|five|six|seven|\d+) cards?", text, re.I)
    if m and _count(m[2]) and (m[2].lower() in ("a", "an", "one", "1")) == text.lower().endswith(" card"):
        return (m[1].lower(), _count(m[2]))
    return None


_HELPS = ("pump", "grant", "gain_life", "draw")


def _side(effects) -> str:
    """Whose side a target player should be on: "mine" when the effects only help, else "theirs"."""
    hurt = any(e.kind not in _HELPS or e.data.get("side") == "theirs" for e in effects)
    return "theirs" if hurt else "mine"


def parse_players(s: str):
    """[cx_players effect] for "<player> loses 2 life and draws a card", or None (target players are left to the
    templates: the AI chooses a target player by effect kind)."""
    m = re.fullmatch(rf"({'|'.join(re.escape(k) for k in _PLAYERS)}|target player|target opponent) "
                     rf"({_PLAYER_VERB}\b.*)", s, re.I)
    if m is None:
        return None
    verbs = [_player_verb(v) for v in _PLAYER_SPLIT.split(m[2])]
    if not verbs or None in verbs:
        return None
    inner = [_effect(k, n, target="that_controller") for k, n in verbs]
    who = m[1].lower()
    if who.startswith("target "):
        if len({_side([e]) for e in inner}) > 1:
            return None         # helps and hurts: which player the controller wants isn't clear
        return [_effect("cx_players", target="player", filter="opp" if who.endswith("opponent") else "",
                        data={"who": "target", "side": _side(inner), "effects": inner})]
    return [_effect("cx_players", data={"who": _PLAYERS[who], "effects": inner})]


def players(game, p, who, item, prev, target=None):
    """The players a cx_players subject names as it resolves (a two-player game: the defending player is the
    opponent)."""
    opp = game.opponent(p)
    if who == "target":
        return [target] if target in game.players else []
    if who == "you":
        return [p]
    if who == "each":
        return list(game.players)
    if who in ("opponents", "defending"):
        return [opp]
    if who == "that_player":
        context = item.context if item is not None else None
        return [context] if context in game.players else []
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
    from .cx_events import _obj_match
    spec = _desc(group["cx_desc"], group["plural"])
    viewer = _Viewer(p, source)
    return [x for x in pool if not (group.get("other") and x is source) and _obj_match(game, spec, viewer, x)]


def parse_fallback(s: str, effects: list) -> bool:
    """The _parse_effects hook: append the sentence's effects and return True, or return False."""
    new = parse_sentence(s)
    if not new:
        return False
    effects += new
    return True


# ---------------------------------------------------------------- static grants

_STATIC_KW = {"can't block": "cant_block_now", "can't attack": "cant_attack_now", "can't be blocked": "unblockable",
              "attack each combat if able": "must_attack_now", "attacks each combat if able": "must_attack_now",
              "block each combat if able": "must_block_now", "blocks each combat if able": "must_block_now"}


def _static_verb(text: str):
    """("pt", p, t) / ("kw", keywords) for one static verb phrase, or None."""
    t = text.strip()
    m = re.fullmatch(r"gets? ([+-]\d+)/([+-]\d+)", t, re.I)
    if m:
        return ("pt", int(m[1]), int(m[2]))
    m = re.fullmatch(r"(?:has|have) (.+)", t, re.I)
    if m:
        kws = _keyword_list(m[1])
        return ("kw", tuple(kws)) if kws else None
    low = t.lower()
    if low == "can't attack or block":
        return ("kw", ("cant_attack_now", "cant_block_now"))
    if low in _STATIC_KW:
        return ("kw", (_STATIC_KW[low],))
    return None


def parse_static(line: str, st) -> bool:
    """A static ability granting a group P/T, keywords or a combat restriction, recorded where the engine reads
    anthems (advanced_rules["anthems"]) and static keyword grants. Returns True when the line is consumed."""
    s = line.strip()
    if not s.endswith(".") or re.search(r'[:"]|\b(?:until|this turn|as long as|during|if(?! able)|for each|where|except)\b', s, re.I):
        return False
    s = re.sub(r"^[A-Z][\w' ,-]* — ", "", s[:-1])        # an ability word
    head = re.match(rf"(.+?) ({_VERB}\b.*)", s, re.I)
    if head is None:
        return False
    host = re.fullmatch(r"(equipped|enchanted) creature", head[1], re.I)
    if host:
        return _host_static(host[1].lower(), head[2], st)
    subj = subject(head[1])
    if subj is None or subj[3] is None or subj[0] != "none":
        return False
    group = subj[3]
    spec = group["selector"] if "selector" in group else dict(group, cx_desc=group["cx_desc"])
    parts = [_static_verb(p) for p in _SPLIT.split(head[2])]
    if not parts or None in parts or sum(p[0] == "pt" for p in parts) > 1:
        return False
    kws = tuple(k for p in parts if p[0] == "kw" for k in p[1])
    if _stat_conditioned(spec):
        return False    # "creatures with power 2 or less get +1/+1" would read its own result
    from .cards.model import KEYWORDS
    if _condition_keywords(spec) and any(k in KEYWORDS for k in kws):
        return False    # "creatures with flying have shroud" and a "with shroud ... flying" grant would read each other
    extra = st.extra
    for p in parts:
        if p[0] == "pt":
            extra.setdefault("advanced_rules", {}).setdefault("anthems", []).append((spec, p[1], p[2]))
    if kws:
        extra["static_keyword_grants"] = extra.get("static_keyword_grants", ()) + ((spec, kws),)
    return True


def _host_static(host: str, verbs: str, st) -> bool:
    """"Equipped creature gets -1/+2 and has flying" on an Equipment, "Enchanted creature has defender" on an
    Aura: added to the attachment's bonus and keywords (Permanent._pt_bonus / has read them)."""
    extra = st.extra
    if host == "equipped" and "Equipment" not in st.type_line or host == "enchanted" and not extra.get("aura"):
        return False
    parts = [_static_verb(p) for p in _SPLIT.split(verbs)]
    if not parts or None in parts or sum(p[0] == "pt" for p in parts) > 1:
        return False
    for p in parts:
        if p[0] == "pt":
            bp, bt = extra.get("equip_bonus", (0, 0))
            extra["equip_bonus"] = (bp + p[1], bt + p[2])
        else:
            extra["equip_keywords"] = frozenset(extra.get("equip_keywords", frozenset())) | set(p[1])
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


def desc_matches(game, permanent, spec, controller, source) -> bool:
    """permanent_templates.matches for a selector carrying a cx_desc noun phrase (the static grants above)."""
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
