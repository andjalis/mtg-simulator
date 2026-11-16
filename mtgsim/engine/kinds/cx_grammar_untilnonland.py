"""Kind for "exile cards from the top of your library until you exile a nonland card" (mtgsim.until_nonland, #625)."""
from . import kind


@kind("until_nonland")
def until_nonland(game, p, eff, **_):
    from ...until_nonland import resolve
    resolve(game, p, eff)
