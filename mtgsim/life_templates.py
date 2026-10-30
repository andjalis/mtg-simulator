"""Life-gain triggers the engine's gain-life events feed: "Whenever an opponent gains life,
…" (Punishing Fire returns itself from the graveyard, Kavu Predator grows by that much).

The event needs Game.change_life to also fire ``opp_gains_life`` to the gaining player's
opponent (mirroring the existing ``opp_loses_life`` delivery), so the trigger template is
only reachable once that one-line engine hook lands; tests fire the event directly.
"""
from __future__ import annotations


def _e(kind, **kw):
    from .cards import Effect
    return Effect(kind, 0, **kw)


TRIGGERS = [
    (r"Whenever an opponent gains life, (.+)", ("opp_gains_life",)),
]

EFFECT_PATTERNS = [
    # Kavu Predator: "put that many +1/+1 counters on ~" after the opponent gained life.
    (r"put that many \+1/\+1 counters on (?:~|it)", lambda m: _e("p1_counters", target="self",
                                                                data={"that_much": True})),
]

SUBS = []
