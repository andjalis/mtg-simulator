"""#646: Morph with a cost that isn't mana (CR 702.37).

    Morph—Reveal a black card in your hand.      {"reveal": "B"}
    Morph—Discard a card.                         {"discard": ""}
    Morph—Discard a Zombie card.                  {"discard": "Zombie"}
    Morph—Pay 5 life.                             {"life": 5}
    Morph—Sacrifice two Mountains.                {"sacrifice": ("Mountain", 2)}

CR 702.37a/e: the card can be cast face down as a 2/2 for {3}, and its controller may turn it face up any time they
have priority by paying the morph cost (a special action). The card gets ``AltCost("morph", {})`` (cast face down as
any morph card), and the cost goes to ``advanced_rules["morph_cost"]``, which Game.turn_face_up pays through ``pay``
here. Revealing has no further effect in the simulation (no player acts on hidden information).

The default AI turns it face up when the cost is cheap for it: a reveal always, life while 10 or more is left,
a discard with a spare card, lands while four or more remain.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_N = {"two": 2, "three": 3}
_BASIC = ("Plains", "Island", "Swamp", "Mountain", "Forest")


def parse(body: str):
    m = re.fullmatch(r"Reveal an? (white|blue|black|red|green) card in your hand", body)
    if m:
        return {"reveal": _COLORS[m[1]]}
    if body == "Discard a card":
        return {"discard": ""}
    m = re.fullmatch(r"Discard an? ([A-Z][a-z]+) card", body)
    if m:
        from .permanent_templates import _SUBTYPE_TYPES
        return {"discard": m[1]} if m[1].lower() in _SUBTYPE_TYPES else None
    m = re.fullmatch(r"Pay (\d+) life", body)
    if m:
        return {"life": int(m[1])}
    m = re.fullmatch(r"Sacrifice (two|three) (Plains|Islands|Swamps|Mountains|Forests)", body)
    if m:
        kind = m[2] if m[2] == "Plains" else m[2][:-1]
        return {"sacrifice": (kind, _N[m[1]])}
    return None


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Morph—(.+)\.", line.strip())
    spec = parse(m[1]) if m else None
    if spec is None:
        return False
    from .cards.model import AltCost
    st.alt_costs.append(AltCost("morph", {"generic": 0}))
    st.extra.setdefault("advanced_rules", {})["morph_cost"] = spec
    return True


def _discard_pool(p, kind):
    return [c for c in p.hand if not kind or kind in c.subtypes or (c.changeling and c.is_creature)]


def payable(game, p, spec) -> bool:
    if "reveal" in spec:
        return any(spec["reveal"] in c.colors for c in p.hand)
    if "discard" in spec:
        return bool(_discard_pool(p, spec["discard"]))
    if "life" in spec:
        return p.life >= spec["life"]
    kind, n = spec["sacrifice"]
    return sum(kind in x.card.subtypes for x in p.battlefield) >= n


def wants(game, p, spec) -> bool:
    """The default AI's choice: is the cost cheap enough to turn the creature face up now?"""
    if "life" in spec:
        return p.life - spec["life"] >= 10
    if "discard" in spec:
        return len(p.hand) >= 2 or not any(c.is_land for c in p.hand) and len(p.hand) >= 1
    if "sacrifice" in spec:
        return sum(x.card.is_land for x in p.battlefield) - spec["sacrifice"][1] >= 4
    return True


def pay(game, p, perm, spec) -> bool:
    """Pay spec to turn perm face up (True), or nothing (False)."""
    from .engine.policy import perm_value
    if not payable(game, p, spec) or not wants(game, p, spec):
        return False
    if "reveal" in spec:
        card = next(c for c in p.hand if spec["reveal"] in c.colors)
        game.log(f"reveals {card.name}", p)
    elif "discard" in spec:
        pool = _discard_pool(p, spec["discard"])
        pick = p.ai.choose_discard(game, p) if not spec["discard"] else min(pool, key=lambda c: c.cmc)
        if pick not in pool:
            pick = min(pool, key=lambda c: c.cmc)
        game.discard_card(p, pick)
        game.log(f"discards {pick.name}", p)
    elif "life" in spec:
        game.change_life(p, -spec["life"], f"{perm.hidden.name}: morph")
    else:
        kind, n = spec["sacrifice"]
        for x in sorted((x for x in p.battlefield if kind in x.card.subtypes), key=lambda x: (not x.tapped,
                                                                                               perm_value(x)))[:n]:
            game.sacrifice(x)
    return True
