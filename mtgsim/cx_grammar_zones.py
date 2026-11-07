"""Grammar verbs that move permanents between zones: destroy, exile and return to hand, said as an imperative
("Destroy target creature or planeswalker that's red or green.", "Exile up to two target artifacts.", "Return all
nonland permanents to their owners' hands."). The object is read by ``cx_grammar.object_phrase``: one or more
targets, "it" / "that creature", or a group ("all"/"each" <noun phrase>, a list "artifacts, creatures, and lands").

The existing kinds do the work, so the rules stay theirs: ``destroy`` (indestructible, regeneration),
``exile_permanent`` and ``bounce`` (``leave_battlefield``: a card goes to its owner's exile or hand, a token
ceases to exist). See mtgsim/GRAMMAR.md.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, ai_value, count, object_phrase, verb

_KINDS = {"destroy": "destroy", "exile": "exile_permanent", "return": "bounce"}
# Words that turn a zone change into something these kinds don't do: linked exile, a rider, a choice, a
# condition, or a card in another zone.
_REJECT = re.compile(r"\b(?:until|unless|if|instead|card|cards|graveyards?|library|exile|hand|from|then|"
                     r"face (?:up|down)|at the beginning|at end of|this way|and/or|this turn|last turn|chosen|your choice|"
                     r"that player|defending player|its controller|its owner)\b|\bor all\b")


_COLOR = r"(?:white|blue|black|red|green)"
_THATS = re.compile(rf"((?:(?:up to )?\w+ )?(?:other |another )?target |all |each )?([a-z]+(?: or [a-z]+)*) that's "
                    rf"({_COLOR}(?:,? or {_COLOR})*)")


def _object(text: str):
    """object_phrase, also reading "target creature or planeswalker that's red or green" as "target red or green
    creature or planeswalker" (types without other qualifiers only)."""
    m = _THATS.fullmatch(text)
    if m:
        text = f"{m[1] or ''}{m[3]} {m[2]}"
    return object_phrase(text)


def objects(text: str):
    """The Subjects an object phrase names: one; one per item of "target A, target B, and target C"; or one
    group per item of "all A, B, and C". None if any part is not understood."""
    if _REJECT.search(text):
        return None
    obj = _object(text)
    if obj is not None:
        # "it" / "that creature" (target "prev") waits for the back-reference round
        return [obj] if obj.kind == "group" or obj.kind == "permanent" and obj.target != "prev" else None
    items = re.split(r",? and |, ", text)
    if len(items) > 1 and all(i.startswith("target ") for i in items):      # "target creature and target land"
        objs = [_object(i) for i in items]
        ok = all(o is not None and o.kind == "permanent" and o.target == "permanent" and o.copies == 1 for o in objs)
        return objs if ok else None
    m = re.fullmatch(r"(all|each) (.+)", text)
    if m is None:
        return None
    items = re.split(r",? and (?:all )?|, (?:all )?", m[2])
    if len(items) < 2:
        return None
    out = []
    for words in items:
        obj = _object(f"{m[1]} {words}")
        if obj is None or obj.kind != "group":
            return None
        out.append(obj)
    types = [o.group.get("selector", {}).get("types_all") for o in out]
    if all(t and len(t) == 1 and o.group["selector"] == {"types_all": t} for o, t in zip(out, types)):
        # Plain types ("artifacts, creatures, and lands"): one group, every member moved at once.
        out[0].group = {"selector": {"types_any": [t[0] for t in types]}}
        return out[:1]
    return out


def _parts(kind: str, text: str):
    objs = objects(text)
    if objs is None:
        return None
    return [Part(kind, obj=obj) for obj in objs]


@verb(r"(destroy|exile) (.+)", heads=("destroy", "exile"), subjects=("imperative",))
def destroy_exile(m, clause):
    if clause.duration:
        return None
    return _parts(_KINDS[m[1]], m[2])


@verb(r"return (.+?) to (?:its|their) owner(?:'s|s') hands?", heads=("return",), subjects=("imperative",))
def bounce(m, clause):
    if clause.duration:
        return None
    return _parts("bounce", m[1])


_WHERE = {"on top of": "top", "on the bottom of": "bottom"}


@verb(r"put (.+?) (on top of|on the bottom of) (?:its|their) owner(?:'s|s') librar(?:y|ies)", heads=("put",),
      subjects=("imperative",))
