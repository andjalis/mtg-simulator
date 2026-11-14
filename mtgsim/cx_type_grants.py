"""Creature types added by a static ability (layer 4): "... and is a Demon in addition to its other types".

    Enchanted creature gets +2/+2, has flying, and is a Demon in addition to its other types.     (Inner Demon)
    Equipped creature gets +1/+1, has "...," and is a Rogue in addition to its other types.     (Thief's Knife)
    Creature tokens you control are Squirrels in addition to their other creature types.         (Earl of Squirrel)

The type clause is taken out of the line and recorded as ``advanced_rules["type_grants"]`` ((spec, subtypes), ...),
spec ``{"host": True}`` or a creature selector; the rest of the line goes to the static parsers that own it (the
grammar's host bonus / keywords / anthems, quoted trigger grants), and nothing is recorded unless they take all of it.

Engine: ``effects(perm)`` adds one layer-4 ``add_subtypes`` ContinuousEffect per source that applies (on the
battlefield, abilities not suppressed, attached to perm / perm in the group), read by ``continuous.active``. The
characteristic view is recomputed when that can change: a source entering or leaving, an Aura or Equipment being
attached or moved, a permanent changing controller (``refresh_all`` / ``refresh_attach``).

Only creature subtypes on creatures; card types ("is an artifact"), land types, "legendary", "the chosen type" and
groups whose membership depends on a creature type (it could read its own result) stay unsupported.
"""
from __future__ import annotations

import re

_CLAUSE = re.compile(r"(?:,? and |, | and )?(?:is an?|are) ((?:[A-Z][\w'-]*)(?: [A-Z][\w'-]*)*) in addition to "
                     r"(?:its|their) other (?:creature )?types")
_HOST = re.compile(r"(Enchanted|Equipped) creature")
_IRREGULAR = {"Elves": "Elf", "Dwarves": "Dwarf", "Wolves": "Wolf", "Mercenaries": "Mercenary", "Fungi": "Fungus"}


def _subtypes(words: str, plural: bool):
    from .permanent_templates import _CREATURE_SUBTYPES
    out = []
    for w in words.split():
        if plural:
            w = _IRREGULAR.get(w, w[:-1] if w.endswith("s") else w)
        if w.lower() not in _CREATURE_SUBTYPES:
            return None
        out.append(w)
    return tuple(out)


def parse_line(line: str, st) -> bool:
    import copy
    m = _CLAUSE.search(line)
    if not m or line.count(" in addition to ") != 1:
        return False
    host = _HOST.match(line)
    extra = st.extra
    if host:
        if host[1] == "Enchanted" and not extra.get("aura") or host[1] == "Equipped" and "Equipment" not in st.type_line:
            return False
        spec, subj_end = {"host": True}, host.end()
    else:
        each = re.match(r"Each creature ((?:you|your opponents) control) is\b", line)
        g = re.match(r"(.+?) (?:are|get|have)\b", line) if not each else None
        if g is None and each is None:
            return False
        group = "Creatures " + each[1] if each else g[1]     # "Each creature you control is a X" = "Creatures ... are Xs"
        from .permanent_templates import selector
        spec = selector(group, plural=True)
        if spec is None or "creature" not in spec.get("types_all", ()) or spec.get("subtypes") or \
                spec.get("not_subtypes") or "cx_desc" in spec or "keyword" in spec:
            return False                     # creatures only, and no membership that reads creature types
        subj_end = len(group)
    subs = _subtypes(m[1], plural=not host and not each)
    if not subs:
        return False
    rest = re.sub(r"\s+", " ", line[:m.start()] + line[m.end():]).strip()
    if not host and each:
        rest = re.sub(r"^Each creature .+? control( and has | has |\.?$)",
                      lambda r: group + (" have " if "has" in r[1] else ""), rest)
    rest = re.sub(r',"\s*\.?$', '."', rest)            # 'has "... draw a card,"' -> 'has "... draw a card."'
    rest = re.sub(r",\s*$", "", rest.rstrip("."))
    if not rest.endswith('"'):
        rest += "."
    saved = copy.deepcopy(extra)
    if len(rest.rstrip(".").strip()) > subj_end:      # more than the subject: other modifiers to parse
        from .cx_grammar import parse_static
        from .cx_trigger_grants import parse_line as trigger_grant
        if not (parse_static(rest, st) or trigger_grant(rest, st)):
            extra.clear()
            extra.update(saved)
            return False
    record(extra, spec, subs)
    return True


def record(extra: dict, spec: dict, subs) -> None:
    rules = extra.setdefault("advanced_rules", {})
    rules["type_grants"] = tuple(rules.get("type_grants", ())) + ((spec, tuple(subs)),)


def effects(perm) -> list:
    """The layer-4 effects other permanents' static abilities give perm."""
    game = getattr(perm.controller, "_game", None)
    if game is None or "impending" not in perm.__dict__ or not perm._card.is_creature:
        return []           # still being constructed (impending is set last): the enter hook refreshes it
    from .continuous import ContinuousEffect
    from .permanent_templates import matches
    from .residual_templates import sources
    out = []
    for source in sources(game, "type_grants"):
        for i, (spec, subs) in enumerate(source.card.advanced_rules["type_grants"]):
            if spec.get("host"):
                if (source.aura_host or source.attached_to) is not perm:
                    continue
                stamp = getattr(source, "attachment_timestamp", 0) or getattr(source, "rules_timestamp", 0)
            elif matches(game, perm, spec, source.controller, source):
                stamp = getattr(source, "rules_timestamp", 0)
            else:
                continue
            out.append(ContinuousEffect(-(id(source) * 8 + i), perm, "add_subtypes", stamp, source=source,
                                        subtypes=frozenset(subs)))
    return out


def refresh_all(game) -> None:
    from .continuous import refresh
    for pl in game.players:
        for x in list(pl.battlefield):
            refresh(x)


def _grants(perm) -> bool:
    card = getattr(perm, "_card", None)
    return bool(card is not None and card.advanced_rules and card.advanced_rules.get("type_grants"))


def changed(game, perm) -> None:
    """perm entered, left or changed controller: if it grants types, or such grants exist, recompute views."""
    if game is None:
        return
    from .residual_templates import sources
    if _grants(perm) or sources(game, "type_grants"):
        refresh_all(game)


def refresh_attach(source, old, new) -> None:
    """source (an Aura or Equipment) moved from old to new."""
    if old is new or not _grants(source):
        return
    from .continuous import refresh
    for x in (old, new):
        if x is not None and hasattr(x, "_card"):
            refresh(x)
