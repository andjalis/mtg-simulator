"""For Mirrodin! effect kind (see mtgsim.for_mirrodin)."""
from . import kind


@kind("for_mirrodin")
def for_mirrodin(game, p, eff, item, **_):
    from ... import for_mirrodin as _for_mirrodin
    _for_mirrodin.for_mirrodin(game, p, eff, item)
