"""Token descriptions as a sub-grammar, and the "create" sentences around them.

A token description is cut into its parts: count, "tapped", power/toughness, colours, supertypes,
card types and subtypes, "named <Name>", "with <keywords and "quoted abilities">" and "that's tapped
and attacking". The parts are turned into the token's own card text (a type line plus one rules line
per keyword or quoted ability) and parsed by the ordinary card parser, so any keyword or ability the
engine supports on a card also works on a token (toxic, changeling, crew, "~ can't block.", mana
abilities, characteristic-defining P/T ...). A token whose text the parser ignores or simplifies is
not accepted: the sentence stays unmatched.

    create a 1/1 colorless Phyrexian Mite artifact creature token with toxic 1 and "~ can't block."
    its controller creates a 3/3 green Beast creature token
    each player creates a Food token
    create a number of Food tokens equal to the number of opponents you have
    create a 2/2 black Zombie creature token for each creature card in your graveyard
    create a tapped 0/0 Planet land token named New Planet with "{2}: Add two mana of any one color."

Predefined tokens the engine already models by kind (Treasure, Food, Clue, ...) keep that kind, so
replacement effects that read it (Academy Manufactor, sacrifice costs) see them.
"""
from __future__ import annotations

import dataclasses
import re


_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "twenty": 20}
_COUNT = r"(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|twenty|\d+|x)"
_COLOR_LETTERS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_CARD_TYPES = ("artifact", "creature", "enchantment", "land", "planeswalker", "battle")
_SUPERTYPES = ("legendary", "snow")
# Kinds make_token already builds (with their abilities and the engine's kind checks).
_KINDS = ("treasure", "clue", "blood", "map", "lander", "food", "mutagen", "junk")
# Other predefined tokens, as card text for the card parser.
_PREDEFINED = {
    "gold": ("Artifact — Gold", "Sacrifice this artifact: Add one mana of any color."),
    "powerstone": ("Artifact — Powerstone", "{T}: Add {C}. This mana can't be spent to cast a nonartifact spell."),
    "shard": ("Enchantment — Shard", "{2}, Sacrifice this enchantment: Scry 1, then draw a card."),
}

_SUBJECTS = {
    "": "you", "you": "you", "each opponent": "opp", "each player": "each",
    "its controller": "that_controller", "that creature's controller": "that_controller",
    "that permanent's controller": "that_controller", "that spell's controller": "that_controller",
    "its owner": "owner",
}


def _mask(text: str):
    """text with each quoted ability replaced by \\x00N\\x00, and the list of quoted abilities."""
    quoted = []

    def keep(m):
        quoted.append(m[1])
        return f"\x00{len(quoted) - 1}\x00"
    return re.sub(r'"([^"]*)"', keep, text), quoted


def _unmask(text: str, quoted: list) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: '"' + quoted[int(m[1])] + '"', text)


def _split_list(text: str) -> list:
    return [x.strip() for x in re.split(r",\s*(?:and\s+)?|\s+and\s+", text) if x.strip()]


def _with_lines(text: str, quoted: list):
    """The rules lines of a "with ..." list: keywords ("flying", "toxic 1", "crew 2") and quoted abilities."""
    lines = []
    for item in _split_list(text):
        q = re.fullmatch(r"\x00(\d+)\x00", item)
        if q:
            lines.append(quoted[int(q[1])].strip())
        elif "\x00" in item or not re.fullmatch(r"[a-z][\w\- ]*(?:\{[^}]+\})*", item):
            return None
        else:
            lines.append(item[0].upper() + item[1:])
    return lines


def _tail(rest: str):
    """The parts after "token(s)": name, "with" lines and the tapped/attacking state, or None."""
    name, with_text, state = "", "", ""
    while rest:
        m = re.match(r"\s*named ([A-Z][\w',\- ]*?)(?=\s+with\s|,?\s+that(?:'s| are)\s|$)", rest)
        if m and not name:
            name, rest = m[1], rest[m.end():]
            continue
        m = re.match(r"\s*with (.+?)(?=\s+named [A-Z]|,?\s+that(?:'s| are)\s|$)", rest)
        if m and not with_text:
            with_text, rest = m[1], rest[m.end():]
            continue
        m = re.match(r",?\s*that(?:'s| are) (tapped and attacking|tapped|attacking)$", rest)
        if m and not state:
            state, rest = m[1], ""
            continue
        return None
    return name, with_text, state


