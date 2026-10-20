"""Board and turn-history conditions for "if ..." clauses and "attacks while ..." triggers: counts of what
you control, delirium, "a permanent left the battlefield under your control this turn" (Disappear), "two or
more nonland permanents entered under your control this turn" (Celebration), and the spells cast last turn
(werewolves: "if no spells were cast last turn", "if a player cast two or more spells last turn")."""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_KINDS = "artifact|creature|enchantment|token|land"


def parse(phrase: str) -> str:
    phrase = phrase.strip().lower()
    m = re.fullmatch(rf"you control (a|an|two|three|four|five)(?: or more)? ({_KINDS})s?", phrase)
    if m:
        return f"ctl:{m[2]}>={_N[m[1]]}"
    if phrase == "there are four or more card types among cards in your graveyard":
        return "delirium"
    if phrase == "a permanent left the battlefield under your control this turn":
        return "perm_left"
    m = re.fullmatch(r"(two|three|four) or more nonland permanents entered the battlefield under your control this turn", phrase)
    if m:
        return f"entered_nonland>={_N[m[1]]}"
    if phrase == "no spells were cast last turn":
        return "no_spells_last_turn"
    if phrase == "a player cast two or more spells last turn":
        return "player_spells_last_turn>=2"
    m = re.fullmatch(r"you don't control another ([a-z]+)", phrase)
    if m:
        return f"!ctl_other:{m[1].capitalize()}"
    return ""


def check(game, p, cond: str, item):
    """None means this module does not own the condition."""
    m = re.fullmatch(rf"ctl:({_KINDS})>=(\d+)", cond)
    if m:
        kind, n = m[1], int(m[2])
        have = sum(x.card.is_token if kind == "token" else kind.capitalize() in x.card.types for x in p.battlefield)
        return have >= n
    if cond == "delirium":
        kinds = set()
        for c in p.graveyard:
            kinds |= set(c.types)
        return len(kinds) >= 4
    if cond == "perm_left":
        return p.perm_left_turn
    if cond == "no_spells_last_turn":
        return not any(getattr(game, "last_turn_spells", {}).values())
    if cond == "player_spells_last_turn>=2":
        return max(getattr(game, "last_turn_spells", {}).values(), default=0) >= 2
    m = re.fullmatch(r"entered_nonland>=(\d+)", cond)
    if m:
        return p.entered_nonland_turn >= int(m[1])
    return None
