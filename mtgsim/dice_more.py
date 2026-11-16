"""More die-roll wordings (#634 DICE), on top of dungeon_mechanics' die_roll.

    At the beginning of your upkeep, if ~ is in your graveyard, roll a four-sided die. If the result is 1, return ~
    from your graveyard to the battlefield.                                                   (Arden Angel)
    If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll.
                                                                (Barbarian Class, Pixie Guide, Wyll, Blade of Frontiers)

A four-sided die is a ``die_roll`` with four sides. The advantage replacement is a static (``dice_advantage``, one per
permanent that has it): a player with k of them rolls k more dice and ignores the k lowest (CR 706.6: each
replacement adds one die and ignores the lowest). All dice come from the game's seeded generator. "Roll two and ignore
one of those results" (Krark's Other Thumb) is the roller's choice, not the lowest, and stays unread.
"""
from __future__ import annotations

import re

EFFECT_PATTERNS = [
    (r"(?:you may )?roll a (?:four-sided die|d4)", lambda m: _d4()),
    # "Choose target creature, then roll a d20." (Spiked Pit Trap): the result table's "that creature". Only the
    # marker the SUB below writes: a plain "Choose target creature." belongs to other templates
    (r"DIECHOOSE target creature", lambda m: _choose()),
]

SUBS = [
    (re.compile(r"\bchoose target creature, then roll a d(\d+)\.", re.I),
     lambda m: f"DIECHOOSE target creature. Roll a d{m[1]}."),
]


def _choose():
    from .cards import Effect
    return Effect("die_roll", target="creature", data={"sides": 0})

_ADVANTAGE = "If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll."


def _d4():
    from .cards import Effect
    return Effect("die_roll", data={"sides": 4})


def face_line(st, line):
    if line == _ADVANTAGE or re.fullmatch(r"[A-Z][^—.]* — " + re.escape(_ADVANTAGE), line):   # an ability word too
        rules = st.extra.setdefault("advanced_rules", {})
        rules["dice_advantage"] = rules.get("dice_advantage", 0) + 1
        return None
    return line


def faces(game, p, sides: int, n: int) -> list:
    """n die results for p: with k advantage replacements, n + k dice rolled and the k lowest ignored."""
    k = sum(x.card.advanced_rules.get("dice_advantage", 0) for x in p.battlefield if not x.abilities_suppressed)
    rolled = [game.rng.randint(1, sides) for _ in range(n + k)]
    if k:
        kept = sorted(range(len(rolled)), key=lambda i: rolled[i])[k:]     # drop the k lowest (ties: the first ones)
        game.log(f"rolls {rolled}, ignores the lowest {k}", p)
        rolled = [rolled[i] for i in sorted(kept)]
    return rolled


_HARM = {"damage", "destroy", "exile_permanent", "debuff", "debuff_one", "bounce", "tap", "stun", "fight"}


def choose_marker(game, me, eff):
    """The creature for "Choose target creature, then roll a d20": the opponent's best one when the result table
    harms "that creature", else our own best (both from the table both players can read)."""
    from .engine.state import Permanent
    from .engine.policy import perm_value
    source = getattr(game.target_source, "source", game.target_source)
    card = source.card if isinstance(source, Permanent) else getattr(source, "card", source)
    outcomes = [e for t in getattr(card, "triggers", ()) if t.event.startswith("die:") for e in t.effects
                if e.target == "prev"]
    harmful = any(e.kind in _HARM for e in outcomes)
    opp = game.opponent(me)
    legal = [x for x in game.legal_targets(me, eff) if isinstance(x, Permanent)]
    side = [x for x in legal if (x.controller is opp) == harmful]
    return max(side, key=perm_value, default=None)