def put_library(m, clause):
    """"Put target creature on top of its owner's library", "Put all creatures on the bottom of their owners'
    libraries": cx_tuck. (Several cards on top at once would need an order: only one target or a group of one.)"""
    if clause.duration:
        return None
    parts = _parts("cx_tuck", m[1])
    if parts is None or m[2] == "on top of" and (len(parts) > 1 or parts[0].obj.kind == "group"
                                                  or parts[0].obj.copies > 1):
        return None
    for part in parts:
        part.data = {"where": _WHERE[m[2]], "side": "theirs"}
    return parts


@verb(r"shuffles? (.+?) into (?:its|their) owner(?:'s|s') librar(?:y|ies)", heads=("shuffle",),
      subjects=("imperative",))
def shuffle_library(m, clause):
    if clause.duration:
        return None
    parts = _parts("cx_tuck", m[1])
    for part in parts or ():
        part.data = {"where": "shuffle", "side": "theirs"}
    return parts


@verb(r"sacrifices? (a|an|one|two|three|four|five|\d+) (.+)", heads=("sacrifice", "sacrifices"),
      subjects=("player",))
def sacrifice(m, clause):
    """"Each player sacrifices two lands", "each opponent sacrifices a creature or planeswalker": cx_edict."""
    n = count(m[1])
    noun = m[2]
    if not n or clause.duration or _REJECT.search(noun) or re.search(r"\b(?:you|they|control|controls|other|"
                                                                      r"than|greatest|least|with the)\b", noun):
        return None
    if (n == 1) == bool(re.fullmatch(r".*s", noun)) and not re.fullmatch(r".*(?:ss|elves|dwarves)", noun):
        return None                     # "a creatures" / "two creature": not a phrase we read
    obj = object_phrase(("each " if n == 1 else "all ") + noun)
    if obj is None or obj.kind != "group":
        return None
    return [Part("cx_edict", n, data={"noun": obj.group, "scales": True})]


# ---------------------------------------------------------------- what the default AI thinks these are worth

def _signed(me, perm, v: float) -> float:
    return v if perm.controller is not me else -v


@ai_value("destroy", "exile_permanent", "bounce", "cx_tuck")
def _removal_value(game, me, eff, obj):
    from .engine.policy import perm_value
    from .engine.state import Permanent
    if not isinstance(obj, Permanent):
        return 0.0
    if eff.kind == "destroy" and obj.has("indestructible"):
        return 0.0
    if eff.kind == "bounce" and not obj.card.is_token:
        return _signed(me, obj, 0.5 * obj.card.cmc + 0.5)        # they can cast it again
    return _signed(me, obj, perm_value(obj))


@ai_value("cx_edict")
def _edict_value(game, me, eff, obj):
    """The permanents that player would sacrifice (cx_edict picks the least valuable), signed by who loses them."""
    from .cx_grammar import group_members
    from .engine.policy import perm_value
    from .engine.state import Player
    if not isinstance(obj, Player):
        return 0.0
    pool = group_members(game, obj, {"group": eff.data["noun"]}, None, obj)
    lost = sum(sorted((0.3 if x.card.is_token else perm_value(x)) for x in pool)[:max(1, eff.amount)])
    return lost if obj is not me else -lost


# ---------------------------------------------------------------- cards in graveyards

_CARD_TYPES = ("artifact", "creature", "enchantment", "land", "instant", "sorcery", "planeswalker", "battle",
               "permanent")
_TYPE = "|".join(_CARD_TYPES)
_CARD_NOUN = re.compile(
    rf"(?:({_COLOR}|colorless|multicolored) )?(?:non({_TYPE}) )?(?:((?:{_TYPE})(?:(?:,? or |, )(?:{_TYPE}))*) )?cards?"
    r"(?: with (mana value|power|toughness) (\d+) or (less|greater))?")
_ZONES = {"your graveyard": "you", "a graveyard": "any", "an opponent's graveyard": "opp"}


def card_noun(text: str):
    """A spec for a card noun phrase ("creature card with mana value 3 or less", "instant or sorcery card"), or
    None. Only these words are read: anything else (named, with a keyword, lesser, chosen, ...) rejects."""
    m = _CARD_NOUN.fullmatch(text)
    if m is None:
        return None
    spec = {"types": re.split(r",? or |, ", m[3]) if m[3] else []}
    if m[1]:
        spec["color"] = m[1]
    if m[2]:
        spec["non"] = m[2]
    if m[4]:
        spec["stat"] = [m[4], int(m[5]), m[6]]
    return spec


