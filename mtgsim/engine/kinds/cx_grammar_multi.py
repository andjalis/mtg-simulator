"""``cx_multi``: a chain of effects run on each object of a list target ("any number of target ...", #391)."""
from . import kind


@kind("cx_multi")
def cx_multi(game, p, eff, target, item, **_):
    from . import HANDLERS
    probe, chain = eff.data["probe"], eff.data["chain"]
    if probe.kind == "blink" and len(chain) == 1:     # exiled together, then returned together (#318)
        from ...blink import blink_all
        with game.targeting(item):
            members = [m for m in target or () if game.legal_target(p, probe, m)]
        return blink_all(game, p, chain[0], members, item)
    for member in target or ():
        with game.targeting(item):
            if not game.legal_target(p, probe, member):
                continue        # an illegal target is unaffected; the others still are
        for inner in chain:
            if inner.cond and not game.check_cond(p, inner, item, member):
                continue        # "If C, those creatures ..." (cx_group_refs.cond_rider)
            HANDLERS[inner.kind](game, p=p, eff=inner, target=member, item=item, opp=game.opponent(p), prev=member,
                                 cause=f"cx_multi: {inner.kind}", k=inner.kind, source=item.source if item else None)