def _token_card(name, power, toughness, colors, supertypes, types, subtypes, lines, colorless):
    from .cards.parse import card_from_scryfall
    type_line = " ".join([*(s.title() for s in supertypes), *(t.title() for t in types)])
    if subtypes:
        type_line += " — " + " ".join(subtypes)
    data = {"name": name, "mana_cost": "", "type_line": type_line, "oracle_text": "\n".join(lines)}
    if power is not None:
        data["power"], data["toughness"] = power, toughness
    card = card_from_scryfall(data)
    if card.unsupported or card.approximations:
        return None
    return dataclasses.replace(card, is_token=True, color_override=frozenset(colors) if colors or colorless
                               else frozenset())


def describe(desc: str):
    """One token description (without its count) as {"card": CardDef} or {"kind": ...}, plus "tapped" and
    "attacking"; None when a part isn't understood."""
    masked, quoted = _mask(desc.strip())
    m = re.fullmatch(r"(tapped )?(?:([\dX*]+)/([\dX*]+) )?(.+?) tokens?(.*)", masked, re.I)
    if m is None:
        return None
    tail = _tail(m[5])
    if tail is None:
        return None
    name, with_text, state = tail
    tapped = bool(m[1]) or "tapped" in state
    attacking = "attacking" in state
    words = m[4].split()
    colors, supertypes, types, subtypes, colorless = [], [], [], [], False
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in _COLOR_LETTERS and not (supertypes or types or subtypes):
            colors.append(_COLOR_LETTERS[lw])
        elif lw == "colorless" and not (colors or supertypes or types or subtypes):
            colorless = True
        elif lw == "and" and colors and i + 1 < len(words) and words[i + 1].lower() in _COLOR_LETTERS:
            continue
        elif lw in _SUPERTYPES and not (types or subtypes):
            supertypes.append(lw)
        elif lw in _CARD_TYPES:
            types.append(lw)
        elif re.fullmatch(r"[A-Z][a-z']+(?:-[A-Z][a-z']+)?", w) and not types:
            subtypes.append(w)
        else:
            return None
    lines = _with_lines(with_text, quoted) if with_text else []
    if lines is None:
        return None
    state_out = {"tapped": tapped, "attacking": attacking}
    if not types:                          # a predefined token: "a Treasure token", "a tapped Food token"
        if len(subtypes) != 1 or m[2] or colors or colorless or supertypes or name or lines:
            return None
        kind = subtypes[0].lower()
        if kind in _KINDS:
            return {"kind": kind, **state_out}
        if kind not in _PREDEFINED:
            return None
        type_line, text = _PREDEFINED[kind]
        types, sub = type_line.split(" — ")
        card = _token_card(subtypes[0], None, None, (), (), [types.lower()], [sub], text.split("\n"), True)
        return {"card": card, **state_out} if card is not None else None
    if ("creature" in types) != bool(m[2]) and not (m[2] and "Vehicle" in subtypes):
        return None
    power = toughness = None
    if m[2]:
        if not (m[2].isdigit() and m[3].isdigit()):
            if not (m[2] == m[3] == "*" and lines):          # "*/*" with a defining ability in quotes
                return None
        power, toughness = m[2], m[3]
    if "~" in name:
        return None
    card_name = name or " ".join(subtypes) + " token"
    card = _token_card(card_name, power, toughness, colors, supertypes, types, subtypes, lines, colorless)
    if card is None:
        return None
    return {"card": card, **state_out}


def _quantity(text: str):
    if re.search(r"\b(?:it|its|that creature|that permanent|that card)\b", text, re.I):
        return None                         # the triggering object, which the counts don't read
    from .cx_night_quantity import _quantity as quantity, _PLURAL_ZONES
    return quantity(text) if text.startswith("the number of") or text.startswith("your ") else \
        quantity("the number of " + _PLURAL_ZONES.get(text, text), plural=False)


def _split_descs(masked: str) -> list:
    """Split "a A token, a B token, and a C token" at the boundaries before each new count."""
    return [x for x in re.split(r"(?:,\s*and|,|\s+and)\s+(?=(?:an?|one|two|three|four|five|\d+) "
                                r"(?:tapped |legendary |[\dX*]+/[\dX*]+ |[A-Z]|white|blue|black|red|green|colorless))",
                                masked) if x.strip()]


