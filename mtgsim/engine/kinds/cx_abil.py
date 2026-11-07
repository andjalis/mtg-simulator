"""Effect kinds of the activated-ability lane (see cx_abil*.py)."""
import dataclasses

from . import kind


@kind("mana_restrict")
def mana_restrict(game, p, eff, **_):
    """"Spend this mana only to ...": the mana the ability just added can only pay what the restriction allows."""
    for mana in getattr(p, "last_added_mana", ()):
        mana.card = dataclasses.replace(mana.card, mana_restriction=eff.data["code"])
    p.last_added_mana = []
