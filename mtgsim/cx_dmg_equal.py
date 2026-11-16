"""Damage with a computed amount (#626 DMG-EQUAL): "<source> deals damage to <recipient> equal to <quantity>" and
"<source> deals damage equal to <quantity> to <untargeted recipients>".

    When ~ enters, it deals damage to target creature equal to the number of Mountains you control.  (Fire Dragon)
    When ~ enters, it deals damage to any target equal to the number of Elementals you control.     (Omnath)
    When ~ enters, it deals damage to each opponent equal to your devotion to red.                   (Fanatic of Mogis)
    ~ deals damage equal to the number of doom counters on it to each player.                         (Armageddon Clock)
    ~ deals damage equal to the number of time counters on it to each creature and each player.      (Time Bomb)

The quantity is read by the shared ", where X is ..." reader (``cards.clauses._xq`` and its grammar fallback), so only
quantities the engine already counts are accepted, and only ones that don't depend on the recipient: a quantity that
says "they", "that player", "its" and the like names something else (often the recipient) and stays ignored, as do
quantities the plain count would misread ("Wolves and Werewolves"). A targeted recipient goes through the general
damage sentence (``cx_abil_damage``: its target grammar, "it" as the source, and the AI's sizing of the amount); an
untargeted one ("each opponent", "each creature without flying", "each creature and each player") through the effect
grammar with an amount of one, multiplied by the quantity when the effect resolves (``Game.resolve`` and the
grammar's group / player wrappers apply ``data["xq"]``).
"""
from __future__ import annotations

import dataclasses
import re

_SRC = r"(?P<s>~|this creature|it|that creature)"
# words that refer to something the quantity can't name on its own (the recipient, an earlier object, a player)
_REFERS = re.compile(r"\b(?:they|their|them|theirs|that player|that player's|that opponent|its|it|his|her|he|she|"
                     r"that creature|that creature's|the creature's|that permanent|that card|those|this way|"
                     r"excess|difference)\b", re.I)
_DAMAGE_KINDS = {"cx_damage", "damage", "damage_each_player"}


_TYPE_NOUNS = {"creature", "artifact", "enchantment", "permanent", "land", "planeswalker"}


def _noun_ok(word: str) -> bool:
    """A word that names one permanent: a card type, or a subtype ("that Wall's")."""
    from .permanent_templates import _SUBTYPE_TYPES
    return word.lower() in _TYPE_NOUNS or word.lower() in _SUBTYPE_TYPES


def _referent(q: str):
    """("stat", "prev", stat) for "that creature's power" / "the artifact's mana value" / "that Wall's mana value":
    the object the effect before it acted on (or the permanent a trigger fired on), read as it last was, or None."""
    m = re.fullmatch(r"(?:that|the) ([\w-]+)'s (power|toughness|mana value)", q, re.I)
    return ("stat", "prev", m[2].lower()) if m and _noun_ok(m[1]) else None


def _recipient(t: str) -> str:
    """"the creature's controller" / "that Wall's controller" -> "that permanent's controller" (the grammar's
    controller of the object the sentence refers to)."""
    m = re.fullmatch(r"(?:that|the) ([\w-]+)'s controller", t.strip(), re.I)
    return "that permanent's controller" if m and _noun_ok(m[1]) else t


def _spec(q: str, own: bool = False):
    """The quantity spec, or None when it isn't one the engine counts faithfully on its own."""
    from .cards.clauses import _xq
    q = q.strip().rstrip(".")
    m = re.fullmatch(r"~'s (power|toughness|mana value)", q, re.I)
    if m:
        return ("stat", "self", m[1].lower())       # the source's own stat as the damage is dealt
    if _referent(q):
        return _referent(q)
    if own:     # "~ deals damage equal to the number of time counters on it to ...": on the source itself
        q = re.sub(r"\bcounters on it$", "counters on ~", q)
    if re.search(r"\bnamed ~", q):
        return None     # in a granted ability ("Artifacts you control have ...", Food Fight) ~ would read the holder's name
    if _REFERS.search(q.replace("~", "")) or q.lower() == "your life total":
        # "your life total" is card_referent's stand-in for "that card's <stat>" (no real card deals damage equal to
        # it): that module reads those sentences through its own fallback forms, so leave them to it
        return None
    spec = _xq(q)
    if not isinstance(spec, tuple) or not spec or spec[0] in ("this_way", "prev", "spell", "sac", "stat"):
        return None
    if spec[0] == "count":
        # counted by copies.fits, which reads single type / subtype words: "Wolf and Werewolf" would count nothing
        from .copies import _TYPES
        from .permanent_templates import _SUBTYPE_TYPES
        known = {"permanent", "token", "nontoken", "nonland", "noncreature", "nonartifact", "creature", "basic",
                 "other"} | set(_TYPES)
        if not isinstance(spec[1], str) or not all(w.lower() in known or w.lower() in _SUBTYPE_TYPES
                                                   for w in spec[1].split()):
            return None
    return spec


