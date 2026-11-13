"""Counted mana amounts: "{T}: Add {G} for each creature you control", "Add an amount of {G} equal to ~'s power",
"Add {C} for each charge counter on ~". A card carries ``mana_dyn`` and the engine asks ``dynamic_amount`` for
how much mana the permanent makes when it is tapped (or counted toward a payment)."""
import re

_SYM = r"\{[WUBRGC]\}"


def parse_dynamic(text: str) -> tuple:
    """The mana_dyn tuple for the text after "{T}: Add ", or () if the amount isn't a supported count."""
    m = re.fullmatch(_SYM + r" for each ([\w+/-]+) counter on ~", text)
    if m:
        return ("counters", m[1])
    m = re.fullmatch(r"an amount of " + _SYM + r" equal to the number of ([\w+/-]+) counters on ~", text)
    if m:
        return ("counters", m[1])
    if re.fullmatch(r"an amount of " + _SYM + r" equal to ~'s power", text):
        return ("power",)
    m = re.fullmatch(_SYM + r" for each (\w+) (you control|on the battlefield)", text)
    from .counting import known
    if m and known(m[1]):    # one type or subtype word: copies.fits can't test "with defender" or "power 4 or greater"
        return ("count", m[1], "battlefield" if m[2] == "you control" else "all")
    return ()


def dynamic_amount(perm) -> int:
    kind = perm.card.mana_dyn
    if kind[0] == "power":
        return max(0, perm.power)
    if kind[0] == "counters":
        return perm.counters.get(kind[1], 0)
    from .counting import count
    return count(perm.controller._game, perm.controller, {"what": kind[1], "zone": kind[2]}, perm)
