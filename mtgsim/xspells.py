"""X spells: amounts that are the X paid when the spell is cast ("deals X damage to target creature",
"target creature gets -X/-X until end of turn", "you lose X life", "each opponent loses X life", "counter target
spell unless its controller pays {X}", "draw X cards"). An effect with ``data["x"]`` takes the stack item's X
(Game.cast pays as much X as the remaining mana allows); ``data["x2"]`` sets amount2 to X as well.
"""
from __future__ import annotations

KINDS = {"opp_lose_life"}


def _e(kind, target="none", **data):
    from .cards import Effect
    return Effect(kind, target=target, data={"x": True, **data})


EFFECT_PATTERNS = [
    (r"(?:~|it) deals X damage to target creature", lambda m: _e("damage", "creature")),
    (r"(?:~|it) deals X damage to target (?:creature or planeswalker|creature, planeswalker, or battle)",
     lambda m: _e("damage", "creature_pw")),
    (r"(?:~|it) deals X damage to target player or planeswalker", lambda m: _e("damage", "any")),
    (r"target creature gets -X/-X until end of turn", lambda m: _e("debuff_one", "creature", x2=True)),
    (r"you lose X life", lambda m: _e("lose_life")),
    (r"each opponent loses X life", lambda m: _e("opp_lose_life")),
    (r"each opponent loses X life and you gain X life",
     lambda m: [_e("opp_lose_life"), _e("gain_life")]),
    (r"you gain X life", lambda m: _e("gain_life")),
    (r"draw X cards", lambda m: _e("draw")),
    (r"counter target spell unless its controller pays \{X\}", lambda m: _e("counter", "spell")),
]


def resolve(game, p, eff, target, item):
    if eff.kind == "opp_lose_life":
        game.change_life(game.opponent(p), -eff.amount, f"{item.name if item else 'effect'}: lose life")
        if eff.data.get("gain"):
            game.change_life(p, eff.amount, f"{item.name if item else 'effect'}: gain life")
