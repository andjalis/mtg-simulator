"""Kinds for the condition riders (see mtgsim.cx_grammar_cond)."""
from ..state import Permanent, Player, StackItem
from . import kind


def _payer(game, p, who, eff, item, prev):
    """The player who may pay (cx_grammar_cond._who_pays): you, an opponent, the trigger's player, the player B
    targets, or the controller of the object B targets / refers to."""
    if who == "you":
        return p
    if who == "opponent":
        return game.opponent(p)
    if who == "context":        # "that player": the trigger's player; the player handlers fall back to you
        context = getattr(item, "context", None)
        return context if isinstance(context, Player) else p
    if who == "prev_controller":
        return prev.controller if isinstance(prev, (Permanent, StackItem)) else None
    nxt = None
    if item is not None:
        i = next((n for n, e in enumerate(item.effects) if e is eff), None)
        if i is not None and i + 1 < len(item.targets):
            nxt = item.targets[i + 1]
    if who == "target":
        return nxt if isinstance(nxt, Player) else None
    return nxt.controller if isinstance(nxt, (Permanent, StackItem)) else None


@kind("cx_unless")
def unless(game, p, eff, item, prev=None, **_):
    """"B unless <payer> pays <cost>": the payer chooses to pay (if they can), and B (the effects after this one,
    gated on ``unless_unpaid``) happens only when they don't."""
    payer = _payer(game, p, eff.data["payer"], eff, item, prev)
    paid = False
    if payer is not None and game.hook(payer, "pay_unless")(game, payer, 0, item):
        paid = any(_pay(game, payer, cost, item, eff) for cost in eff.data["costs"])     # the first one they can pay
    if item is not None:
        item.cx_unless_paid = paid


def _stake(item, eff):
    """The source permanent the gated effects would sacrifice, destroy or exile ("sacrifice ~ unless ..."), else
    None: what a counted sacrifice is weighed against."""
    if item is None or not isinstance(item.source, Permanent):
        return None
    after = item.effects[next((i for i, e in enumerate(item.effects) if e is eff), len(item.effects)) + 1:]
    selfish = any(e.kind in ("sacrifice_self", "exile_self") or e.kind == "destroy" and e.target == "self"
                  for e in after if e.cond.endswith('"unless_unpaid"]'))
    return item.source if selfish else None


def _pay(game, payer, cost, item, eff=None) -> bool:
    """Pay the cost if the payer can (the ward and counter-unless rule: pay when able; life only above 2 after)."""
    from ..mana import find_payment
    from ..policy import perm_value
    from ...cx_condlib import _card_ok
    from ...residual_templates import life_locked
    if "life" in cost:
        n = cost["life"]
        if life_locked(payer) or payer.life <= n + 2:
            return False
        game.change_life(payer, -n, f"pays {n} life")
        return True
    if "sacrifice" in cost:
        source = getattr(item, "source", None)
        pool = [x for x in payer.battlefield if _card_ok(x.card, cost["sacrifice"], x)
                and not (cost["other"] and x is source)]
        n = cost.get("count", 1)
        if len(pool) < n:           # a counted cost needs every object: no partial payment
            return False
        chosen = sorted(pool, key=perm_value)[:n]
        if n > 1 and not game.hook(payer, "pay_unless_sacrifice")(game, payer, chosen, _stake(item, eff)):
            return False
        for x in chosen:
            game.sacrifice(x)
        return True
    if "discard" in cost:
        cards = [c for c in payer.hand if _card_ok(c, cost["discard"])]
        if not cards:
            return False
        choice = payer.ai.choose_discard(game, payer)
        game.discard_card(payer, choice if choice in cards else cards[0])
        return True
    mana = cost["mana"]
    if find_payment(game.mana_sources(payer, spell="ability"), mana) is None:
        return False
    game.pay(payer, mana)
    game.log(f"pays {sum(mana.values())} mana", payer)
    return True
