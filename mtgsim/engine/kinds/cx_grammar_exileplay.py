"""Kinds for "you may play that card for as long as it remains exiled" (mtgsim.cx_exile_play, #316)."""
from . import kind


@kind("cx_exile_watch")
def exile_watch(game, item=None, **_):
    if item is not None:
        from ...cx_exile_play import start_watch
        start_watch(game, item)


@kind("cx_exile_play")
def exile_play(game, p, eff, item=None, **_):
    if item is not None:
        from ...cx_exile_play import grant
        grant(game, p, eff, item)


@kind("cx_exile_top_of")
def exile_top_of(game, p, eff, item=None, prev=None, target=None, **_):
    from ...cx_exile_play import exile_top_of as run
    run(game, p, eff, item, prev, target)
