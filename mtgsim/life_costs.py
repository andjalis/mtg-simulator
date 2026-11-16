"""Life payments as a rules check versus as an AI choice (#467).

CR 119.4: a player can pay life only if their life total is greater than or equal to the payment, so paying
your last life is legal (the player then loses at the next state-based action check). The engine's legality
checks use ``life < n``. The AI is the one that shouldn't pay itself to 0: these helpers are its side of it.
"""


def spell_life_cost(game, p, card) -> int:
    """The life a cast of this spell_options() variant pays: an alternative cost's life ("pay 10 life rather
    than pay this spell's mana cost"), a printed additional life cost, and a life part of a choice cost."""
    _, _, alt = game._origin(card)
    n = (alt.life if alt is not None and alt.life else 0) + (card.extra_life_cost or 0)
    from . import cx_spell_costs
    if cx_spell_costs.alternatives(card):
        chosen = cx_spell_costs.choose(game, p, card)
        if chosen is not None:
            n += sum(k_n for kind, k_n, _, _ in chosen[1] if kind == "life")
    return n


def ai_spell_life_ok(game, p, card) -> bool:
    """Whether the AI is willing to pay this spell's life cost: never its last life."""
    n = spell_life_cost(game, p, card)
    return not n or p.life > n


def ai_ability_life_ok(p, act) -> bool:
    """Whether the AI is willing to pay this activated ability's life cost: never its last life."""
    n = act.extra_costs.get("life") or 0
    return not n or p.life > n
