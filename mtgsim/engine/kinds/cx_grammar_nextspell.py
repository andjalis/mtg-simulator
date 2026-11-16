"""Kind for "the next <kind> spell you cast this turn has <keyword>" (mtgsim.spell_grants, #633)."""
from . import kind


@kind("next_spell_grant")
def next_spell_grant(game, p, eff, **_):
    from ...spell_grants import register_next
    register_next(game, p, eff)
