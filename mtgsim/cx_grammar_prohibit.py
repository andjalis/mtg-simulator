"""Grammar verbs: what players can't cast ("Your opponents can't cast spells this turn.", "You can't cast creature
spells.", "Players can't cast noncreature spells.", "Target player can't cast instant or sorcery spells this
turn."). Prohibitions with a price or a condition ("unless ...") belong to the static lane. See mtgsim/GRAMMAR.md.

The rule is ``cx_cast_ban`` (a spell description), read with cx_grammar.player_rules by ``cast_forbidden``, which
advanced_templates.cast_allowed asks."""
from __future__ import annotations

import re

from .cx_grammar import Part, ai_value, player_rules, verb

_TYPES = {"creature", "artifact", "enchantment", "instant", "sorcery", "planeswalker", "battle", "legendary"}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def spell_spec(text: str):
    """[[word, ...] alternatives] for "creature spells", "instant or sorcery spells", "noncreature spells",
    "red spells", "spells", or None."""
    t = text.strip().lower()
    if not re.fullmatch(r"(?:(.+) )?spells", t):
        return None
    desc = re.fullmatch(r"(?:(.+) )?spells", t)[1] or ""
    if not desc:
        return [[]]
    alts = []
    for alt in re.split(r",? or |, ", desc):
        words = alt.split()
        if not words or not all(w in _TYPES or w in _COLORS or w.startswith("non") and (w[3:] in _TYPES or
                                                                                         w[3:] in _COLORS)
                                for w in words):
            return None
        alts.append(words)
    return alts


def spell_fits(card, spec) -> bool:
    def word(w):
        neg = w.startswith("non") and w not in _TYPES
        base = w[3:] if neg else w
        has = (_COLORS[base] in card.colors) if base in _COLORS else card.legendary if base == "legendary" \
            else base.capitalize() in card.types
        return has != neg
    return any(all(word(w) for w in alt) for alt in spec)


@verb(r"can't cast (.+)", heads=("can't",), subjects=("player",))
def cant_cast(m, clause):
    spec = spell_spec(m[1])
    if spec is None:
        return None
    if clause.duration == "static":
        return [Part("cx_static", data={"rule": "cx_cast_ban", "value": spec})]
    if clause.duration == "turn":
        return [Part("cx_player_rule", data={"rule": "cx_cast_ban", "value": spec})]
    return None


def cast_forbidden(game, player, card) -> bool:
    return any(spell_fits(card, spec) for spec in player_rules(game, player, "cx_cast_ban"))


@ai_value("cx_player_rule")
def rule_value(game, me, eff, obj):
    if eff.data.get("rule") != "cx_cast_ban":
        return 0.0
    worth = 0.4 * sum(spell_fits(c, eff.data["value"]) for c in obj.hand)
    return worth if obj is not me else -worth
