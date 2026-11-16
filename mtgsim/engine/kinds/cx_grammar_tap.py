"""Kinds for the tap family (see mtgsim.cx_grammar_tap)."""
from ..state import Permanent
from . import kind


@kind("cx_skip_untap")
def skip_untap(game, p, eff, target, **_):
    """"It doesn't untap during its controller's next untap step". With ``yours_only`` ("... during your next untap
    step" of a permanent the sentence doesn't restrict to yours) it only applies while you control it: your untap
    step doesn't untap another player's permanent anyway."""
    if eff.data.get("yours_only") and getattr(target, "controller", None) is not p:
        return
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.skip_untap = max(target.skip_untap, 1)
