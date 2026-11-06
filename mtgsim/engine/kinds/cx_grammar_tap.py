"""Kinds for the tap family (see mtgsim.cx_grammar_tap)."""
from ..state import Permanent
from . import kind


@kind("cx_skip_untap")
def skip_untap(game, target, **_):
    """"It doesn't untap during its controller's next untap step"."""
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.skip_untap = max(target.skip_untap, 1)
