"""``cx_multi``: a chain of effects run on each object of a list target ("any number of target ...", #391)."""
from . import kind


@kind("cx_multi")
def cx_multi(game, p, eff, target, item, **_):
    from . import HANDLERS
    probe, chain = eff.data["probe"], eff.data["chain"]
    for member in target or ():
        with game.targeting(item):
            if not game.legal_target(p, probe, member):
                continue        # an illegal target is unaffected; the others still are
        for inner in chain:
            HANDLERS[inner.kind](game, p=p, eff=inner, target=member, item=item, opp=game.opponent(p), prev=member,
                                 cause=f"cx_multi: {inner.kind}", k=inner.kind, source=item.source if item else None)
