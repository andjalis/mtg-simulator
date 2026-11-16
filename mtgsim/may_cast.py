"""#839: "you may cast / play" permissions on the cards the sentence before just exiled from the top of a library.

    Exile the top card of your library. You may cast that card this turn.
    Discard your hand, then exile the top three cards of your library. Until end of turn, you may play cards exiled
    this way.
    Exile the top two cards of your library. Until the end of your next turn, you may cast those cards.

These are the impulse permission ``may_play_exiled`` already gives "You may play that card this turn"; "cast" adds
``cast_only``, which leaves out lands (a land card can be played, never cast). The rider only reads right after an
``exile_top`` effect, so the permission always lands on the cards that effect exiled; anywhere else the sentence
stays unmatched. Conditional ("If it's red, you may cast it"), immediate ("You may cast that card. If you don't,
..."), free and mana-type riders are not read here.
"""
from __future__ import annotations

import re

_THEM = r"(?:that card|those cards|it|them|the exiled cards?|cards exiled this way)"
_RX = re.compile(
    rf"(?:you may (?P<v1>cast|play) {_THEM} (?P<d1>this turn|until the end of your next turn)"
    rf"|(?P<d2>until end of turn|until the end of your next turn), you may (?P<v2>cast|play) {_THEM})", re.I)


def parse_rider(sentence: str, effects: list) -> bool:
    from .cards.model import Effect
    if not effects or effects[-1].kind != "exile_top" or effects[-1].target == "that_player":
        return False
    m = _RX.fullmatch(sentence.strip().rstrip("."))
    if not m:
        return False
    verb = (m["v1"] or m["v2"]).lower()
    turns = 2 if "next turn" in (m["d1"] or m["d2"]).lower() else 0
    effects.append(Effect("may_play_exiled", turns, data={"cast_only": True} if verb == "cast" else {}))
    return True
