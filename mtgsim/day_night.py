"""Day and night (CR 726): a game-wide state that starts when a daybound or nightbound permanent is
on the battlefield, flips at each untap step by the previous turn's spell count, and transforms every
daybound / nightbound permanent with it."""


def set_state(game, state):
    """Make it day or night and transform the permanents that face the wrong way."""
    changed = getattr(game, "day_night", None) not in (None, state)
    game.day_night = state
    for pl in game.players:
        for perm in list(pl.battlefield):
            c = perm.card
            if state == "night" and c.daybound and c.back is not None and c.back.nightbound:
                game.transform(perm)
            elif state == "day" and c.nightbound and getattr(perm, "front_face", None) is not None:
                game.transform(perm)
    game.log(f"it becomes {state}")
    if changed:
        for pl in game.players:
            game.fire(pl, "day_night_change")        # "whenever day becomes night or night becomes day"


def on_enter(game, perm):
    """A daybound or nightbound permanent entering: it becomes day if neither; a daybound one entering at
    night enters transformed."""
    c = perm.card
    if not (c.daybound or c.nightbound or c.advanced_rules.get("starts_day")):
        return
    if getattr(game, "day_night", None) is None:
        set_state(game, "night" if c.nightbound and not c.daybound else "day")    # CR 726.2
    elif game.day_night == "night" and c.daybound and c.back is not None and c.back.nightbound:
        game.transform(perm)
    elif game.day_night == "day" and c.nightbound and getattr(perm, "front_face", None) is not None:
        game.transform(perm)


def begin_turn(game, p):
    """At the start of p's untap step: day turns to night if the previous player cast no spells, night to day
    if they cast two or more."""
    previous = getattr(game, "dn_previous", None) or game.opponent(p)    # whose turn just ended (extra turns)
    game.dn_previous = p
    state = getattr(game, "day_night", None)
    if state is None:
        return
    cast = getattr(game, "last_turn_spells", {}).get(previous.name, 0)
    if state == "day" and cast == 0:
        set_state(game, "night")
    elif state == "night" and cast >= 2:
        set_state(game, "day")
