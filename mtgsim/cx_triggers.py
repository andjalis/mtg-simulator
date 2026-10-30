"""Trigger and effect wordings from the cards lane: tap-and-stun on cast, "that much" damage riders, hand-reveal
discard of two cards, entered-this-turn hexproof, and Crabomination's three-zone exile.

    When you cast this spell, tap up to four target permanents.                         (Elder Deep-Fiend)
    ~ has hexproof as long as it entered this turn.                                     (Drownyard Behemoth)
    Whenever enchanted creature is dealt damage, its controller loses that much life.   (Ragged Veins)
    Whenever enchanted creature is dealt damage, ~ deals that much damage to that creature's controller.
                                                                                        (Binding Agony)
    Whenever a creature you control deals combat damage, you gain that much life.       (Noble Purpose)
    Target opponent reveals their hand. You choose from it a nonland card with mana value 3 or less and a card
    with mana value 4 or greater. That player discards those cards.                     (Distended Mindbender)
    Target opponent exiles the top card of their library, a card at random from their graveyard and a card at
    random from their hand. You may cast a spell from among cards exiled this way without paying its mana cost.
                                                                                        (Crabomination)

The "that much" damage riders and Noble Purpose are statics in ``advanced_rules`` (``damage_link``,
``combat_gain``) applied by ``on_damage``, called from Game.deal_damage next to the Spirit Link hook.
"""
from __future__ import annotations

import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

KINDS = {"exile_three_zones", "detain", "attach_equipment", "counter_stack_ability"}


def _tap(m, **data):
    from .cards import Effect
    return Effect("tap", _NUM[m[1]], target="permanent", data=data)


def _detain(m):
    from .cards import Effect
    n = _NUM.get(m[1], 1) if m[1] else 1
    return Effect("detain", n, target="nonland_perm" if "nonland" in m[0] else "creature", filter="opp")


def _attach(m):
    from .cards import Effect
    return Effect("attach_equipment", 1, target="self" if m[2] == "~" else "creature_mine",
                  data={"all": m[1] in ("all", "any number of target")})


def _counter_ability(m):
    from .cards import Effect
    return Effect("counter_stack_ability", 1, target="none",
                  data={"activated": "activated" in m[1], "triggered": "triggered" in m[1]})


def _two_discards(m):
    return "TARGETDISCARD2 nonland 3 less. TARGETDISCARD3 card 4 greater."


def _discard_prev(m):
    from .cards import Effect
    mv = (int(m[2]), m[3])
    return Effect("discard_choice", 1, target="prev", filter="" if m[1] == "card" else m[1], data={"mv": mv})


def _three_zones(m):
    from .cards import Effect
    return Effect("exile_three_zones", 1, target="player")


SUBS = [
    (re.compile(r"tap up to (two|three|four|five) target permanents\. put a stun counter on each of them\.?", re.I),
     lambda m: "TAPSTUNEACH " + m[1] + "."),
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose from it an? nonland card with "
                r"mana value 3 or less and a card with mana value 4 or greater\. that player discards those cards\.?",
                re.I), _two_discards),
    (re.compile(r"target opponent exiles the top card of their library, a card at random from their graveyard, and a "
                r"card at random from their hand\. you may cast a spell from among cards exiled this way without "
                r"paying its mana cost\.?", re.I), lambda m: "EXILE3ZONES."),
]

EFFECT_PATTERNS = [
    (r"tap up to (two|three|four|five) target permanents", _tap),
    # Equipment is picked on resolution (the best one not already on the creature), noted as an approximation.
    (r"attach (any number of target|all|up to one target|target) equipment(?: you control)? to "
     r"(target creature you control|up to one target creature you control|~)", _attach),
    # The ability is picked on resolution: the newest matching one an opponent controls.
    (r"counter target (activated or triggered|activated|triggered) ability", _counter_ability),
    (r"detain (?:up to (two) )?target (?:creatures?|nonland permanents?) (?:an opponent controls|your opponents control)",
     _detain),
    (r"TAPSTUNEACH (two|three|four|five)",
     lambda m: _tap(m, stun_each=True)),
    (r"TARGETDISCARD3 (card|[\w, -]+?) (\d+) (less|greater)", _discard_prev),
    (r"EXILE3ZONES", _three_zones),
]

TRIGGERS: list = []


