"""Linked results ("if you do"): see mtgsim/cx_links.py."""
from __future__ import annotations

from . import kind


@kind("link_start")
def link_start(game, p, eff, item, **_):
    from ...cx_links import decide, snapshot
    if item is None:
        return
    item.gate_paid = False
    item.link_taken = eff.data.get("forced") or decide(game, p, eff.data.get("kinds", ()))
    item.link_snapshot = snapshot(game) if item.link_taken else None


@kind("link_check")
def link_check(game, p, item, **_):
    from ...cx_links import snapshot
    if item is None:
        return
    item.gate_paid = bool(getattr(item, "link_taken", False)) and snapshot(game) != item.link_snapshot


def _matching(game, p, spec, source):
    from ...cx_condlib import _card_ok
    return [x for x in p.battlefield if not (spec.get("other") and x is source) and _card_ok(x.card, spec, x)]


@kind("sac_filtered")
def sac_filtered(game, p, eff, item, **_):
    """"Sacrifice an artifact / a Blood token / a nontoken creature": p's least valuable match."""
    from ..policy import perm_value
    source = getattr(item, "source", None)
    pool = _matching(game, p, eff.data["spec"], source)
    if not pool:
        return
    victim = min(pool, key=lambda x: (not x.card.is_token, perm_value(x)))
    if item is not None:
        item.gate_sac_stats = (victim.power, victim.toughness, victim.card.cmc)
    game.sacrifice(victim)


@kind("tap_own")
def tap_own(game, p, eff, item, **_):
    """"Tap N untapped creatures you control" (a cost inside an effect): nothing happens unless N are available."""
    from ..policy import perm_value
    source = getattr(item, "source", None)
    pool = [x for x in _matching(game, p, eff.data["spec"], source) if not x.tapped]
    if len(pool) < eff.amount:
        return
    for x in sorted(pool, key=perm_value)[:eff.amount]:
        x.tapped = True
        game.fire(p, "becomes_tapped", x)


@kind("peek_top")
def peek_top(game, p, eff, item, **_):
    """"Look at / reveal the top card of your library": remembered for "if it's a ... card" (cx_links)."""
    if item is not None:
        item.link_card = p.library[-1] if p.library else None
    if p.library and eff.data.get("reveal"):
        game.log(f"reveals {p.library[-1].name}", p)


@kind("ref_move")
def ref_move(game, p, eff, item, **_):
    """Put the looked-at top card into a hand, onto the battlefield, into the graveyard or on the bottom."""
    card = getattr(item, "link_card", None)
    if card is None or not p.library or p.library[-1] is not card:
        return
    to = eff.data["to"]
    if to == "battlefield":
        p.library.remove(card)
        perm = game.enter_battlefield(p, card)
        if eff.data.get("tapped"):
            perm.tapped = True
    elif to == "bottom":
        p.library.remove(card)
        p.library.insert(0, card)
    else:
        game.move_card(card, p.library, p.hand if to == "hand" else p.graveyard, reason="ref_move")
    game.log(f"puts {card.name} {'on the bottom of the library' if to == 'bottom' else 'into ' + to}", p)
    item.link_card = None


@kind("exert_self")
def exert_self(game, p, item, **_):
    """Exert: the source doesn't untap during its controller's next untap step (once per exert)."""
    src = getattr(item, "source", None)
    if src is None or src not in p.battlefield or getattr(src, "exerted_turn", None) == game.turn:
        return
    src.exerted_turn = game.turn
    src.skip_untap += 1
    game.fire(p, "exerted", src)
    game.log(f"exerts {src.card.name}", p)
