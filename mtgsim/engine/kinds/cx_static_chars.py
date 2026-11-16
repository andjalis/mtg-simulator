"""The cx_lose_all kind (see mtgsim.cx_static_chars, #406 slice 3)."""
from . import kind




@kind("cx_lose_all")
def lose_all(game, eff, target, **_):
    """"Target creature loses all abilities [until end of turn]": a layer-6 effect (cx_static_chars.strip)."""
    from ..state import Permanent
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        game.add_continuous_effect(target, "lose_all", until_eot=eff.data.get("eot", True))
