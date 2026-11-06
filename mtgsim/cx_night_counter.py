"""Counterspell taxes the plain template misses.

* Type filters: "counter target nonartifact spell unless its controller pays {2}", "... creature or planeswalker spell
  ..." (Revolutionary Rebuff, Anticognition, Reject, Assimilate Essence). They reuse the ``types:`` / ``nonartifact``
  filters of Game.can_counter.
* A tax that scales: "unless its controller pays {1} for each card in your graveyard / creature you control / artifact
  you control / card in your hand" (Countervailing Winds, Rakshasa's Disdain, Protect the Negotiators, Override,
  Oppressive Will). ``data["per"]`` names what is counted; engine/kinds/other.py ``counter`` turns it into the amount
  when the spell resolves, so the count is taken then. A count of zero makes it a plain counter."""
from __future__ import annotations

_TYPES = {"creature": "Creature", "planeswalker": "Planeswalker", "battle": "Battle"}


_PER = {"card in your graveyard": "graveyard", "card in your hand": "hand", "creature you control": "creatures",
        "artifact you control": "artifacts"}


def _per(m):
    from .cards.model import Effect
    return Effect("counter", 1, target="spell", data={"per": _PER[m[1]]})


EFFECT_PATTERNS = [
    (r"counter target (nonartifact|creature or planeswalker|creature or battle) spell unless its controller pays \{(\d+)\}",
     lambda m: _typed_spell(m)),
    (r"counter target spell unless its controller pays \{1\} for each (card in your graveyard|card in your hand|"
     r"creature you control|artifact you control)", _per),
]


def _typed_spell(m):
    from .cards.model import Effect
    kind = m[1]
    flt = "nonartifact" if kind == "nonartifact" else "types:" + ",".join(
        _TYPES[t] for t in kind.split(" or "))
    return Effect("counter", int(m[2]), target="spell", filter=flt)


def count_per(game, p, per: str) -> int:
    """How many of the thing a "for each" tax counts, for the counterspell's controller ``p``."""
    if per == "graveyard":
        return len(p.graveyard)
    if per == "hand":
        return len(p.hand)
    if per == "creatures":
        return len(p.creatures)
    if per == "artifacts":
        return sum(1 for x in p.battlefield if x.card.is_artifact)
    return 0
