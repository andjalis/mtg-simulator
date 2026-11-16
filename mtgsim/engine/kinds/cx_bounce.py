"""Bounce residue (#638): "Each player returns a creature they control to its owner's hand."."""
from ... import permanent_templates
from ..policy import perm_value
from . import kind


@kind("bounce_choice")
def bounce_choice(game, p, eff, item, opp, target=None, **_):
    """Each named player returns one permanent of theirs that fits the selector: the cheapest (a tapped land
    first, the source itself last), as for the other choose-your-own effects. "named": the player a grammar
    ``cx_players`` wrapper hands over ("that player returns a land they control", cx_grammar_bounce)."""
    from ..state import Player
    src = item.source if item is not None else None
    if eff.data["who"] == "named":
        who = [target] if isinstance(target, Player) else []
    else:
        who = {"you": [p], "each": [p, opp], "opponents": [opp]}[eff.data["who"]]
    for player in who:
        pool = [x for x in player.battlefield if permanent_templates.matches(game, x, eff.data["selector"], player, src)]
        if not pool:
            continue
        pick = min(pool, key=lambda x: (x is src, not (x.card.is_land and x.tapped), perm_value(x)))
        game.log(f"returns {pick.card.name} to hand", player)
        game.leave_battlefield(pick, "hand")


@kind("shuffle_zones_in")
def shuffle_zones_in(game, p, eff, opp, **_):
    """"Each player shuffles their hand (and graveyard) into their library" (Diminishing Returns, Weftwalking)."""
    for who in ([p, opp] if eff.data.get("who") == "each" else [p]):
        for card in list(who.hand):
            who.hand.remove(card)
            who.library.append(card)
        if eff.data.get("graveyard"):
            for card in list(who.graveyard):
                who.graveyard.remove(card)
                who.library.append(card)
        who.library.shuffle(game.rng)
        game.log(f"{who} shuffles their hand{' and graveyard' if eff.data.get('graveyard') else ''} into their library", p)


@kind("source_card_to_hand")
def source_card_to_hand(game, item, **_):
    """"Return this card to its owner's hand" after it left the battlefield (Angelic Destiny's Aura, Weatherseed
    Totem): the source's own card, from its owner's graveyard. Gone elsewhere (exile, a token): nothing happens."""
    from ..state import Permanent
    from .permanents import _from_graveyard
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src not in src.controller.battlefield:
        _from_graveyard(game, src)      # the card it became, if it is still where it went (CR 400.7)


@kind("life_total")
def life_total(game, p, eff, target, opp, **_):
    """Double / set / exchange a life total (#629): the difference is gained or lost (rule 119.5)."""
    from ..state import Player
    op, who = eff.data["op"], eff.data["who"]
    players = {"you": [p], "each": list(game.players), "opponents": [opp]}.get(who) or \
        ([target] if isinstance(target, Player) else [])
    if op == "exchange":
        if eff.data.get("both"):        # "two target players": you are the other target (#629)
            from ...batch1_templates import player_targetable
            if not player_targetable(game, p, p):
                return
        if eff.data.get("may") and players and players[0].life <= p.life:
            return                      # "you may": only exchanged when it gains you life
        if players and players[0] is not p:
            a, b = p.life, players[0].life
            game.change_life(p, b - a, "exchange life totals")
            game.change_life(players[0], a - b, "exchange life totals")
        return
    lives = [pl.life for pl in game.players]
    for pl in players:
        goal = (max(pl.life, 0) * 2 if op == "double" else min(lives) if op == "lowest" else max(lives)
                if op == "highest" else eff.amount)
        game.change_life(pl, goal - pl.life, f"life total {op}")
        game.log(f"life total is now {pl.life}", pl)


@kind("player_loses")
def player_loses(game, p, target, **_):
    """"Target player loses the game" (#629)."""
    from ..state import Player
    from ...cx_night_aura import cant_lose
    if isinstance(target, Player) and not target.lost and not cant_lose(game, target):
        game.audit("loss", seat=game.players.index(target), cause="a card's effect")
        target.lost = True
