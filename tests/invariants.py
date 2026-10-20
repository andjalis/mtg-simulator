"""Post-game state invariants shared by the bounded-game tests and the opt-in fuzz test."""

_BOUND = ("delayed_sacrifice", "delayed_exile", "delayed_destroy")


def violations(game):
    """Return a list of human-readable invariant violations for a finished game (empty if clean)."""
    bad = []
    on_field = [x for p in game.players for x in p.battlefield]
    ids = {id(x) for x in on_field}
    for p in game.players:
        for zone in ("hand", "graveyard", "exile", "library"):
            for c in getattr(p, zone):
                if c.is_token:
                    bad.append(f"{p.name}: token {c.name} in {zone}")
    for x in on_field:
        if x.attached_to is not None and id(x.attached_to) not in ids:
            bad.append(f"{x.card.name} attached to {x.attached_to.card.name}, which is off the battlefield")
    for e in game.delayed:
        if e.effect.kind in _BOUND and id(e.context) not in ids:
            bad.append(f"delayed {e.name!r} bound to an object that left the battlefield")
    if game.stack:
        bad.append(f"stack not empty: {len(game.stack)} item(s)")
    return bad


def assert_clean(test, game, label=""):
    test.assertEqual(violations(game), [], label or "post-game invariants")
