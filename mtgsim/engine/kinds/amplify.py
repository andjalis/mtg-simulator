"""Amplify effect kind (see mtgsim.amplify)."""
from . import kind


@kind("amplify")
def amplify(game, p, eff, item, **_):
    from ... import amplify as _amplify
    _amplify.amplify(game, p, eff, item)
