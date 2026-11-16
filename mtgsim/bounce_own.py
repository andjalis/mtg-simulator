"""Bounce residue (#638): a player returns a permanent they control to its owner's hand, chosen on resolution.

    Return another permanent you control to its owner's hand.        (Ambrosia Whiteheart, Deputy of Acquittals)
    Return an artifact you control to its owner's hand.              (Esperzoa)
    Each player returns a creature they control to its owner's hand. (Curfew)
    Each opponent returns a nonland permanent they control to its owner's hand.

The noun phrase is a battlefield selector (permanent_templates.selector), so any restriction it can't read leaves
the sentence ignored. A creature phrase of the older ``return_own`` template is left to it.
"""
from __future__ import annotations


_WHO = {"each player": "each", "each opponent": "opponents"}


def _build(m):
    from .cards.model import NO_MATCH, Effect
    from .permanent_templates import selector
    who = _WHO[m[1].lower()] if m[1] else "you"
    sel = selector(m[2])
    if not sel or "cx_desc" in sel or sel.get("controller") or sel.get("owner"):
        return NO_MATCH
    return Effect("bounce_choice", 1, data={"selector": dict(sel, controller="mine"), "who": who})


def _source_card(m):
    """"Return this card to its owner's hand": the source's card, from the graveyard it went to (kinds/cx_bounce)."""
    from .cards.model import Effect
    return Effect("source_card_to_hand")


_COLOR = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _with_auras(m):
    """"Return target creature [you control] and all [white] Auras [you control / you own] attached to it to their
    owners' hands" (Hubris, Orzhov Charm, Word of Undoing, Mark of Eviction): the bounce of the creature, plus its
    Auras that fit."""
    import dataclasses
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    effects, bad = _parse_effects(f"Return {m['what']} to its owner's hand.")
    if bad or len(effects) != 1 or effects[0].kind != "bounce":
        return NO_MATCH
    spec = {}
    if m["color"]:
        spec["colors"] = [_COLOR[m["color"].lower()]]
    if m["whose"]:
        spec["controller" if "control" in m["whose"] else "owner"] = "mine"
    return dataclasses.replace(effects[0], data=dict(effects[0].data, with_auras=spec))


def _sub(word: str):
    """"Krakens" -> "kraken", "Octopuses" -> "octopus", "Merfolk" -> "merfolk": a real subtype, or None."""
    from .permanent_templates import _SUBTYPE_TYPES
    low = word.lower()
    for cand in (low, low[:-2] if low.endswith("es") else low, low[:-1] if low.endswith("s") else low,
                 {"wolves": "wolf", "elves": "elf", "dwarves": "dwarf", "fungi": "fungus"}.get(low, low)):
        if cand in _SUBTYPE_TYPES:
            return cand
    return None


def _all_except(m):
    """"Return all creatures to their owners' hands except for Krakens, Leviathans, Octopuses, and Serpents"
    (Whelming Wave), "... all permanents ... except for Giants, Wizards, and lands" (Cyclone Summoner): the mass
    bounce with those subtypes (and lands) left out of its selector."""
    import dataclasses
    import re
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    effects, bad = _parse_effects(f"Return all {m['np']} to their owners' hands.")
    if bad or len(effects) != 1 or "selector" not in effects[0].data:
        return NO_MATCH
    sel = dict(effects[0].data["selector"])
    words = [w for w in re.split(r",\s*(?:and\s+)?|\s+and\s+", m["ex"].strip()) if w]
    subs, lands = [], False
    for w in words:
        if w.lower() == "lands":
            lands = True
            continue
        sub = _sub(w)
        if sub is None or not w[:1].isupper():
            return NO_MATCH
        subs.append(sub)
    if subs:
        sel["not_subtypes"] = sorted(set(sel.get("not_subtypes", [])) | set(subs))
    if lands:
        sel["traits"] = sorted(set(sel.get("traits", [])) | {"nonland"})
    return dataclasses.replace(effects[0], data=dict(effects[0].data, selector=sel))


EFFECT_PATTERNS = [
    (r"return all (?P<np>[\w -]+?) to their owners'? hands? except for (?P<ex>[\w ,-]+)", _all_except),
    (r"return (?P<what>target creature(?: you control)?|enchanted creature) and all (?:(?P<color>white|blue|black|red|"
     r"green) )?Auras (?:(?P<whose>you control|you own) )?attached to (?:it|that creature) to their owners?'s? hands?",
     _with_auras),
    (r"return this card to its owner's hand", _source_card),
    (r"(?:return|(each player|each opponent) returns) ((?:an?|another) [^,.]+?) (?:you|they) control to "
     r"(?:its|their) owners?'s? hands?", _build),
]
