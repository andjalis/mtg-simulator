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
    text = _FROM_LIST.sub(_from_list, text)
    text = _COMMA_LIST.sub(_numbered_list, text)
    text = _MV_TAIL.sub(lambda m: m[1] + "\nP" + m[2][1:], text)
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


# "Protection from blue, from black, and from red" / "Hexproof from artifacts, creatures, and enchantments" (#643):
# one keyword per item, when every item is a keyword the engine knows (else the line is left as printed).
_FROM_LIST = re.compile(r"(?m)^(Protection|Hexproof) from ([A-Za-z-]+(?:, (?:from )?[A-Za-z-]+)*,? and (?:from )?"
                        r"[A-Za-z-]+) *$")
# "Lifelink, protection from mana value 3 or greater": the mana-value protection on a line of its own
_MV_TAIL = re.compile(r"(?m)^([A-Z][a-z]+(?: [a-z]+)*(?:, [A-Za-z][a-z]+(?: [a-z]+)*)*), (protection from (?:mana value "
                      r"\d+ or (?:greater|less)|non-[A-Z][a-z]+)) *$")


def _from_list(m):
    from .cards.model import KEYWORDS
    head = m[1].lower()
    items = [re.sub(r"^(?:and )?(?:from )?", "", x.strip()).lower() for x in re.split(r",? and |, ", m[2])]
    kws = [f"{head} from {x}" for x in items]
    if len(kws) < 2 or not all(k in KEYWORDS for k in kws):
        return m[0]
    return ", ".join(k[0].upper() + k[1:] if i == 0 else k for i, k in enumerate(kws))


# "Flying, protection from spells that are one or more colors, annihilator 6" (#643): a comma keyword list with a
# numbered keyword the engine reads only on a line of its own; split into one line per keyword when every other piece
# is a known keyword (else the line is left as printed).
_NUMBERED = ("renown", "bloodthirst", "fabricate", "vanishing", "fading", "modular", "soulshift", "annihilator",
             "rampage", "backup", "afflict")
_COMMA_LIST = re.compile(r"(?m)^([A-Z][a-z]+(?: [a-z-]+)*(?:, [A-Za-z][a-z-]+(?: [a-z-]+)*(?: \d+)?)+) *$")


def _numbered_list(m):
    from .cards.model import KEYWORDS
    pieces = [x.strip() for x in m[1].split(", ")]
    numbered = [x for x in pieces if re.fullmatch(r"[A-Za-z]+ \d+", x) and x.split()[0].lower() in _NUMBERED]
    if not numbered or not all(x in numbered or x.lower() in KEYWORDS for x in pieces):
        return m[0]
    return "\n".join(x[0].upper() + x[1:] for x in pieces)
