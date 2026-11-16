"""#646: keyword lines in older or flavored layouts, rewritten to the lines the parser already reads.

- "Flying; fear", "Trample; rampage 2", "Vigilance; horsemanship": the pre-2005 semicolon form of a keyword list (one
  line, several keywords; CR 702.1 lists keywords the same way with commas). Each keyword becomes its own line, so a
  keyword the engine doesn't know ("banding") stays ignored on its own line while the rest are read.
- "Equip—Pay 3 life.": a non-mana Equip cost, read as the activated ability CR 702.6a defines.
- "Gae Bolg — Equip {4}": a flavor word (CR 207.2d: it has no rules meaning) in front of an Equip ability; the
  ability is read without it.
"""
import re

_KW = r"[a-z]+(?:[ -][a-z]+)?(?: \d+| \{[^}]+\})?"         # "fear", "first strike", "rampage 2", "ward {2}"
_SEMI = re.compile(rf"(?m)^([A-Z]{_KW}(?:; {_KW})+)(?: \([^()]*\))? *$")       # reminder text (or its leftover space) dropped
_EQUIP_COST = re.compile(r"(?m)^Equip—([^.:]+)\.((?: Activate only once each turn\.)?) *$")
_FLAVOR_EQUIP = re.compile(r"(?m)^[A-Z][\w'’]*(?: [A-Za-z][\w'’]*)* — (Equip(?: \{| ?—))")


def split_lines(text: str) -> str:
    text = _SEMI.sub(lambda m: "\n".join(x[0].upper() + x[1:] for x in m[1].split("; ")), text)
    text = _FLAVOR_EQUIP.sub(r"\1", text)
    # CR 702.6a: "Equip [cost]" means "[Cost]: Attach this permanent to target creature you control. Activate only
    # as a sorcery." A non-mana cost ("Equip—Pay 3 life.") is read as that activated ability, so its cost goes
    # through the general ability-cost reader (an unread cost part keeps the line ignored).
    return _EQUIP_COST.sub(_equip_ability, text)


def _equip_ability(m):
    from .cards.parse import _parse_ability_cost
    if _parse_ability_cost(m[1]) is None:
        return m[0]                 # "Equip—Pay {3} or discard a card.": kept as printed, and ignored
    return f"{m[1]}: Attach ~ to target creature you control. Activate only as a sorcery.{m[2]}"


_BASIC = ("Plains", "Island", "Swamp", "Mountain", "Forest")


def typecycling(line: str):
    """CR 702.29e-f: "<Type>cycling {cost}" (search for a card of that subtype), "Artifact landcycling {cost}" (an
    artifact land card), and two landcycling abilities with the same cost on one line ("Islandcycling {2},
    swampcycling {2}": either search, read as one spec with both types). A cycling spec for engine.cycle_spare, or None.
    Different costs, unknown subtypes and un-set words ("Affinitycycling") stay ignored."""
    from .cards.model import parse_mana_cost
    from .permanent_templates import _SUBTYPE_TYPES
    m = re.fullmatch(r"Artifact landcycling (\{[^ ]+\})", line)
    if m:
        return {"cost": parse_mana_cost(m[1]), "land": "artifact"}
    parts = re.findall(r"([A-Za-z]+)cycling (\{[^ ,]+\})", line)
    if not parts or ", ".join(f"{w}cycling {c}" for w, c in parts) != line or len({c for _, c in parts}) != 1:
        return None
    subs = tuple(w.capitalize() for w, _ in parts)
    if len(set(subs)) != len(subs) or not all(s.lower() in _SUBTYPE_TYPES for s in subs):
        return None
    cost = parse_mana_cost(parts[0][1])
    if all(s in _BASIC for s in subs):
        return {"cost": cost, "land": "|".join(subs)}
    if len(subs) == 1 and _SUBTYPE_TYPES[subs[0].lower()] != ["land"]:
        return {"cost": cost, "land": "", "type": subs[0]}
    return None
