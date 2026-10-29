"""Optional spell targets, graveyard-cast draw riders, and deck ETB wording families."""
from __future__ import annotations

import dataclasses
import re

KINDS = {"draw_pair", "sacrifice_types", "hand_exile_until_leaves", "random_graveyard_play"}
_N = r"a|one|two|three|four|five|six|seven|eight|nine|ten|\d+"
_TYPES = r"creature|artifact|enchantment|planeswalker"


def _effect(kind, *args, **kwargs):
    from .cards.model import Effect
    return Effect(kind, *args, **kwargs)


def _num(word):
    from .cards.model import _num
    return _num(word)


def parse_sequence(text):
    """Only complete paired/repeated wordings are treated as one scoped effect."""
    s = text.strip().rstrip(".")
    m = re.fullmatch(rf"target opponent sacrifices an? ({_TYPES})(?: of their choice)?\. if they can't, "
                     rf"they lose (\d+) life and you draw ({_N}) cards?\. then repeat this process for an? "
                     rf"({_TYPES}) and an? ({_TYPES})", s, re.I)
    if m:
        return [_effect("sacrifice_types", int(m[2]), target="player", filter="opp",
                        data={"types": tuple(m[i].capitalize() for i in (1, 4, 5)), "draw": _num(m[3])})]
    if re.fullmatch(r"look at target opponent's hand\. you may exile a nonland card from it until ~ leaves "
                    r"the battlefield", s, re.I):
        return [_effect("hand_exile_until_leaves", target="player", filter="opp")]
    return None


def parse_early(sentence):
    m = re.fullmatch(rf"target player draws ({_N}) cards? and loses (\d+) life", sentence, re.I)
    if m:
        return [_effect("draw", _num(m[1]), target="player"), _effect("lose_life", int(m[2]), target="prev")]
    m = re.fullmatch(rf"target player draws ({_N}) cards?", sentence, re.I)
    if m:
        return [_effect("draw", _num(m[1]), target="player")]
    m = re.fullmatch(rf"put ({_N}) \+1/\+1 counters? on up to one target creature( you control)?", sentence, re.I)
    if m:
        return [_effect("p1_counters", _num(m[1]), target="creature_mine" if m[2] else "creature",
                        data={"optional": True})]
    m = re.fullmatch(r"up to one target creature gets \+(\d+)/\+(\d+) until end of turn", sentence, re.I)
    if m:
        return [_effect("pump", int(m[1]), int(m[2]), target="creature", data={"optional": True})]
    m = re.fullmatch(r"up to one target creature gets -(\d+)/-(\d+) until end of turn", sentence, re.I)
    if m:
        return [_effect("debuff_one", int(m[1]), int(m[2]), target="creature", data={"optional": True})]
    m = re.fullmatch(r"destroy up to one target (artifact or enchantment|artifact|enchantment)", sentence, re.I)
    if m:
        return [_effect("destroy", target="nonland_perm", data={"optional": True},
                        filter="x:" + m[1].lower().replace(" or ", ",") + "||")]
    m = re.fullmatch(r"target opponent loses (\d+) life and you gain (\d+) life", sentence, re.I)
    if m:
        return [_effect("drain", int(m[1]), target="player", filter="opp"), _effect("gain_life", int(m[2]))]
    return None


def origin_rider(sentence, prior):
    m = re.fullmatch(rf"if ~ was cast from a graveyard, draw ({_N}) cards? instead", sentence, re.I)
    if not m:
        return None
    if not prior or prior[-1].kind != "draw" or prior[-1].target != "none" or prior[-1].cond:
        return False
    prior[-1] = dataclasses.replace(prior[-1], cond="!cast_from_graveyard")
    prior.append(_effect("draw", _num(m[1]), cond="cast_from_graveyard"))
    return True


def parse_trigger(line):
    from .cards.model import Trigger
    m = re.fullmatch(r"Whenever ~ attacks, if there are (\w+|\d+) or more cards in your graveyard, exile a card "
                     r"at random from your graveyard\. You may play that card this turn\.", line)
    if not m:
        return None
    try:
        n = _num(m[1])
    except ValueError:
        return None
    return [Trigger("attacks", [_effect("random_graveyard_play", data={"intervening_if": f"gy_size>={n}"})])], [], None


def _tribal_pump(m):
    from .cards.model import NO_MATCH
    # Preserve the uppercase subtype vocabulary; arbitrary lower-case restrictions stay unknown.
    types = re.split(r",? or |, ", m[1])
    if any(not re.fullmatch(r"[A-Z][a-z]+", t) for t in types):
        return NO_MATCH
    return _effect("pump", int(m[2]), int(m[3]), target="creature_mine",
                   filter="subtypes:" + "|".join(types), data={"keyword": m[4].lower()})


EFFECT_PATTERNS = [
    (rf"target player discards ({_N}) cards?", lambda m: _effect("discard", _num(m[1]), target="player")),
    (r"return target creature or Vehicle to its owner's hand",
     lambda m: _effect("bounce", target="creature_vehicle")),
    (rf"you and target opponent each draw ({_N}) cards?",
     lambda m: _effect("draw_pair", _num(m[1]), target="player", filter="opp")),
    (r"target ([\w ,]+?) you control gets \+(\d+)/\+(\d+) and gains (haste|flying|trample|vigilance|lifelink|"
     r"hexproof|indestructible) until end of turn", _tribal_pump),
]
SUBS = []


def return_hand_exiles(game, source):
    returning = getattr(source, "hand_exile_returns", [])
    source.hand_exile_returns = []
    for ref, owner in returning:
        card = ref.find(owner.exile)
        if card is not None:
            game.move_card(card, owner.exile, owner.hand, reason="until-source-leaves")


def resolve(game, p, eff, target, item):
    from .engine.state import Player
    if eff.kind == "draw_pair":
        game.draw(p, eff.amount)
        if isinstance(target, Player):
            game.draw(target, eff.amount)
    elif eff.kind == "sacrifice_types" and isinstance(target, Player):
        for typ in eff.data["types"]:
            if typ == "Creature":
                candidates = list(target.creatures)
            elif typ == "Planeswalker":
                candidates = list(target.planeswalkers)
            else:
                candidates = [x for x in target.battlefield if typ in x.card.types]
            if candidates:
                victim = game.hook(target, "choose_sacrifice")(game, target, list(candidates))
                if victim not in candidates:
                    from .engine.policy import perm_value
                    victim = min(candidates, key=perm_value)
                game.sacrifice(victim)
            else:
                game.change_life(target, -eff.amount, "unable to sacrifice")
                game.draw(p, eff.data["draw"])
    elif eff.kind == "hand_exile_until_leaves" and isinstance(target, Player):
        source = item.source if item else None
        if source is None or source not in source.controller.battlefield:
            return
        card = game.hook(p, "choose_discard_from")(game, p, target)
        if card is None or card not in target.hand or card.is_land:
            return
        card = game.move_card(card, target.hand, target.exile, reason="hand-exile-until-leaves")
        if not hasattr(source, "hand_exile_returns"):
            source.hand_exile_returns = []
        source.hand_exile_returns.append((target.exile.reference(card), target))
    elif eff.kind == "random_graveyard_play" and p.graveyard:
        card = game.rng.choice(p.graveyard)
        card = game.move_card(card, p.graveyard, p.exile, reason="random-graveyard-play")
        p.impulse.append((card, game.turn))
