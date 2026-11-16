"""A card from a graveyard put on top of or on the bottom of its owner's library (#632):

    You may put a land card from your graveyard on top of your library.                       (Glowspore Shaman)
    Then you may put an instant, sorcery, or battle card from your graveyard on top of your library.
                                                                                              (Halo-Charged Skaab)
    Put target card from an opponent's graveyard on the bottom of their library.              (Landscaper Colos)

Targeted forms already go through cx_grammar_zones.put_card; "their library" after another player's graveyard is
that card's owner's library, so it is rewritten to "its owner's library" (SUBS). The untargeted "a <noun> card from
your graveyard" is a choice made when the effect resolves: kind cx_card_choose (the same as "return a creature card
from your graveyard to your hand") with a library destination; the controller picks the best matching card
(``choose_dig``), which is what they want on top of their library. The bottom-of-library form would need the
card worth least instead and is not read (Ardent Dustspeaker).
"""
from __future__ import annotations

import re

from .cx_grammar import Part, Subject, verb
from .cx_grammar_zones import card_noun

SUBS = [
    # A sentence of its own "Then you may X." is "You may X.": the sentences already resolve in order.
    (re.compile(r"(^|(?<=\. ))Then you may (?=put )"), lambda m: f"{m[1]}You may "),
    (re.compile(r"\b(from (?:an opponent's|target opponent's|target player's) graveyard) (on top of|on the bottom of) "
                r"their library\b", re.I),
     lambda m: f"{m[1]} {m[2]} its owner's library"),
]


@verb(r"put (a|an|one) (.+? card) from your graveyard (on top of) your library",
      heads=("put",), subjects=("imperative", "player"))
def put_choice(m, clause):
    if clause.duration or clause.subject.kind == "player" and clause.subject.who != "you":
        return None
    spec = card_noun(m[2])
    if spec is None:
        return None
    from .cards.model import Effect
    data = {"cx_card": spec, "up_to": False, "to": "library_top", "zone": "you"}
    return [Part("cx_players", obj=Subject("player", who="you"),
                 data={"effects": [Effect("cx_card_choose", 1, data=data)]})]
