"""Change the target of target spell with a single target: the new target is any other legal one, preferring a permanent
or player the redirecting player's opponent controls."""
from ..state import Permanent, Player, StackItem, TARGETED
from ..policy import perm_value


def redirect_spell(game, p, spell) -> bool:
    if not isinstance(spell, StackItem) or spell not in game.stack:
        return False
    slots = [i for i, (e, t) in enumerate(zip(spell.effects, spell.targets)) if e.target in TARGETED and t is not None]
    if len(slots) != 1:
        return False
    i = slots[0]
    eff, old = spell.effects[i], spell.targets[i]
    with game.targeting(spell):
        legal = [t for t in game.legal_targets(spell.controller, eff) if t is not old]

    def owner(t):
        return t if isinstance(t, Player) else getattr(t, "controller", None)

    theirs = [t for t in legal if owner(t) is spell.controller]
    pool = theirs or legal
    if not pool:
        return False
    new = max(pool, key=lambda t: perm_value(t) if isinstance(t, Permanent) else 0)
    spell.targets[i] = new
    game.log(f"changes the target of {spell} to {new}", p)
    return True
