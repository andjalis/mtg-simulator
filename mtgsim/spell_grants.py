"""#633 SPELL-KW-GRANT: keywords a permanent gives the spells its controller casts.

    Artifact spells you cast have convoke.                               (Chief Engineer)
    Spells you cast with mana value 6 or greater have cascade.           (Imoti, Celebrant of Bounty)
    Instant and sorcery spells you cast from your hand have cascade.     (Quandrix, the Proof)
    Each instant and sorcery spell you cast has storm.                   (also "Instant and sorcery spells you cast have storm")
    Instant and sorcery spells you control have split second / rebound.  (Samut, Cast Through Time)

Each line adds ``(filter specs, from hand only, mana-value bound, keywords)`` to the permanent's
``advanced_rules["spell_grants"]``. ``apply`` runs inside ``Game.cast`` for every spell: when a permission of a
permanent the caster controls matches, the spell is cast as a copy of its card with those keywords set (convoke,
improvise, delve as payment options; cascade and storm as one more instance each, CR 702.85c / 702.40b; split second
and rebound as keywords). Only keywords the engine reads from the spell are granted; "the first / next spell you
cast" and other riders stay unmatched.
"""
from __future__ import annotations

import dataclasses
import re

_LOWER = {"instant", "sorcery", "artifact", "creature", "enchantment", "planeswalker", "noncreature", "nonartifact",
          "legendary", "colorless", "multicolored", "white", "blue", "black", "red", "green", "permanent"}
_KWS = ("convoke", "improvise", "delve", "cascade", "storm", "split second", "rebound")
_LINE = re.compile(r"(?:Each (?P<d1>[\w ]+?) spell you cast|(?P<d2>[\w ]*?) ?[Ss]pells you (?P<v>cast|control))"
                   r"(?P<hand> from your hand)?(?: with mana value (?P<n>\d+) or (?P<dir>greater|less))? "
                   r"(?:has|have) (?P<k>[\w ,]+?)\.")


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    kws = [k.strip() for k in re.split(r",? and |, ", m["k"])]
    if not kws or any(k not in _KWS for k in kws):
        return False
    if m["v"] == "control" and any(k not in ("split second", "rebound") for k in kws):
        return False            # "spells you control have convoke" means nothing different, but read it only as cast
    from .cx_flash_perm import specs_for
    desc = (m["d1"] or m["d2"] or "").strip()
    if "commander" in desc.lower():
        return False            # commander rules aren't simulated (a parked universe)
    if desc and desc.split()[0].lower() in _LOWER:       # sentence case: "Artifact spells you cast ..."
        desc = desc[0].lower() + desc[1:]
    specs = specs_for(desc)
    if specs is None:
        return False
    bound = (int(m["n"]), m["dir"]) if m["n"] else None
    rules = st.extra.setdefault("advanced_rules", {})
    rules["spell_grants"] = tuple(rules.get("spell_grants", ())) + ((specs, bool(m["hand"]), bound, tuple(kws)),)
    return True


def _granted(game, p, card, from_hand) -> list:
    from .cx_condlib import _card_ok
    out = []
    for x in p.battlefield:
        if x.abilities_suppressed:
            continue
        for specs, hand_only, bound, kws in x.card.advanced_rules.get("spell_grants", ()):
            if hand_only and not from_hand:
                continue
            if bound and (card.cmc < bound[0] if bound[1] == "greater" else card.cmc > bound[0]):
                continue
            if any(_card_ok(card, s) for s in specs):
                out += kws
    return out


def apply(game, p, card, base, kind, log=True):
    """The spell to cast: card itself, or a copy with the granted keywords."""
    if card.is_land or getattr(card, "is_ability", False):
        return card
    kws = _granted(game, p, card, game._zone(p, kind) is p.hand)
    if not kws:
        return card
    names = {f.name for f in dataclasses.fields(card)}
    g = dataclasses.replace(
        card, convoke=card.convoke or "convoke" in kws, improvise=card.improvise or "improvise" in kws,
        delve=card.delve or "delve" in kws,
        cascade=(card.cascade or int("cascade" in card.keywords)) + kws.count("cascade"),
        storm=(card.storm or int("storm" in card.keywords)) + kws.count("storm"),
        keywords=frozenset(card.keywords) | {k for k in kws if k in ("split second", "rebound")})
    for k, v in vars(card).items():
        if k not in names:
            setattr(g, k, v)
    g.origin = (base, kind, getattr(card, "origin", (None, None, None))[2] if getattr(card, "origin", None) else None)
    if log:
        game.log(f"{card.name} has {', '.join(sorted(set(kws)))}", p)
    return g


def view(game, p, card):
    """card as it would be cast now (for payability checks): with its granted payment keywords."""
    if not any("spell_grants" in x.card.advanced_rules for x in p.battlefield):
        return card
    base, kind, _ = game._origin(card)
    return apply(game, p, card, base, kind, log=False)
