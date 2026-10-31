"""Small effects for the most common single-sentence gaps.

* "Destroy / Exile / Return target <desc> [to its owner's hand]" where <desc> is a disjunction the base table
  doesn't know ("creature or Vehicle", "artifact, creature, or Vehicle you control"): the description is read
  with the trigger-event library's subject grammar and checked in ``Game.passes_filter`` (``cx_desc``).
* "Target opponent draws N cards." / "Each opponent draws N cards." (two players: the opponent draws).
* "Put [up to N] target <desc> card from your graveyard on top of your library."
* "Return a <desc> card at random from your graveyard to your hand / the battlefield."
* "If a creature would die this turn, exile it instead." (every creature, for the rest of the turn) and
  "If it / that creature would die this turn, exile it instead." (the previous target).
* "for each card in target opponent's hand" / "in each opponent's hand": the opponent's hand size.
"""
from __future__ import annotations

import re

KINDS = {"cx_gy_top", "cx_gy_random", "cx_exile_turn"}
_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _num(word):
    word = word.lower()
    return int(word) if word.isdigit() else _N[word]


def _desc_ok(desc: str):
    from .cx_events import _object_subject
    spec = _object_subject("a " + desc)
    return spec is not None and not spec["host"] and not spec["batch"] and not spec["self"]


def _targeted(kind):
    def make(m):
        from .cards.model import NO_MATCH
        from .cards import Effect
        desc = m[1]
        if " or " not in desc and "," not in desc or not _desc_ok(desc):
            return NO_MATCH
        return Effect(kind, target="permanent", data={"cx_desc": desc})
    return make


def _draws(m):
    from .cards import Effect
    return Effect("draw", _num(m[1]), target="each_opponent")


def _gy_top(m):
    from .cards.model import NO_MATCH
    from .cards import Effect
    from .cx_events import _desc_alts
    desc = (m[2] or "").strip()
    if desc and _desc_alts(desc) is None:
        return NO_MATCH
    return Effect("cx_gy_top", _num(m[1]) if m[1] else 1, data={"what": desc, "up_to": bool(m[1])})


def _gy_random(m):
    from .cards.model import NO_MATCH
    from .cards import Effect
    from .cx_events import _desc_alts
    if _desc_alts(m[1]) is None:
        return NO_MATCH
    return Effect("cx_gy_random", 1, data={"what": m[1], "dest": "hand" if m[2] == "your hand" else "bf"})


def _exile_turn(m):
    from .cards import Effect
    return Effect("cx_exile_turn")


def _exile_prev(m):
    from .cards import Effect
    return Effect("exile_instead", target="prev")


EFFECT_PATTERNS = [
    (r"destroy target ([\w ,/-]+?)", _targeted("destroy")),
    (r"exile target ([\w ,/-]+?)", _targeted("exile_permanent")),
    (r"return target ([\w ,/-]+?) to its owner's hand", _targeted("bounce")),
    (r"(?:target|each) opponent draws (a|an|one|two|three|\d+) cards?", _draws),
    (r"put (?:up to (one|two|three) )?target ((?:[\w-]+ )*?)cards? from your graveyard on top of your library",
     _gy_top),
    (r"return an? ([\w ,-]+?) card at random from your graveyard to (your hand|the battlefield)", _gy_random),
    (r"if a creature would die this turn, exile it instead", _exile_turn),
    (r"if (?:it|that creature|the creature an opponent controls|that permanent) would die this turn, exile it instead",
     _exile_prev),
]

SUBS = [
    (re.compile(r"for each card in (?:target|each) opponent's hand", re.I), "for each card in an opponent's hand"),
]


# ---------------------------------------------------------------- engine side

def passes(game, eff, perm, by) -> bool | None:
    """The cx_desc target check, or None when the effect has none."""
    desc = eff.data.get("cx_desc")
    if not desc:
        return None
    from .cx_events import _object_subject, _obj_match
    spec = _object_subject("a " + desc)
    if spec is None:
        return False

    class _Viewer:              # _obj_match reads the watcher's controller for "you control"
        controller = by
    return _obj_match(game, spec, _Viewer, perm)


def _card_fits(card, desc: str) -> bool:
    if not desc:
        return True
    from .engine.state import card_matches
    return card_matches(card, "a " + desc.strip() + " card") or card_matches(card, "a " + desc.strip())


def gy_top(game, p, eff):
    picks = sorted((c for c in p.graveyard if _card_fits(c, eff.data["what"])), key=lambda c: c.cmc, reverse=True)
    for card in picks[:eff.amount]:
        game.move_card(card, p.graveyard, p.library, reason="gy_to_top")     # the library's end is its top
        game.log(f"puts {card.name} on top of their library", p)


def gy_random(game, p, eff):
    pool = [c for c in p.graveyard if _card_fits(c, eff.data["what"])]
    if not pool:
        return
    card = game.rng.choice(pool)
    if eff.data["dest"] == "hand":
        game.move_card(card, p.graveyard, p.hand, reason="return")
        game.log(f"returns {card.name} at random to their hand", p)
    else:
        p.graveyard.remove(card)
        game.enter_battlefield(p, card)


def exile_this_turn(game, perm) -> bool:
    return getattr(game, "cx_exile_turn", None) == game.turn and perm.is_creature
