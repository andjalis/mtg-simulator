"""Redirect a spell: "Change the target of target spell with a single target."

Read as a ``counter`` effect flagged ``redirect`` so it uses the counterspell's spell targeting (and the AI's spell choice);
the handler in engine/kinds/cx_night_redirect.py picks the new target."""
from __future__ import annotations


def _redirect(m):
    from .cards.model import Effect
    return [Effect("counter", target="spell", data={"redirect": True})]


EFFECT_PATTERNS = [(r"change the target of target spell with a single target", _redirect)]
