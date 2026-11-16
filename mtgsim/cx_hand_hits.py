"""Revealed hands (#631):

    Target player reveals their hand and discards all nonland cards.                           (Amnesia)
    Target opponent reveals their hand and discards all multicolored cards.                    (Shatter Assumptions)
    Target player chooses a card in their hand and discards the rest.                          (Monomania)

"Reveals their hand and discards all <X> cards" is the existing ``discard_choice`` kind with ``data["all"]``: every
card in that hand matching <X> (engine/kinds/cards._hand_matches, the same filter words as "you choose a <X> card")
is discarded. Using that kind keeps every AI path (target the opponent, value of hand disruption) as it is. You see
the revealed hand, so using it is allowed (the lead's hidden-information rule).

Not read here: the comma form "reveals their hand, you choose a <X> card from it, then that player discards that card"
behind a condition or "instead" (River's Grasp, Devour Intellect): the condition would not carry over to the split
sentences.
"""
from __future__ import annotations

import re

SUBS: list = []

_FILTER = re.compile(r"(?:(?:non)?(?:land|creature|artifact|enchantment|planeswalker|instant|sorcery)|white|blue|black|"
                     r"red|green|colorless|multicolored|[A-Z][a-z]+)(?: (?:non)?(?:land|creature|artifact|enchantment|"
                     r"planeswalker|instant|sorcery)| (?:white|blue|black|red|green))?")


def _all(m):
    from .cards.model import Effect, NO_MATCH
    desc = m[2]
    if not _FILTER.fullmatch(desc):
        return NO_MATCH
    words = desc.split()
    if words[0][0].isupper() and len(words) == 1:
        desc = words[0]                      # a subtype ("Trap")
    else:
        desc = desc.lower()
    return Effect("discard_choice", target="player", filter=desc,
                  data={"all": True, **({"opp": True} if m[1].lower() == "target opponent" else {})})


def _keep(m):
    from .cards.model import Effect
    return Effect("discard_choice", target="player", data={"all": True, "keep": 1})


EFFECT_PATTERNS = [
    # "Target player chooses a card in their hand and discards the rest." (Monomania): that player keeps its best card
    (r"target player chooses a card in (?:their|his or her) hand and discards the rest", _keep),
    (r"(target player|target opponent) reveals (?:their|his or her) hand and discards all ([\w ]+?) cards", _all),
]
