"""#646: Evoke with a non-mana cost (CR 702.74).

    Evoke—Exile a white card from your hand.          (Solitude; Fury, Grief, Endurance, Subtlety likewise)

CR 702.74a: "You may cast this spell by paying [cost] rather than paying its mana cost" and "When this permanent
enters, if its evoke cost was paid, its controller sacrifices it." The cost is read with cx_altcost's cost parts (a
"pitch": exile a card of that colour from your hand, never the spell itself) into a ``cond_alt_<i>`` alternative cost,
so it is offered, paid and cast exactly like Force of Will's; its index is listed in ``advanced_rules["evoke_alts"]``,
and Game's resolution sacrifices the permanent as it does for a mana evoke (stack.py: ``evoked``).

HeuristicAI (``ai_value``): an evoked creature is worth only what its enters abilities do, less the card exiled to pay
for it, so it isn't evoked with nothing to hit.
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Evoke—(Exile an? (?:white|blue|black|red|green) card from your hand)\.", line.strip())
    if not m:
        return False
    from .cx_altcost import _add, _parts
    got = _parts(m[1][0].lower() + m[1][1:])
    if got is None or got[0] is not None or got[1] or [p[0] for p in got[2]] != ["pitch"]:
        return False
    rules = st.extra.setdefault("advanced_rules", {})
    index = len(rules.get("alt_if", ()))
    _add(st, None, None, 0, got[2])
    rules["evoke_alts"] = tuple(rules.get("evoke_alts", ())) + (f"cond_alt_{index}",)
    return True


def evoked(base, kind: str) -> bool:
    """Whether a spell cast as variant ``kind`` of ``base`` was cast for a non-mana evoke cost."""
    return kind in ((base.advanced_rules or {}).get("evoke_alts") or ())


def ai_value(ai, game, me, card, precombat) -> float | None:
    """HeuristicAI's value of casting ``card`` when it is a non-mana evoke variant, else None: its enters value minus
    the card it exiles (a hand card is worth about its own card value)."""
    from .ai import card_value
    base, kind, _ = game._origin(card)
    if not evoked(base, kind):
        return None
    from .cx_altcost import _candidates, _rule
    from .engine.policy import _mode_value
    effects = [e for t in base.triggers if t.event == "etb" for e in t.effects] or list(base.etb_effects)
    from .engine.state import TARGETED
    with game.targeting(base):
        targets = game.auto_targets(me, effects, None) if effects else []
        aimed = all(t is not None for e, t in zip(effects, targets) if e.target in TARGETED)
        etb = max(ai._etb_value(game, me, base, precombat),
                  _mode_value(game, me, effects) if effects and aimed else 0.0)     # "up to one": nothing to hit
    _, parts = _rule(base, kind)
    pitched = sum(min((card_value(c) for c in _candidates(game, me, base, part, n, spec)), default=0.0) * n
                  for part, n, spec in parts)
    return etb - pitched