def parse_line(line: str, st) -> bool:
    rules = st.extra.setdefault("advanced_rules", {})
    m = re.fullmatch(r"~ has hexproof as long as it entered this turn\.", line)
    if m:
        rules["hexproof_entered"] = True
        return True
    m = re.fullmatch(r"Whenever enchanted creature is dealt damage, (its controller loses that much life|"
                     r"~ deals that much damage to that creature's controller)\.", line)
    if m:
        mode = "lose" if m[1].startswith("its") else "damage"
        rules["damage_link"] = rules.get("damage_link", ()) + (mode,)
        return True
    if line == "~ doesn't untap during your untap step if it has a depletion counter on it.":
        # Land Cap and friends: tapping puts a depletion counter on it, and the upkeep removes it after the untap step,
        # so it skips exactly one untap step, like the "slow" duals.
        st.extra["color_skips_untap"] = True
        st.approximations.append("the depletion counter is only added when its colored mana is needed")
        return True
    if line == "Whenever a creature you control deals combat damage, you gain that much life.":
        rules["combat_gain"] = True
        return True
    return False


def on_damage(game, source, target, amount: int, combat: bool):
    """Damage-driven statics, after the damage is dealt."""
    from .engine.state import Permanent
    if isinstance(target, Permanent):
        for aura in list(target.auras):
            if aura.abilities_suppressed:
                continue
            for mode in aura.card.advanced_rules.get("damage_link", ()):
                victim = target.controller
                if mode == "lose":
                    game.change_life(victim, -amount, f"{aura.card.name}: damage to {target.card.name}")
                else:
                    game.deal_damage(victim, amount, by=aura.controller, source=aura)
    if combat and isinstance(source, Permanent) and source.is_creature:
        for x in list(source.controller.battlefield):
            if x.card.advanced_rules.get("combat_gain") and not x.abilities_suppressed:
                game.change_life(source.controller, amount, f"{x.card.name}: combat damage")


def hexproof_entered(perm) -> bool:
    """Drownyard Behemoth: hexproof during the turn it entered."""
    game = getattr(perm.controller, "_game", None)
    return game is not None and perm.card.advanced_rules.get("hexproof_entered") and perm.entered_turn == game.turn


def detain(game, p, eff, target):
    chosen = [target] if target is not None else []
    from .engine.policy import perm_value
    more = sorted((x for x in game.legal_targets(p, eff) if x not in chosen and x.controller is game.opponent(p)),
                  key=perm_value, reverse=True)
    chosen += more[:eff.amount - len(chosen)]
    for perm in chosen:
        if hasattr(perm, "detained_by"):
            perm.detained_by = p
            game.log(f"detains {perm.card.name}", p)


def attach_equipment(game, p, eff, target, item):
    from .engine.state import Permanent
    if not isinstance(target, Permanent) or target not in p.battlefield or not target.is_creature:
        return
    pool = [x for x in p.battlefield if "Equipment" in x.card.subtypes and x.attached_to is not target and
            x is not target and (not x.is_creature or x.card.reconfigure)]
    from .engine.policy import perm_value
    pool.sort(key=perm_value, reverse=True)
    for eq in (pool if eff.data.get("all") else pool[:1]):
        eq.attached_to = target
        game.log(f"attaches {eq.card.name} to {target.card.name}", p)


def counter_stack_ability(game, p, eff):
    wanted = [k for k, on in (("ability", eff.data["activated"]), ("loyalty", eff.data["activated"]),
                              ("trigger", eff.data["triggered"])) if on]
    for it in reversed(game.stack):
        if it.is_spell or it.controller is p or it.kind not in wanted:
            continue
        game.stack.remove(it)
        game.log(f"counters {it.name}", p)
        return


def resolve(game, p, eff, target, item):
    if eff.kind == "counter_stack_ability":
        return counter_stack_ability(game, p, eff)
    if eff.kind == "attach_equipment":
        return attach_equipment(game, p, eff, target, item)
    if eff.kind == "detain":
        return detain(game, p, eff, target)
    if eff.kind != "exile_three_zones" or not hasattr(target, "library"):
        return
    from . import cast_triggers
    exiled = []
    zones = [(target.library, lambda z: z.pop() if z else None),
             (target.graveyard, lambda z: z.pop(game.rng.randrange(len(z))) if z else None),
             (target.hand, lambda z: z.pop(game.rng.randrange(len(z))) if z else None)]
    for zone, take in zones:
        card = take(zone)
        if card is not None:
            target.exile.append(card)
            exiled.append(card)
    game.log(f"exiles {[c.name for c in exiled]}", target)
    for card in sorted((c for c in exiled if not c.is_land), key=lambda c: c.cmc, reverse=True):
        target.exile.remove(card)
        p.exile.append(card)
        if cast_triggers.cast_exiled(game, p, card, "cascade"):
            break
        p.exile.remove(card)
        target.exile.append(card)