def card_fits(card, spec) -> bool:
    def is_type(t):
        return card.is_permanent if t == "permanent" else t.title() in card.types
    if spec["types"] and not any(is_type(t) for t in spec["types"]):
        return False
    if spec.get("non") and is_type(spec["non"]):
        return False
    color = spec.get("color")
    if color == "colorless" and card.colors or color == "multicolored" and len(card.colors) < 2:
        return False
    if color in _COLOR_CODES and _COLOR_CODES[color] not in card.colors:
        return False
    if spec.get("stat"):
        stat, n, way = spec["stat"]
        value = card.cmc if stat == "mana value" else (getattr(card, stat, 0) or 0)
        if (value > n) if way == "less" else (value < n):
            return False
    return True


_COLOR_CODES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _card_part(text: str, zone: str, data: dict, side: str):
    """The Part moving the card(s) an object phrase names, with the AI's side: whose graveyard it picks from."""
    obj = _card_object(text, zone)
    if obj is None:
        return None
    obj.data["side"] = "mine" if zone == "your graveyard" else "theirs" if zone == "an opponent's graveyard" else side
    return [Part("cx_card_move", data=data, obj=obj)]


def _card_object(text: str, zone: str):
    """A Subject for "[up to N] [other] target <card noun> from <zone>" (target graveyard_card), or None."""
    from .cx_grammar import Subject
    m = re.fullmatch(r"(?:(up to) )?(?:(a|one|two|three|four|five) )?target (.+)", text)
    if m is None or m[1] and not m[2] or zone not in _ZONES:
        return None
    n = count(m[2]) if m[2] else 1
    spec = card_noun(m[3])
    if spec is None or (n > 1) != m[3].split(" with ")[0].endswith("cards"):
        return None
    data = {"cx_card": spec, "zone": _ZONES[zone]}
    if m[1]:
        data["optional_target"] = True
    if n > 1:
        data["distinct"] = True
    return Subject("permanent", target="graveyard_card", data=data, copies=n, text=text)


_GY = r"(.+?) from (your graveyard|a graveyard|an opponent's graveyard)"


@verb(rf"return {_GY} to (your hand|its owner's hand|their owners' hands|their hand|the battlefield)( tapped)?",
      heads=("return",), subjects=("imperative",))
def return_card(m, clause):
    """"Return target creature card from your graveyard to your hand / to the battlefield [tapped]", "Return target
    card from a graveyard to its owner's hand": cx_card_move. The card goes to its owner's hand; to the battlefield
    only from your own graveyard (under your control)."""
    if clause.duration:
        return None
    dest = m[3]
    if dest == "the battlefield":
        if m[2] != "your graveyard":
            return None
        return _card_part(m[1], m[2], {"to": "battlefield", "tapped": bool(m[4])}, "mine")
    if m[4] or (dest == "your hand") != (m[2] == "your graveyard") or dest == "their hand" and m[2] != \
            "an opponent's graveyard":
        return None
    return _card_part(m[1], m[2], {"to": "hand"}, "mine")


@verb(rf"put {_GY} (onto the battlefield under (?:your|its owner's) control|on top of its owner's library|"
      r"on the bottom of its owner's library|on top of your library|on the bottom of your library)",
      heads=("put",), subjects=("imperative",))
def put_card(m, clause):
    obj = _card_object(m[1], m[2])
    if clause.duration or obj is None or obj.copies > 1 and "on top" in m[3]:
        return None               # several cards on top: the owner orders them
    if "your library" in m[3] and m[2] != "your graveyard":
        return None
    to = ("battlefield" if "battlefield" in m[3] else "library_top" if "top" in m[3] else "library_bottom")
    data = {"to": to}
    if to == "battlefield":
        data["under"] = "you" if "your control" in m[3] else "owner"
    side = {"library_top": "mine", "library_bottom": "theirs"}.get(to, "any" if data.get("under") == "you" else "mine")
    return _card_part(m[1], m[2], data, side)


@verb(rf"exile {_GY}", heads=("exile",), subjects=("imperative",))
def exile_card(m, clause):
    if clause.duration:
        return None
    return _card_part(m[1], m[2], {"to": "exile"}, "theirs")


def grave_cards(game, p, eff):
    """The cards a cx_card graveyard target may be: in the named graveyards, matching the noun phrase."""
    zone = eff.data["zone"]
    owners = [p] if zone == "you" else [game.opponent(p)] if zone == "opp" else list(game.players)
    return [c for o in owners for c in o.graveyard if card_fits(c, eff.data["cx_card"])]
