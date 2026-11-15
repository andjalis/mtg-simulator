"""Copy effects whose object is named by a referent rather than a target (#527).

    Exile a random creature card from that player's library. Create a token that's a copy of that card, ...
    If the discarded card was an artifact card, exile it from your graveyard. If you do, create a token
    that's a copy of it, ...

The exile sentences resolve as cx_card_move with data["zone"] == "library" (a random card of the
trigger's damaged player's library) or data["discard_ref"] (the card this ability just discarded);
both record the moved physical card on the stack item (item.exiled_card), which a following
"create a token that's a copy of that card / it" (cx_token with data ref "card") then copies.
The "if you do" wrapper is enforced by the same referent: it is set only when the exile happened,
and cards/parse.py only accepts the copy sentence right after the discard-referent exile.

Joined to the templates in mtgsim.cards; the moves themselves are handled by cx_card_move in
engine/kinds/cx_grammar_zones.py.
"""
from __future__ import annotations

import re


def _lib_exile(m):
    """"Exile a random <card noun> from that player's library": the trigger's damaged player's library."""
    from .cards import Effect, NO_MATCH
    from .cx_grammar_zones import card_noun
    spec = card_noun(m[1])
    if spec is None:
        return NO_MATCH
    return Effect("cx_card_move", target="that_player",
                  data={"to": "exile", "zone": "library", "random": True, "cx_card": spec})


def _discard_ref_exile(m):
    """"If the discarded card was <desc>, exile it from your graveyard": the referent is the card this
    ability just discarded, and only when it matches <desc> does the exile (and any "If you do" payoff)."""
    from .cards import Effect, NO_MATCH
    from .cx_grammar_zones import card_noun
    spec = card_noun(re.sub(r"^an? ", "", m[1]))
    if spec is None:
        return NO_MATCH
    return Effect("cx_card_move", target="none",
                  data={"to": "exile", "discard_ref": True, "cx_card": spec})


def _if_you_do_copy(m):
    """"If you do, create ... a copy of it/that card ...": the payoff of the discard-referent exile above.
    The copy reads item.exiled_card, which that exile sets only when it actually exiled the card."""
    import dataclasses
    from .cards import NO_MATCH
    from . import cx_tokens
    if not re.search(r"cop(?:y|ies) of (?:it|that card)\b", m[1], re.I):
        return NO_MATCH
    out = cx_tokens.parse_create("you", m[1])
    if not isinstance(out, list) or len(out) != 1 or "copy" not in out[0].data:
        return NO_MATCH
    return dataclasses.replace(out[0], data=dict(out[0].data, ref="card", if_you_do=True))


EFFECT_PATTERNS = [
    (r"exile a random (.+?) from that player's library", _lib_exile),
    (r"if the discarded card was (an? .+?), exile it from your graveyard", _discard_ref_exile),
    (r"if you do, creates? (.+)", _if_you_do_copy),
]
