"""The cx_temp_cost kind (see mtgsim.cx_static_cost, #341 slice 2)."""
from . import kind


@kind("cx_temp_cost")
def temp_cost(game, p, eff, item=None, **_):
    """"The next Dragon spell you cast costs {2} less to cast" / "Artifact spells you cast this turn cost {1} less"
    (cx_static_cost, #341): a rule read by cost_of until it's spent or its turn ends."""
    d = eff.data
    amount = d["amount"]
    if "X" in amount:           # fixed now: "where X is ... as this ability resolves", or the X paid
        n = game.x_quantity(p, d["xq"], item, None) if "xq" in d else getattr(item, "x", 0)
        if n <= 0:
            return
        amount = {"generic": n}
    rules = game.__dict__.setdefault("temp_cost_rules", [])
    rules.append({"player": p, "turn": game.turn if d["this_turn"] else None, "once": d["once"],
                  "specs": d["specs"], "amount": amount})
