"""Static type, colour and base-P/T changes (#406 slice 2): layer 4, 5 and 7b effects from a static ability.

    Enchanted artifact is a creature with base power and toughness 5/5 in addition to its other types.  (Ensoul Artifact)
    Enchanted creature gets -1/-1 and is a black Zombie in addition to its other colors and types.
    Equipped creature gets +1/+1 and is an artifact in addition to its other types.                  (Silverskin Armor)
    Other creatures have base power and toughness 2/2 and are Bears in addition to their other types.
    Enchanted creature is a black Dragon with base power and toughness 4/2 and has flying.
    ~ is also a Cleric, Rogue, Warrior, and Wizard.                                                  (a CDA)
    ~ is all colors.                                                                                 (a CDA)

Parsing: ``parse_line`` (a face_lines hook after cx_type_grants) splits a static line into its subject and verb
phrases, reads every "is / are <description> [in addition to its other (colors and) types]" phrase itself and gives
the other phrases back to the grammar's static parser (cx_grammar.parse_static: pumps, keywords, base P/T through
cx_grammar_chars), so nothing is recorded unless the whole line is read. A phrase becomes a tuple of operations,
recorded as the cx_static rule ``cx_chars`` (``advanced_rules["cx_chars"]`` on ~, ``"cx_chars@host"`` for the
enchanted / equipped permanent, ``"cx_chars@group"`` ((spec, ops), ...) for a group).

    ("set_base", p, t)                  layer 7b (p or t None: only the other is set)
    ("add_types", types)                layer 4, card types added
    ("set_types", types, subtypes)      layer 4, card types and subtypes replaced ("is a Frog creature")
    ("add_subtypes", subs)              layer 4, creature types added
    ("set_subtypes", subs)              layer 4, creature types replaced, other subtypes kept (rule 205.1b)
    ("add_colors", colors) / ("set_colors", colors)     layer 5
    ("set_name", name)                  layer 3 ("... named Legitimate Businessperson")

Engine: ``effects(perm)`` (read by continuous.active) makes one ContinuousEffect per operation that reaches perm,
stamped with its source's timestamp (an Aura's or Equipment's: when it was attached), so the engine's layer order
applies: base P/T under counters and pumps, a later animation over an earlier static. P/T is read live; the type and
colour view is recomputed when a source enters, leaves, changes controller or is attached (cx_type_grants' hooks),
so conditional statics and groups whose membership can change otherwise (counters, tapped, a type the line changes)
are refused for layers 4 and 5.

Refused: "loses all abilities" (a later slice), "is every creature type", land types, conditions and durations,
"the chosen type / color", noncreature groups getting creature types.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_CARD_TYPES = {"artifact": "Artifact", "enchantment": "Enchantment", "creature": "Creature"}
_IRREGULAR = {"elves": "elf", "dwarves": "dwarf", "wolves": "wolf", "fungi": "fungus", "mercenaries": "mercenary"}
_HEADS = r"(?:is|are|has|have|gets?|can't|can|attacks?|blocks?|loses?|it loses)"
_HOST = re.compile(r"(Enchanted|Equipped) (creature|artifact|permanent)\b")
# group membership a layer-4/5 change can't make stale (the view is recomputed only on enter / leave / attach)
_STABLE = {"other", "controller", "types_all", "traits"}


# ---------------------------------------------------------------- the description

def _creature_subtype(word: str, plural: bool):
    from .permanent_templates import _SUBTYPE_TYPES
    low = word.lower()
    if plural:
        low = _IRREGULAR.get(low) or (low[:-1] if low.endswith("s") and not low.endswith("ss") else "")
    if low and "creature" in _SUBTYPE_TYPES.get(low, ()):
        return "-".join(w.capitalize() for w in low.split("-"))
    return None


def description(text: str, plural: bool, addition: str):
    """The operations for "[a|an] [colours] [creature types] [card types] [with base power and toughness N/N]",
    addition "" (sets), "types", "creature types" or "colors and types"; or None."""
    t = text.strip()
    ops, pt = [], None
    named = re.search(r" named ([A-Z][\w'-]*(?: [A-Z][\w'-]*)*)$", t)
    if named:               # "... named Legitimate Businessperson" (#517): the name in the view
        if plural or addition:
            return None
        t = t[:named.start()]
    m = re.search(r" with base power and toughness (\d+)/(\d+)$", t)
    mv = re.search(r" with power and toughness each equal to its mana value$", t)
    if m:
        pt = (int(m[1]), int(m[2]))
        t = t[:m.start()]
    elif mv:                # layer 7b, per permanent: its own mana value (#520)
        pt = ("mv", "mv")
        t = t[:mv.start()]
    if not plural:
        m = re.match(r"an? ", t)
        if not m:
            return None
        t = t[m.end():]
    words = [w.rstrip(",") for w in t.split()]
    if not words:
        return None
    cols, subs, types = [], [], []
    for i, w in enumerate(words):
        low = w.lower()
        if low == "and":
            if not (cols and i + 1 < len(words) and words[i + 1].lower() in _COLORS):
                return None             # "and" only between colours
            continue
        card_type = low[:-1] if plural and low.endswith("s") else low
        if low in _COLORS and not subs and not types:
            cols.append(_COLORS[low])
        elif card_type in _CARD_TYPES and (not plural or low.endswith("s")):
            types.append(_CARD_TYPES[card_type])
        elif _creature_subtype(w, plural) and w[:1].isupper() and not types:
            subs.append(_creature_subtype(w, plural))
        else:
            return None
    if not subs and not types or len(set(types)) != len(types):
        return None
    if subs and types and "Creature" not in types:
        return None                     # "a Golem artifact" is not a creature: creature types need the type
    if addition == "creature types" and (types or cols):
        return None
    if cols:
        if addition == "colors and types":
            ops.append(("add_colors", "".join(sorted(cols))))
        elif addition in ("", "types"):
            ops.append(("set_colors", "".join(sorted(cols))))
        else:
            return None
    elif addition == "colors and types":
        return None
    if addition:
        if types:
            ops.append(("add_types", tuple(types)))
        if subs:
            ops.append(("add_subtypes", tuple(subs)))
    elif types:
        ops.append(("set_types", tuple(types), tuple(subs)))      # "is a Frog creature": rule 205.1a
    else:
        ops.append(("set_subtypes", tuple(subs)))                 # "is a Treefolk": rule 205.1b
    if pt:
        ops.append(("set_base",) + pt)
    if named:
        ops.append(("set_name", named[1]))
    return tuple(ops)


# ---------------------------------------------------------------- parsing

def _subject(line: str, st):
    """(scope, spec, subject text, plural, rest of the line) or None. scope "self", "host" or "group"."""
    host = _HOST.match(line)
    if host:
        if host[1] == "Enchanted" and not st.extra.get("aura") or host[1] == "Equipped" and \
                ("Equipment" not in st.type_line or host[2] != "creature"):
            return None
        return "host", {"host": True, "noun": host[2]}, host[0], False, line[host.end():].strip()
    if line.startswith("~ "):
        return "self", None, "~", False, line[2:]
    m = re.match(rf"(.+?) (?={_HEADS}\b)", line)
    if not m:
        return None
    from .permanent_templates import selector
    each = re.fullmatch(r"(?:Each|All) (.+)", m[1])
    plural = not (each and m[1].startswith("Each"))
    words = each[1] if each else m[1]
    spec = selector(words if plural else re.sub(r"^(\w+)", r"\1s", words), plural=True)
    if spec is None and not plural:         # "Each other non-Aura enchantment": the noun is last (#520)
        spec = selector(re.sub(r"(\w+)((?: you control| an opponent controls)?)$", r"\1s\2", words), plural=True)
    if spec is None:
        return None
    return "group", spec, m[1], plural, line[m.end():]


def _phrases(rest: str):
    return [p.strip() for p in re.split(rf"(?:,? and |, (?:and )?)(?={_HEADS}\b)", rest) if p.strip()]


_ADD = re.compile(r"(?:is|are) (.+?) in addition to (?:its|their) other (colors and types|creature types|types)")
_SET = re.compile(r"(?:is|are) (.+)")


def _host_guard(line: str, st) -> bool:
    """"As long as enchanted permanent is a Vehicle, it's a creature in addition to its other types." (Aerial
    Modification, #517): a host rule guarded by the host's printed subtype, which only changes when the Aura moves
    (and the view is recomputed on attach)."""
    m = re.fullmatch(r"As long as enchanted (permanent|artifact|creature) is an? ([A-Z][\w-]+), it's (.+?) in addition to "
                     r"its other (types|creature types|colors and types)\.", line.strip())
    if not m or not st.extra.get("aura"):
        return False
    from .permanent_templates import _SUBTYPE_TYPES
    if m[2].lower() not in _SUBTYPE_TYPES:
        return False
    ops = description(m[3], False, m[4])
    if ops is None:
        return False
    rules = st.extra.setdefault("advanced_rules", {})
    rules["cx_chars@host"] = tuple(rules.get("cx_chars@host", ())) + ((("if_sub", m[2]),) + tuple(ops),)
    return True


def parse_line(line: str, st, gate: str = "") -> bool:
    """Read the line; with ``gate`` (a cx_static_gate condition code, the "as long as" already removed) the
    operations are recorded as a gated row instead (Starfield of Nyx, #520)."""
    if not gate and _host_guard(line, st):
        return True
    s = line.strip()
    if not s.endswith(".") or '"' in s or re.search(r"\b(?:as long as|during|until|this turn|if|unless|for as long|"
                                                     r"where|for each|chosen|of your choice|except)\b", s, re.I):
        return False
    s = re.sub(r"^[A-Z][\w' ,-]* — ", "", s[:-1])          # an ability word
    m = re.fullmatch(r"~ is also (?:an? )?((?:[A-Z][\w'-]*)(?:,? (?:and )?[A-Z][\w'-]*)*)", s)
    if m:
        return _also(m[1], st)
    if s.strip() == "~ is every creature type" and "Creature" in st.types:
        st.extra["changeling"] = True       # a characteristic-defining ability, like changeling (rule 604.3)
        return True
    if s == "~ is all colors":
        if st.extra.get("color_override") not in (None, frozenset("WUBRG")):
            return False
        st.extra["color_override"] = frozenset("WUBRG")    # a characteristic-defining ability (rule 604.3)
        return True
    subj = _subject(s, st)
    if subj is None:
        return False
    scope, spec, text, plural, rest = subj
    ops, others = [], []
    for phrase in _phrases(rest):
        if re.fullmatch(r"(?:it )?loses? all (?:other )?abilities", phrase):
            ops.append(("lose_all",))       # layer 6 (slice 3): "loses all other abilities" keeps this line's grants
            continue
        if re.fullmatch(r"(?:it )?loses? all other abilities, card types, and creature types", phrase):
            if not any(op[0] == "set_types" for op in ops):
                return False                # the types it keeps must be named first ("is an Insect artifact creature")
            ops.append(("lose_all",))       # Darksteel Mutation (#517): set_types already replaced the types
            continue
        if re.fullmatch(r"(?:has|have) base power and base toughness each equal to (?:its|their) mana value", phrase):
            ops.append(("set_base", "mv", "mv"))     # layer 7b: each permanent's own mana value (#520)
            continue
        if re.fullmatch(r"(?:is|are) every creature type", phrase):
            ops.append(("all_creature_types",))     # layer 4: every creature type (the view's changeling flag)
            continue
        kws = re.fullmatch(r"(loses?|can't have or gain) (.+)", phrase)
        if kws and not kws[2].startswith("all "):
            from .cx_grammar import keyword_list
            found = keyword_list(kws[2])
            if not found:
                return False
            # layer 6: "loses flying" (a later grant wins), "can't have or gain flying" (nothing grants it)
            ops += [("lock_kw" if kws[1].startswith("can't") else "remove_kw", k) for k in found]
            continue
        if not re.match(r"(?:is|are)\b", phrase):
            others.append(phrase)           # the grammar's (gets, has, can't ...)
            continue
        add = _ADD.fullmatch(phrase)
        got = description(add[1], plural, add[2]) if add else \
            description(_SET.fullmatch(phrase)[1], plural, "") if scope != "self" else None
        if got is None:
            return False
        ops += got
    if not ops and scope == "host" and st.extra.get("aura") and \
            re.fullmatch(r"(?:has|have) base power and toughness [01]/\d+", rest):
        from .cx_grammar import parse_static            # "Enchanted creature has base power and toughness 0/2"
        if parse_static(line, st):
            st.extra["gate_hostile"] = True             # a shrinking Aura: auras.finish
            return True
        return False
    if not ops or not _allowed(scope, spec, ops, st):
        return False
    if gate:
        # Only group changes behind a "you control N or more <filter>" count: the views are recomputed on every
        # enter / leave / control change while such a rule is in play, which is exactly when that count changes.
        # A gate that flips otherwise (turn, life, tapped) would leave the type view stale.
        if others or scope != "group" or not gate.startswith("cx:ctrl"):
            return False
        rules = st.extra.setdefault("advanced_rules", {})
        rules["gated"] = tuple(rules.get("gated", ())) + ((gate, scope, dict(spec) if spec else None,
                                                          ("rule", "cx_chars", tuple(ops))),)
        return True
    import copy
    saved = copy.deepcopy(st.extra)
    if others:
        if scope == "host" and spec["noun"] != "creature":
            return False                    # the grammar's host is a creature
        from .cx_grammar import parse_static
        if not parse_static(text + " " + _join(others) + ".", st):
            st.extra.clear()
            st.extra.update(saved)
            return False
    key = {"self": "cx_chars", "host": "cx_chars@host", "group": "cx_chars@group"}[scope]
    rules = st.extra.setdefault("advanced_rules", {})
    rules[key] = tuple(rules.get(key, ())) + ((dict(spec), tuple(ops)) if scope == "group" else tuple(ops),)
    pt = next((op for op in ops if op[0] == "set_base"), None)
    removes = any(op[0] in ("lose_all", "remove_kw", "lock_kw") for op in ops)
    if scope == "host" and st.extra.get("aura") and (removes or pt and (pt[1] or 0) <= 1 and not others):
        st.extra["gate_hostile"] = True     # "Enchanted creature is a Turtle with base power and toughness 0/1"
    return True


def _join(phrases):
    return phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + (", and " if len(phrases) > 2 else " and ") \
        + phrases[-1]


def _allowed(scope, spec, ops, st) -> bool:
    layered = [op for op in ops if op[0] != "set_base"]
    if scope != "group":
        return True
    if not layered:
        return True
    keys = set(spec) - _STABLE
    if keys == {"not_subtypes"} and not any(op[0] in ("add_subtypes", "set_subtypes", "set_types", "all_creature_types")
                                            for op in layered):
        keys = set()        # "non-Aura": no operation here changes subtypes, so membership can't go stale (#520)
    if keys or set(spec.get("traits", ())) - {"token", "nontoken"}:
        return False
    named = {t.lower() for op in layered if op[0] in ("add_types", "set_types") for t in op[1]}
    if named & set(spec.get("types_all", ())) or any(op[0] == "set_types" for op in layered):
        return False                        # it would change its own membership
    subs = any(op[0] in ("add_subtypes", "set_subtypes") for op in layered)
    creature = "creature" in spec.get("types_all", ()) or any("Creature" in op[1] for op in layered
                                                               if op[0] == "add_types")
    return creature or not subs


def _also(words: str, st) -> bool:
    """"~ is also a Cleric, Rogue, Warrior, and Wizard": a characteristic-defining ability (rule 604.3), so the
    types are the card's in every zone."""
    if "Creature" not in st.types:
        return False
    subs = []
    for w in re.split(r",? and |, ", words):
        sub = _creature_subtype(w.strip(), plural=False)
        if sub is None or not w.strip()[:1].isupper():
            return False
        subs.append(sub)
    st.extra["_cda_subtypes"] = tuple(st.extra.get("_cda_subtypes", ())) + tuple(subs)
    return True


# ---------------------------------------------------------------- engine

_BUSY: set = set()


def _stamp(x, attached=False):
    return (getattr(x, "attachment_timestamp", 0) if attached else 0) or getattr(x, "rules_timestamp", 0)


def _rows(perm):
    """(source, timestamp, ops) for every cx_chars rule that reaches perm now."""
    from .permanent_templates import matches
    rules = perm._card.advanced_rules if perm._card.advanced_rules else {}
    if rules.get("cx_chars") and not perm.abilities_suppressed:
        for ops in rules["cx_chars"]:
            yield perm, _stamp(perm), ops
    game = getattr(perm.controller, "_game", None)
    if game is None:
        return
    from .residual_templates import sources
    for x in sources(game, "cx_chars@host"):       # not perm.auras: an Aura's host is set before that list
        if (x.aura_host or x.attached_to) is perm:
            for ops in x.card.advanced_rules["cx_chars@host"]:
                if ops and ops[0][0] == "if_sub":     # "as long as enchanted permanent is a Vehicle" (printed)
                    if ops[0][1] not in perm._card.subtypes:
                        continue
                    ops = ops[1:]
                yield x, _stamp(x, attached=True), ops
    for x in sources(game, "cx_chars@group"):
        for spec, ops in x.card.advanced_rules["cx_chars@group"]:
            if matches(game, perm, spec, x.controller, x):
                yield x, _stamp(x), ops
    from .cx_static_gate import _on, _rows as gated
    for source, code, payload in gated(perm, "rule"):
        if payload[1] == "cx_chars" and _on(source, code, perm):
            yield source, _stamp(source, attached=source is not perm), payload[2]


def effects(perm) -> list:
    """The layer 4 / 5 / 7b ContinuousEffects cx_chars rules give perm now (continuous.active)."""
    game = getattr(perm.controller, "_game", None)
    if game is None or "impending" not in perm.__dict__ or id(perm) in _BUSY:
        return []           # still being constructed, or asked again while reading a group's membership
    from .continuous import ContinuousEffect
    from .permanent_templates import _SUBTYPE_TYPES
    _BUSY.add(id(perm))
    try:
        rows = list(_rows(perm))
    finally:
        _BUSY.discard(id(perm))
    out = []
    printed = perm._card
    for n, (source, stamp, ops) in enumerate(rows):
        creature = printed.is_creature or any(op[0] in ("add_types", "set_types") and "Creature" in op[1]
                                              for op in ops)
        for k, op in enumerate(ops):
            uid = -(id(source) * 64 + 32 + (n * 8 + k) % 32)
            kind = op[0]
            if kind == "set_base":
                p_, t_ = (printed.cmc if v == "mv" else v for v in (op[1], op[2]))      # "equal to its mana value"
                out.append(ContinuousEffect(uid, perm, "set_base", stamp, p_, t_, source=source))
            elif kind == "lose_all":
                out.append(ContinuousEffect(uid, perm, "lose_all", stamp, source=source))
            elif kind in ("remove_kw", "lock_kw"):
                out.append(ContinuousEffect(uid, perm, "remove" if kind == "remove_kw" else "lock", stamp,
                                            keyword=op[1], source=source))
            elif kind == "set_name":
                out.append(ContinuousEffect(uid, perm, "set_name", stamp, source=source, name=op[1]))
            elif kind == "all_creature_types":
                if creature:
                    out.append(ContinuousEffect(uid, perm, "all_creature_types", stamp, source=source))
            elif kind in ("add_types", "set_types"):
                subs = frozenset(op[2]) if kind == "set_types" else None
                out.append(ContinuousEffect(uid, perm, kind, stamp, source=source, types=frozenset(op[1]),
                                            subtypes=subs))
            elif kind in ("add_subtypes", "set_subtypes"):
                if not creature:
                    continue        # creature types on a noncreature: nothing (rule 205.3d)
                subs = frozenset(op[1])
                if kind == "set_subtypes":
                    subs |= {s for s in printed.subtypes
                             if "creature" not in _SUBTYPE_TYPES.get(s.lower(), ("creature",))}
                out.append(ContinuousEffect(uid, perm, kind, stamp, source=source, subtypes=subs))
            else:
                out.append(ContinuousEffect(uid, perm, kind, stamp, source=source, colors=frozenset(op[1])))
    return out


def _gated(rules) -> bool:
    return any(row[3][:2] == ("rule", "cx_chars") for row in rules.get("gated", ()))


def grants(perm) -> bool:
    """Whether perm's card has a cx_chars rule that changes types or colours (its view needs recomputing)."""
    card = getattr(perm, "_card", None)
    rules = card.advanced_rules if card is not None and card.advanced_rules else {}
    return any(rules.get(k) for k in ("cx_chars", "cx_chars@host", "cx_chars@group")) or _gated(rules)


def present(game) -> bool:
    """Whether a group or gated cx_chars rule is in play: then every enter / leave / control change recomputes the
    views (a gate such as "five or more enchantments" only flips on such changes)."""
    from .residual_templates import sources
    if sources(game, "cx_chars@group"):
        return True
    return any(x.card.advanced_rules and _gated(x.card.advanced_rules) for pl in game.players for x in pl.battlefield)


# ---------------------------------------------------------------- "loses all abilities" (layer 6, slice 3)

# What a permanent that loses all its abilities keeps: its characteristics other than abilities (rule 613.1f
# removes abilities in layer 6; name, cost, types, colours and printed P/T stay), and the bookkeeping of the card.
_KEEP = {"name", "mana_cost", "cmc", "types", "subtypes", "power", "toughness", "unsupported", "approximations",
         "oracle", "snow", "back", "adventure", "split_right", "land_face", "token_kind", "is_token", "is_ability",
         "hybrid", "color_override", "basic", "legendary", "aura", "aura_hostile", "loyalty", "defense"}
_BASIC_TYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest"}


def strip(base, subtypes) -> dict:
    """CardDef field values for base without any of its abilities: every ability field back to its default, so
    every reader of ``perm.card`` (triggers, activated abilities, keywords, statics, CDAs) sees none."""
    import dataclasses
    from .cards import CardDef
    out = {}
    for f in dataclasses.fields(CardDef):
        if f.name in _KEEP:
            out[f.name] = getattr(base, f.name)
        elif f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
        else:
            out[f.name] = getattr(base, f.name)
    if set(subtypes) & _BASIC_TYPES:        # a basic land type's mana ability comes with the type (rule 305.6)
        out["produces"] = base.produces
    return out


def granted_after(perm, kw: str, stamp) -> bool:
    """Whether a static grant newer than (or from the same effect as) the "loses all abilities" effect gives perm kw:
    an Equipment or Aura attached at or after it, a group grant whose source arrived later, a later animation."""
    from .permanent_templates import matches
    for x in list(perm.equipment) + list(perm.auras):
        if kw in x.card.equip_keywords and getattr(x, "attachment_timestamp", 0) >= stamp and perm.is_creature:
            return True
    game = getattr(perm.controller, "_game", None)
    if game is not None:
        for pl in game.players:
            for source in pl.battlefield:
                if getattr(source, "rules_timestamp", 0) > stamp and not source.abilities_suppressed and any(
                        kw in kws and matches(game, perm, spec, source.controller, source)
                        for spec, kws in source.card.static_keyword_grants):
                    return True
    anim = perm.animated
    return bool(anim and kw in anim.keywords and getattr(perm, "animation_timestamp", 0) > stamp)


def record_lose_all(extra: dict) -> None:
    """"Enchanted creature loses all abilities" (auras.py's lines): a cx_chars host rule, and a hostile Aura."""
    rules = extra.setdefault("advanced_rules", {})
    rules["cx_chars@host"] = tuple(rules.get("cx_chars@host", ())) + ((("lose_all",),),)
    extra["gate_hostile"] = True