def parse_create(subject: str, body: str):
    """Effects for "<subject> create(s) <body>", or NO_MATCH."""
    from .cards.model import Effect, NO_MATCH
    who = _SUBJECTS.get(subject.lower().strip())
    if who is None:
        return NO_MATCH
    masked, quoted = _mask(body.strip())
    amount_q, per_each = None, False
    m = re.fullmatch(r"a number of (.+?) equal to (.+)", masked, re.I)
    if m:
        masked, amount_q = "x " + m[1], _quantity(m[2])
        if amount_q is None:
            return NO_MATCH
    m = re.fullmatch(r"(.+?), where x is (.+)", masked, re.I) if amount_q is None else None
    if m:
        masked, amount_q = m[1], _quantity(m[2])
        if amount_q is None:
            return NO_MATCH
    m = re.fullmatch(r"(.+?) for each (.+)", masked, re.I) if amount_q is None else None
    if m and "\x00" not in m[2]:
        masked, amount_q, per_each = m[1], _quantity(m[2]), True
        if amount_q is None:
            return NO_MATCH
    parts = _split_descs(masked)
    effects = []
    for part in parts:
        c = re.fullmatch(rf"({_COUNT}) (.+)", part, re.I)
        if c is None:
            return NO_MATCH
        count = c[1].lower()
        if (count == "x") != (amount_q is not None and not per_each) or (amount_q is not None and len(parts) > 1):
            return NO_MATCH
        if count in ("a", "an") and re.search(r"\btokens\b", c[2]) or \
                count not in ("a", "an", "one") and amount_q is None and not re.search(r"\btokens\b", c[2]):
            return NO_MATCH
        spec = describe(_unmask(c[2], quoted))
        if spec is None:
            return NO_MATCH
        n = 1 if count == "x" else int(count) if count.isdigit() else _NUMBERS[count]
        data = dict(spec, who=who)
        if amount_q is not None:
            data["xq"] = amount_q
        effects.append(Effect("cx_token", n, target={"that_controller": "that_controller", "owner": "prev"}.get(who, "none"),
                              data=data))
    return effects or NO_MATCH


def reparse(sentence: str, effects: list) -> list:
    """Hook for cards/parse.py: a token effect the older templates built with keywords they couldn't read
    ("changeling", "firebending 1") is rebuilt here when the whole sentence parses."""
    if not any(e.data.get("unparsed_token_keywords") for e in effects):
        return effects
    from .cards.model import NO_MATCH
    m = re.fullmatch(_CREATE, sentence.strip().rstrip("."), re.I)
    new = parse_create(m[1] or "", m[2]) if m else NO_MATCH
    return effects if new is NO_MATCH else new


_CREATE = (r"(?:(you|each opponent|each player|its controller|its owner|that creature's controller|"
           r"that permanent's controller|that spell's controller) )?creates? (.+)")

EFFECT_PATTERNS = [
    (_CREATE, lambda m: parse_create(m[1] or "", m[2])),
]


def create(game, who, eff_data: dict, n: int):
    """Put n tokens of the description onto the battlefield under who's control."""
    from .cards.model import Effect
    if n <= 0:
        return
    if "kind" in eff_data:
        game.create_token(who, Effect("token", n, data={"kind": eff_data["kind"], "tapped": eff_data["tapped"],
                                                        "attacking": eff_data["attacking"]}))
        return
    from .backlog_templates import entry_batch
    card = eff_data["card"]
    if eff_data.get("xq_size"):             # "an X/X ... token, where X is ...": resolve put X in power/toughness
        card = dataclasses.replace(card, power=eff_data["power"], toughness=eff_data["toughness"])
    count = n * 2 ** sum(bool(x.card.token_double) for x in who.battlefield if not x.abilities_suppressed)
    attacking = eff_data["attacking"] and game.step in ("declare_attackers", "declare_blockers")
    with entry_batch(game):
        for _ in range(count):
            perm = game.enter_battlefield(who, dataclasses.replace(card), tapped_attacking=attacking)
            if eff_data["tapped"]:
                perm.tapped = True
    game.log(f"creates {count} {card.name}" + ("" if card.name.endswith("token") else " token") + "(s)", who)

