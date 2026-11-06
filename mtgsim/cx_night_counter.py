"""Counterspell taxes the plain template misses.

* Type filters: "counter target nonartifact spell unless its controller pays {2}", "... creature or planeswalker spell
  ..." (Revolutionary Rebuff, Anticognition, Reject, Assimilate Essence). They reuse the ``types:`` / ``nonartifact``
  filters of Game.can_counter.
* A tax that scales: "unless its controller pays {1} for each card in your graveyard / card in your hand / creature
  you control / artifact you control / blue permanent you control / <Subtype> you control", "{2} for each Wizard on
  the battlefield", "{2} plus an additional {1} for each Faerie you control" and "{X}, where X is its mana value".
  ``data`` carries ``per`` (what is counted), ``mult`` (mana per counted thing) and ``base``; engine/kinds/other.py
  ``counter`` turns them into the amount when the spell resolves, so the count is taken then. A total of zero means
  the controller pays nothing and the spell is not countered."""
from __future__ import annotations

_TYPES = {"creature": "Creature", "planeswalker": "Planeswalker", "battle": "Battle"}

_PER = {"card in your graveyard": "graveyard", "card in your hand": "hand", "creature you control": "creatures",
        "artifact you control": "artifacts", "blue permanent you control": "color:U"}


def _typed_spell(m):
    from .cards.model import Effect
    kind = m[1]
    flt = "nonartifact" if kind == "nonartifact" else "types:" + ",".join(
        _TYPES[t] for t in kind.split(" or "))
    return Effect("counter", int(m[2]), target="spell", filter=flt)


def _scaled(per, mult=1, base=0):
    from .cards.model import Effect
    return Effect("counter", 1, target="spell", data={"per": per, "mult": mult, "base": base})


def _fixed_per(m):
    return _scaled(_PER[m[1].lower()])


def _subtype_mine(m):
    return _scaled("mine:" + m[1].title(), 1)


def _subtype_all(m):
    return _scaled("all:" + m[2].title(), int(m[1]))


def _plus_each(m):
    return _scaled("mine:" + m[2].title(), 1, int(m[1]))


_PAY = r"counter target spell unless its controller pays "
EFFECT_PATTERNS = [
    (r"counter target (nonartifact|creature or planeswalker|creature or battle) spell unless its controller pays \{(\d+)\}",
     _typed_spell),
    (_PAY + r"\{1\} for each (card in your graveyard|card in your hand|creature you control|artifact you control|"
            r"blue permanent you control)", _fixed_per),
    (_PAY + r"\{1\} for each ([a-z]+) you control", _subtype_mine),
    (_PAY + r"\{(\d)\} for each ([a-z]+) on the battlefield", _subtype_all),
    (_PAY + r"\{(\d)\} plus an additional \{1\} for each ([a-z]+) you control", _plus_each),
    (_PAY + r"\{x\}, where x is its mana value", lambda m: _scaled("mv")),
]


def count_per(game, p, per: str, target=None) -> int:
    """How many of the thing a "for each" tax counts, for the counterspell's controller ``p``."""
    if per == "graveyard":
        return len(p.graveyard)
    if per == "hand":
        return len(p.hand)
    if per == "creatures":
        return len(p.creatures)
    if per == "artifacts":
        return sum(1 for x in p.battlefield if x.card.is_artifact)
    if per == "mv":
        return target.card.cmc if target is not None and getattr(target, "card", None) is not None else 0
    if per.startswith("color:"):
        return sum(1 for x in p.battlefield if per[6:] in x.card.colors)
    if per.startswith("mine:"):
        return sum(1 for x in p.battlefield if per[5:] in x.card.subtypes)
    if per.startswith("all:"):
        return sum(1 for pl in game.players for x in pl.battlefield if per[4:] in x.card.subtypes)
    return 0