def _targeted(text: str) -> bool:
    return bool(re.search(r"\btarget\b", text, re.I))


def _untargeted(src: str, recipients: str, spec):
    """The grammar's damage effects for "<src> deals 1 damage to <recipients>" with the amount counted, or None."""
    from .cx_grammar import parse_sentence
    from .cards.model import NO_MATCH
    effects = parse_sentence(f"{src} deals 1 damage to {recipients}")
    if not effects:
        return NO_MATCH
    out = []
    for e in effects:
        inner = e.data.get("effects") if e.kind in ("cx_group", "cx_players") else [e]
        if not inner or any(i.kind not in _DAMAGE_KINDS or i.amount != 1 or i.data.get("x") or i.data.get("xq")
                            or i.data.get("xq_each") for i in inner) or e.data.get("xq") or e.data.get("x") \
                or (e.kind not in _DAMAGE_KINDS and e.kind not in ("cx_group", "cx_players")) \
                or e.target not in ("none", "prev") or (e.target == "prev" and e.kind != "damage"):
            return NO_MATCH
        out.append(dataclasses.replace(e, data=dict(e.data, xq=spec)))
    return out


def _build(m, own=False):
    from .cards.model import NO_MATCH
    from .cx_abil_damage import _simple
    kicked = re.fullmatch(r"(twice )?the number of times (?:it|~) was kicked", m["q"].strip().rstrip("."), re.I)
    if kicked:      # multikicker: the kicks paid for the spell, read by Game.resolve's "per_kick"
        if not _targeted(m["t"]):
            return NO_MATCH
        return _single_target(m["s"], m["t"], None, 2 if kicked[1] else 1, {"per_kick": True})
    spec = _spec(m["q"], own)
    if spec is None:
        return NO_MATCH
    if spec[:2] == ("stat", "prev") and _recipient(m["t"]) == m["t"]:
        # "that creature's power" only to that creature's controller: with a target the engine's "prev" would be
        # the damage's own target, and another untargeted recipient leaves "that creature" unclear
        return NO_MATCH
    if _targeted(m["t"]):
        eff = _simple(m) if spec[0] != "stat" else NO_MATCH
        return _single_target(m["s"], m["t"], spec) if eff is NO_MATCH else eff
    return _untargeted(m["s"], _recipient(m["t"]), spec)


def _single_target(src: str, recipient: str, spec, n: int = 1, extra=None):
    """A target the general damage sentence doesn't read ("target player or planeswalker", "target opponent"): the
    template parse of "<src> deals 1 damage to <recipient>", when that is one plain damage effect, with the amount
    counted."""
    from .cards.model import NO_MATCH
    from .cards.parse import _parse_effects
    if src.lower() not in ("~", "it"):
        return NO_MATCH
    effects, ignored = _parse_effects(f"{src} deals {n} damage to {recipient}.")
    if ignored or len(effects) != 1:
        return NO_MATCH
    eff = effects[0]
    if eff.kind != "damage" or eff.amount != n or eff.target not in ("player", "any", "creature", "creature_pw") \
            or any(k in eff.data for k in ("x", "xq", "per", "per_kick", "count", "source_power", "that_much")):
        return NO_MATCH
    return dataclasses.replace(eff, data=dict(eff.data, **(extra or {"xq": spec})))


def _equal_first(m):
    """"... deals damage equal to Q to <recipients>": cx_abil_damage reads it first for the targets it knows."""
    return _build(m, own=m["s"] == "~")


EFFECT_PATTERNS = [
    (rf"{_SRC} deals damage to (?P<t>(?:(?!\bequal to\b).)+?) equal to (?P<q>.+)", _build),
    (rf"{_SRC} deals damage equal to (?P<q>.+?) to (?P<t>.+)", _equal_first),
]
