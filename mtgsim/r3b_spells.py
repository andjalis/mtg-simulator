"""Life-gain rewards, source-excluding grants, connive and graveyard-entry riders."""
from __future__ import annotations

from contextlib import contextmanager
import re

KINDS = {"surveil_life_pick", "reanimate_life_target", "remove_source_counter", "pay_life_gate", "connive_many"}
BATCH_KINDS = {"wrath", "wrath_pw", "mill", "surveil", "discard", "rummage", "wheel_self",
               "connive", "connive_many", "edict", "destroy_other_exact_power"}


def _effect(kind, **kwargs):
    from .cards.model import Effect
    return Effect(kind, **kwargs)


_LIFE_RETURN = (r"return up to one target creature card with mana value x or less from your graveyard to the battlefield, "
                r"where x is the amount of life you gained this turn")

EFFECT_PATTERNS = [
    (r"another target (creature or planeswalker|creature) you control gains (hexproof|indestructible|flying|haste) "
     r"until end of turn", lambda m: _effect("grant", target="creature_pw" if "planeswalker" in m[1].lower()
                                           else "creature_mine", filter="mine",
                                           data={"other": True, "keyword": m[2].lower()})),
    (_LIFE_RETURN,
     lambda m: _effect("reanimate_life_target", target="graveyard_creature_life")),
    (r"target attacking creature connives x, where x is the number of attacking creatures",
     lambda m: _effect("connive_many", target="creature", filter="attacking", data={"attackers": True})),
    (r"target attacking creature connives (\d+)",
     lambda m: _effect("connive_many", amount=int(m[1]), target="creature", filter="attacking")),
    (r"remove a -1/-1 counter from ~", lambda m: _effect("remove_source_counter", amount=1,
                                                       data={"counter": "-1/-1"})),
]
SUBS = []


def parse_dynamic(sentence):
    # Target restrictions must retain X rather than be turned into effect amounts.
    return _effect("reanimate_life_target", target="graveyard_creature_life") if re.fullmatch(
        _LIFE_RETURN, sentence, re.I) else None


def parse_rider(sentence, prior):
    """Only the exact supported surveil antecedent can supply this card."""
    if not re.fullmatch(r"if you put a card with mana value less than or equal to the amount of life you gained "
                        r"this turn into your graveyard this way, put that card into your hand", sentence, re.I):
        return None
    if not prior or prior[-1].kind != "surveil" or prior[-1].amount != 1:
        return False
    return [_effect("surveil_life_pick")]


def parse_trigger(line):
    from .cards.model import Trigger
    m = re.fullmatch(r"Whenever one or more permanent cards are put into your graveyard from anywhere while ~ "
                     r"has a -1/-1 counter on it, remove a -1/-1 counter from ~\.", line)
    if m:
        return [Trigger("permanent_cards_to_gy", [_effect("remove_source_counter", amount=1,
                                                          data={"counter": "-1/-1"})], filter="-1/-1")], [], None
    return None


def source_pronouns(rest, events):
    if events not in (("etb",), ("attacks",)):
        return rest
    if re.fullmatch(r"you may pay \d+ life\. if you do, it gains [^.]+ until end of turn\.", rest, re.I):
        return re.sub(r"\bit gains\b", "~ gains", rest, flags=re.I)
    if re.fullmatch(r"put (?:an?|\w+|\d+) [+-]\d+/[+-]\d+ counters? on it(?: if you gained life this turn)?\.",
                    rest, re.I):
        return re.sub(r"\bon it\b", "on ~", rest, flags=re.I)
    return rest


def parse_static(line, extra):
    m = re.fullmatch(r"(Other )?([A-Z][a-z]+)s you control get \+(\d+)/\+(\d+) and have "
                     r"(haste|menace|trample|flying|vigilance|lifelink|first strike|double strike|deathtouch|reach|"
                     r"indestructible)\.", line)
    if m is None or m[2] == "Creature":
        return False
    extra["anthem_sub"] = extra.get("anthem_sub", ()) + ((m[2], int(m[3]), int(m[4]), bool(m[1])),)
    extra["keyword_sub"] = extra.get("keyword_sub", ()) + ((m[2], m[5], bool(m[1])),)
    return True


@contextmanager
def graveyard_event(game, enabled=True):
    """Group simultaneous arrivals while keeping nested, separate events distinct."""
    if not enabled:
        yield
        return
    batches = getattr(game, "_graveyard_batches", None)
    if batches is None:
        batches = game._graveyard_batches = []
    arrivals = []
    batches.append(arrivals)
    try:
        yield
    finally:
        batches.pop()
        owners = dict.fromkeys(owner for owner, _ in arrivals)
        for owner in owners:
            cards = tuple(card for who, card in arrivals if who is owner)
            game._dispatch_trigger_event(owner, "permanent_cards_to_gy", subject=cards)


def graveyard_arrival(game, card, destination):
    if destination.name != "graveyard" or not card.is_permanent or card.is_token:
        return
    batches = getattr(game, "_graveyard_batches", [])
    if batches:
        batches[-1].append((destination.owner, card))
    else:
        game._dispatch_trigger_event(destination.owner, "permanent_cards_to_gy", subject=(card,))


def target_active(eff, target, item):
    if eff.data.get("other") and target is item.source:
        return False
    if eff.target == "graveyard_creature_life":
        ref = item.graveyard_targets.get(id(target))
        return ref is not None and ref.find(item.controller.graveyard) is target
    return True


def resolve(game, p, eff, target, item):
    if eff.kind == "surveil_life_pick":
        for ref in getattr(item, "surveilled", {}).get(p, []):
            card = ref.find(p.graveyard)
            if card is not None and card.cmc <= p.life_gained_turn:
                game.move_card(card, p.graveyard, p.hand, reason="surveil-life-reward")
    elif eff.kind == "reanimate_life_target":
        if target is not None and target in p.graveyard:
            p.graveyard.remove(target)
            game.enter_battlefield(p, target)
    elif eff.kind == "remove_source_counter":
        src = item.source if item is not None else None
        if src is not None and src in src.controller.battlefield:
            ctr = eff.data["counter"]
            src.counters[ctr] = max(0, src.counters.get(ctr, 0) - eff.amount)
    elif eff.kind == "pay_life_gate":
        if item is not None:
            item.gate_paid = p.life >= eff.amount and game.hook(p, "pay_optional")(
                game, p, {"life": eff.amount}, "life")
            if item.gate_paid:
                game.change_life(p, -eff.amount, "optional life payment")
    elif eff.kind == "connive_many":
        from .engine.state import Permanent
        if not isinstance(target, Permanent) or target not in target.controller.battlefield:
            return
        who = target.controller
        n = len(game.attackers) if eff.data.get("attackers") else eff.amount
        game.draw(who, n)
        nonlands = 0
        for _ in range(min(n, len(who.hand))):
            card = who.ai.choose_discard(game, who)
            nonlands += not card.is_land
            game.discard_card(who, card)
        if target in who.battlefield:
            target.counters["+1/+1"] = target.p1 + nonlands
