"""Kinds for the compositional effect grammar (see mtgsim.cx_grammar)."""
from ..state import Permanent, Player
from . import kind


@kind("cx_group")
def group(game, p, item, eff, target, prev=None, **_):
    """Apply each inner effect to every permanent the group names ("creatures target player controls": that
    player's), fixed when the effect resolves."""
    from ...cx_grammar import group_members
    from . import HANDLERS
    if eff.target == "player" and not isinstance(target, Player):
        return
    source = item.source if item else None
    inners = _scaled(game, p, eff, item, prev)
    for victim in group_members(game, p, eff.data, source, target if eff.target == "player" else None):
        for inner in inners:
            HANDLERS[inner.kind](game, p=p, eff=inner, target=victim, item=item, opp=game.opponent(p), prev=prev,
                                 cause=f"cx_group: {inner.kind}", k=inner.kind, source=source)


@kind("cx_color")
def color(game, target, eff, **_):
    """Layer 5: the permanent becomes the colours (or gains them, "in addition to its other colors")."""
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        game.add_continuous_effect(target, eff.data["op"], colors=frozenset(eff.data["colors"]),
                                   until_eot=eff.data["eot"])


@kind("cx_players")
def players(game, p, item, eff, prev=None, target=None, **_):
    """Each inner player effect, applied to the players the subject names ("each player", "defending player",
    "that creature's controller", ...)."""
    from ...cx_grammar import players as named
    from . import HANDLERS
    named_players = named(game, p, eff.data["who"], item, prev, target)
    if eff.data.get("xq_rel"):      # "... for each creature they control": the count is each named player's own (#337)
        _per_player(game, p, eff, item, prev, named_players)
        return
    for inner in _scaled(game, p, eff, item, prev):          # "each player discards a card, then draws a card": all, verb by verb
        for who in named_players:
            HANDLERS[inner.kind](game, p=p, eff=inner, target=who, item=item, opp=game.opponent(p), prev=prev,
                                 cause=f"cx_players: {inner.kind}")


def _per_player(game, p, eff, item, prev, named_players):
    """cx_players with a subject-relative quantity (cx_grammar_playerq): every player's count is read first, then
    the inner effects run verb by verb with each player's own count."""
    import dataclasses
    from . import HANDLERS
    spec = eff.data["xq"]
    counts = [game.x_quantity(who, spec, item, eff.data.get("cast_spell") or prev) for who in named_players]
    for inner in eff.data["effects"]:
        for who, n in zip(named_players, counts):
            scaled = dataclasses.replace(inner, amount=inner.amount * n, amount2=inner.amount2 * n)
            HANDLERS[inner.kind](game, p=p, eff=scaled, target=who, item=item, opp=game.opponent(p), prev=prev,
                                 cause=f"cx_players: {inner.kind}")


def _scaled(game, p, eff, item, prev):
    """The inner effects with their amounts multiplied by the wrapper's X ("for each ..." / "where X is ...").
    Inner handlers are called directly, so the shared amount rules in Game.resolve don't reach them."""
    import dataclasses
    inners = eff.data["effects"]
    if eff.data.get("x"):           # X paid: Game.resolve put it in the wrapper's amount
        inners = [dataclasses.replace(e, amount=eff.amount, amount2=eff.amount if e.data.get("x2") else e.amount2)
                  if e.data.get("x") else e for e in inners]
    if not eff.data.get("xq"):
        return inners
    n = game.x_quantity(p, eff.data["xq"], item, eff.data.get("cast_spell") or prev)
    return [dataclasses.replace(e, amount=e.amount * n, amount2=e.amount2 * n) for e in inners]


@kind("cx_rule_turn")
def rule_turn(game, eff, target, **_):
    """A family rule on the target for this turn ("~ can't be blocked by Walls this turn"): cx_grammar.static_rules."""
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.cx_rules_turn = [r for r in getattr(target, "cx_rules_turn", []) if r[0] == game.turn] + \
            [(game.turn, eff.data["rule"], eff.data["value"])]


@kind("cx_player_rule")
def player_rule(game, eff, target, **_):
    """A family rule on a player for this turn ("target player can't cast creature spells this turn"):
    cx_grammar.player_rules (run inside cx_players with target = the player)."""
    from ..state import Player
    if isinstance(target, Player):
        game.cx_player_rules = [r for r in getattr(game, "cx_player_rules", []) if r[0] == game.turn] + \
            [(game.turn, eff.data["rule"], eff.data["value"], target)]


def _load_families():
    """Import every engine/kinds/cx_grammar_<family>.py module (they register their kinds)."""
    import importlib
    import pkgutil
    from . import __path__ as package
    for info in sorted(pkgutil.iter_modules(package), key=lambda i: i.name):
        if info.name.startswith("cx_grammar_"):
            importlib.import_module(f"{__package__}.{info.name}")


_load_families()
