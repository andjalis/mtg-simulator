"""Kinds for "if it would leave the battlefield, exile it instead" (mtgsim.cx_replace_zones, #407)."""
from . import kind


@kind("cx_bf_watch")
def bf_watch(game, item=None, **_):
    from ...cx_replace_zones import watch
    watch(game, item)


@kind("cx_leave_exile")
def leave_exile(game, item=None, **_):
    from ...cx_replace_zones import mark
    mark(game, item)
