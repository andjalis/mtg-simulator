"""Ripple (Betrayers of Kamigawa): "when you cast ~, ripple N" — reveal the top N cards of
your library and cast any revealed cards with the same name for free; the rest go to the
bottom (shuffled, like cascade's reveal pile).

Ripple N is parsed as a cast-self trigger (the wording rides inside the keyword's reminder
text, which the face parser strips, so the keyword line itself is the trigger pattern), and
Thrumming Stone's "Spells you cast have ripple 4" is the same trigger on every spell its
controller casts. The free casts go through the cascade/impulse exile-cast foundation:
each revealed card is exiled while the ripple resolves, cast with a zero cost from exile,
and removed from exile when it leaves the stack.

Recorded simplifications: every same-name card found is always cast (no per-card decline),
and the revealed cards are revealed in library order from the top.
"""
from __future__ import annotations

import dataclasses


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"ripple (\d+)", lambda m: _e("ripple", int(m[1]))),
]

TRIGGERS = [
    (r"(Ripple \d+)", ("cast_self",)),                       # Surging Sentinel and friends
    (r"Spells you cast have (ripple \d+)\.", ("cast_spell",)),  # Thrumming Stone
]


def ripple(game, p, eff, item):
    """Resolve one ripple: reveal, free-cast the name matches, bottom the rest."""
    n = eff.amount
    revealed = []
    for _ in range(min(n, len(p.library))):
        card = p.library.pop()
        p.exile.append(card)
        revealed.append(card)
    if not revealed:
        return
    game.log(f"reveals {', '.join(c.name for c in revealed)} (ripple {n})", p)
    src = item.context if item is not None else None
    name = getattr(getattr(src, "card", None), "name", None)
    if name is not None:
        name = name.split(" (")[0]        # a free-cast variant is still the same card name
    if name is not None:
        for card in [c for c in revealed if c.name == name]:
            if cast_revealed(game, p, card):
                revealed.remove(card)
    bottom = []
    for card in revealed:
        if card in p.exile:
            p.exile.remove(card)
            bottom.append(card)
    game.rng.shuffle(bottom)
    p.library[0:0] = bottom
    if bottom:
        game.log(f"puts {len(bottom)} card(s) on the bottom", p)


def cast_revealed(game, p, card):
    """Cast a revealed card without paying its mana cost, out of exile (impulse origin)."""
    from .cards import AltCost
    from .engine import TARGETED
    free = dataclasses.replace(card, name=f"{card.name} (ripple)", mana_cost={"generic": 0}, hybrid=())
    free.origin = (card, "impulse", AltCost("impulse", {"generic": 0}))
    free.origin_generation = getattr(card, "generation", None)
    targets = game.auto_targets(p, free.spell_effects)
    if any(e.target in TARGETED and not game.legal_target(p, e, t)
           for e, t in zip(free.spell_effects, targets)):
        return False
    return game.can_cast_now(p, free, during_resolution=True) and game.cast(p, free, targets)
