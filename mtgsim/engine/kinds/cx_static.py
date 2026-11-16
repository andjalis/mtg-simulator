"""Small effect kinds for the static lane (sim-static)."""
from . import kind


def _gate_before(item, eff) -> str:
    """The kind of the gate eff follows in its item: "pay_gate" ("You may exile two cards from your graveyard. If you
    do, ..."), "link_start" ("... When you do, ..."), or ""."""
    effects = getattr(item, "effects", None) or []
    index = next((i for i, e in enumerate(effects) if e is eff), None)
    kind_before = effects[index - 1].kind if index else ""
    return kind_before if kind_before in ("pay_gate", "link_start") else ""


@kind("exile_own_gy_n")
def exile_own_gy_n(game, p, eff, item=None, **_):
    """"Exile two cards from your graveyard." (Bloodcurdler's end step): exile N cards of your own graveyard, all of
    them when there are fewer (rule 609.3). After "you may" / "when you do" it is exactly N or nothing: declined or
    impossible, nothing is exiled and the "If you do" / "When you do" payoff doesn't happen. The AI keeps the
    creature cards and the expensive ones."""
    gate = _gate_before(item, eff)
    if gate == "pay_gate" and not getattr(item, "gate_paid", False):
        return                              # "you may": declined
    if gate and len(p.graveyard) < eff.amount:
        item.gate_paid = False
        return
    picks = sorted(p.graveyard, key=lambda c: (c.is_creature, c.cmc))[:eff.amount]
    for card in picks:
        game.move_card(card, p.graveyard, p.exile, reason="exile_graveyard")
    if picks:
        game.log(f"exiles {len(picks)} card(s) from their graveyard", p)
