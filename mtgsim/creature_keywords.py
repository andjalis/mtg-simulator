"""Keyword abilities of creatures and Equipment that are a trigger or an "enters with" rule.

    Echo {2}{G}     Unleash     Evolve     Renown N     Mentor     Battle cry     Riot     Bloodthirst N
    Fabricate N     Living weapon     Heroic — Whenever you cast a spell that targets ~, ...
    ~ has first strike as long as it's attacking.     Whenever ~ deals damage, you gain that much life.
    Cumulative upkeep {1}     Vanishing N     Fading N     Modular N     Soulshift N     Annihilator N
    Rampage N     Backup N     Dash {2}{R}     Unearth {1}{R}     Madness {1}{R}
    At the beginning of your upkeep, sacrifice ~ unless you pay {G}{G}.

``parse_line`` turns a keyword line into CardDef fields and triggers. The "enters with" ones (unleash, riot,
bloodthirst) are applied in Game.enter_battlefield; echo is checked at the beginning of its controller's
upkeep. Choices: unleash takes the counter unless its controller is low on life against a real attack, riot takes
haste when the creature can attack this turn and nothing untapped would block and kill it, fabricate puts the
counters on an evasive creature and makes Servos otherwise, backup goes on the best other creature (only its keywords are
granted). Modular, annihilator and soulshift choose for the AI without targeting. Dash and unearth are
alternative costs (unearth from the graveyard: a spell, not an ability), madness lets the card be cast from the
graveyard for its madness cost during the turn it was discarded. Not modelled: echo for permanents that
changed control, cumulative upkeep costs other than mana. Extort's hybrid {W/B} is paid as a color of its source,
and devour eats only tokens.
"""
from __future__ import annotations

import re

KINDS = {"extort", "evolve", "renown", "mentor", "battle_cry", "fabricate", "living_weapon", "echo", "pay_or_sac",
         "cumulative_upkeep", "vanishing", "fading", "modular", "soulshift", "annihilator", "rampage", "backup"}


def _effect(kind, amount=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _trigger(event, effects, **kw):
    from .cards import Trigger
    return Trigger(event, effects, **kw)


def parse_line(line: str, st) -> bool:
    """Consume a keyword line of a face (st: its _FaceState); True if understood."""
    from .cards.model import parse_mana_cost
    extra, triggers, keywords = st.extra, st.triggers, st.keywords
    m = re.fullmatch(r"Echo ((?:\{[^}]+\})+)", line)
    if m:
        extra["echo"] = parse_mana_cost(m[1])
        return True
    m = re.fullmatch(r"Cumulative upkeep ((?:\{[^}]+\})+)", line)
    if m:
        triggers.append(_trigger("upkeep", [_effect("cumulative_upkeep", data={"cost": parse_mana_cost(m[1])})]))
        return True
    m = re.fullmatch(r"(Dash|Unearth|Madness) ((?:\{[^}]+\})+)", line)
    if m:
        from .cards.model import AltCost
        kind = m[1].lower()
        st.alt_costs.append(
            AltCost("mayhem" if kind == "madness" else kind, parse_mana_cost(m[2]),
                    zone="hand" if kind == "dash" else "graveyard"))
        if kind != "dash":
            st.approximations.append(
                "unearth is cast like a spell" if kind == "unearth" else "madness: cast from the graveyard this turn")
        return True
    m = re.fullmatch(r"Afflict (\d+)", line)
    if m:
        triggers.append(_trigger("becomes_blocked", [_effect("drain", int(m[1]), target="each_opponent")]))
        return True
    m = re.fullmatch(r"(Renown|Bloodthirst|Fabricate|Vanishing|Fading|Modular|Soulshift|Annihilator|Rampage|Backup) (\d+)",
                     line)
    if m:
        n = int(m[2])
        if m[1] in ("Vanishing", "Fading", "Modular"):
            extra[m[1].lower()] = n
            if m[1] != "Modular":
                triggers.append(_trigger("upkeep", [_effect(m[1].lower())]))
            else:
                triggers.append(_trigger("dies", [_effect("modular")]))
        elif m[1] == "Soulshift":
            triggers.append(_trigger("dies", [_effect("soulshift", n)]))
        elif m[1] == "Annihilator":
            triggers.append(_trigger("attacks", [_effect("annihilator", n)]))
        elif m[1] == "Rampage":
            triggers.append(_trigger("becomes_blocked", [_effect("rampage", n)]))
        elif m[1] == "Backup":
            triggers.append(_trigger("etb", [_effect("backup", n)]))
            st.approximations.append("backup grants only keyword abilities")
        elif m[1] == "Renown":
            triggers.append(_trigger("combat_damage_player", [_effect("renown", n)]))
        elif m[1] == "Fabricate":
            triggers.append(_trigger("etb", [_effect("fabricate", n)]))
        else:
            extra["bloodthirst"] = n
        return True
    if line in ("Unleash", "Riot"):
        extra[line.lower()] = True
        return True
    m = re.fullmatch(r"Afterlife (\d+)", line)
    if m:
        from .cards.patterns import _token
        triggers.append(_trigger("dies", [_token(m[1], 1, 1, "white and black Spirit", "flying")]))
        return True
    if line == "Ingest":
        triggers.append(_trigger("combat_damage_player", [_effect("exile_top_of", target="that_player")]))
        return True
    m = re.fullmatch(r"Devour (\d+)", line)
    if m:
        extra["devour"] = int(m[1])
        return True
    if line == "Extort":
        triggers.append(_trigger("cast_spell", [_effect("extort")]))
        return True
    if line == "Myriad":
        return True             # only copies for opponents other than the defending player: none with two players
    if line == "Evolve":
        triggers.append(_trigger("other_creature_enters", [_effect("evolve")], filter="evolve"))
        return True
    if line == "Mentor":
        triggers.append(_trigger("attacks", [_effect("mentor")]))
        return True
    if line == "Battle cry":
        triggers.append(_trigger("attacks", [_effect("battle_cry")]))
        return True
    if line == "Living weapon":
        triggers.append(_trigger("etb", [_effect("living_weapon")]))
        return True
    m = re.fullmatch(r"~ has (first strike|flying|trample|lifelink|deathtouch|menace|vigilance|double strike) as "
                     r"long as it's attacking\.", line)
    if m:
        extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1], "attacking"),)
        return True
    if line == "Whenever ~ deals damage, you gain that much life.":
        keywords.add("lifelink")
        return True
    return False


def enters(game, p, perm):
    """The "enters with" choices and rules, as perm enters the battlefield."""
    c = perm.card
    if c.devour:                           # devour the tokens (the AI keeps its real creatures)
        eaten = [x for x in p.creatures if x is not perm and x.card.is_token]
        for x in eaten:
            game.sacrifice(x)
        if eaten:
            perm.counters["+1/+1"] = perm.p1 + c.devour * len(eaten)
    if c.vanishing:
        perm.counters["time"] = perm.counters.get("time", 0) + c.vanishing
    if c.fading:
        perm.counters["fade"] = perm.counters.get("fade", 0) + c.fading
    if c.modular:
        perm.counters["+1/+1"] = perm.p1 + c.modular
    if c.bloodthirst and game.opponent(p).lost_life_turn:
        perm.counters["+1/+1"] = perm.p1 + c.bloodthirst
    opp = game.opponent(p)
    if c.unleash:      # the counter, unless it's needed as a blocker: low on life against a real attack
        if not (p.life <= 8 and sum(x.power for x in opp.creatures) * 2 >= p.life):
            perm.counters["+1/+1"] = perm.p1 + 1
    if c.riot:         # haste when it can attack this turn and nothing untapped would block and kill it
        can_attack = p is game.active and game.step in ("main1", "untap", "upkeep", "draw")
        walls = [x for x in opp.creatures if not x.tapped and x.power >= perm.toughness]
        if can_attack and not walls:
            perm.perm_kw.add("haste")
        else:
            perm.counters["+1/+1"] = perm.p1 + 1


def upkeep(game, p):
    """Echo: at the beginning of your upkeep, pay the echo cost of what came under your control since your last one."""
    for perm in p.battlefield:
        if perm.card.echo and not getattr(perm, "echo_done", False):
            perm.echo_done = True
            game.queue_trigger(p, [_effect("echo")], perm, f"{perm.card.name}: echo")


def resolve(game, p, eff, target, item):
    from .engine import Permanent
    src = item.source if item is not None else None
    k = eff.kind
    if k in ("echo", "pay_or_sac", "cumulative_upkeep"):
        if isinstance(src, Permanent) and src in p.battlefield:
            if k == "echo":
                cost = src.card.echo
            elif k == "pay_or_sac":
                cost = eff.data["cost"]
            else:
                src.counters["age"] = src.counters.get("age", 0) + 1
                cost = {c: n * src.counters["age"] for c, n in eff.data["cost"].items()}
            if game.can_pay(p, cost) and game.hook(p, "pay_optional")(game, p, cost, k):
                game.pay(p, cost)
            else:
                game.sacrifice(src)
        return
    if k == "modular":                       # src died: its last known +1/+1 counters
        from .engine import perm_value
        hosts = [x for x in p.creatures if x.card.is_artifact and x is not src]
        if hosts and src.p1:
            best = max(hosts, key=perm_value)
            best.counters["+1/+1"] = best.p1 + src.p1
        return
    if k == "soulshift":
        spirits = [c for c in p.graveyard if "Spirit" in c.subtypes and c.cmc <= eff.amount and c is not getattr(src, "front", None)]
        if spirits:
            card = max(spirits, key=lambda c: c.cmc)
            p.graveyard.remove(card)
            p.hand.append(card)
            game.log(f"returns {card.name} to hand (soulshift)", p)
        return
    if k == "annihilator":
        from .engine import perm_value
        opp = game.opponent(p)
        for victim in sorted(opp.battlefield, key=perm_value)[:eff.amount]:
            game.sacrifice(victim)
        return
    if not isinstance(src, Permanent) or src not in src.controller.battlefield:
        return
    if k == "extort":                      # pay {W/B} (as one of the source's colors): drain 1
        color = next((c for c in ("W", "B") if c in src.card.colors), "B")
        cost = {"generic": 0, color: 1}
        if game.can_pay(p, cost) and game.hook(p, "pay_optional")(game, p, cost, "extort"):
            game.pay(p, cost)
            game.change_life(game.opponent(p), -1, f"{src.card.name}: extort")
            game.change_life(p, 1, f"{src.card.name}: extort")
        return
    if k == "vanishing":
        if src.counters.get("time"):
            src.counters["time"] -= 1
            if not src.counters["time"]:
                game.sacrifice(src)
    elif k == "fading":
        if src.counters.get("fade"):
            src.counters["fade"] -= 1
        else:
            game.sacrifice(src)
    elif k == "rampage":
        extra = max(0, len(game.blocks.get(src, ())) - 1) * eff.amount
        src.pump_p += extra
        src.pump_t += extra
    elif k == "backup":
        from .engine import perm_value
        others = [x for x in p.creatures if x is not src]
        pick = max(others, key=perm_value) if others else src
        pick.counters["+1/+1"] = pick.p1 + eff.amount
        if pick is not src:
            pick.temp_kw |= set(src.card.keywords)
    elif k == "evolve":
        new = item.context
        if isinstance(new, Permanent) and (new.power > src.power or new.toughness > src.toughness):
            src.counters["+1/+1"] = src.p1 + 1
    elif k == "renown":
        if not getattr(src, "renowned", False):
            src.counters["+1/+1"] = src.p1 + eff.amount
            src.renowned = True
    elif k == "fabricate":             # counters on an evasive creature, else 1/1 Servos
        if any(src.has(kw) for kw in ("flying", "trample", "menace", "unblockable", "shadow")):
            src.counters["+1/+1"] = src.p1 + eff.amount
        else:
            from .cards import make_token
            for _ in range(eff.amount):
                game.enter_battlefield(p, make_token("Servo", 1, 1, artifact=True))
    elif k == "mentor":
        from .engine import perm_value
        weaker = [a for a in game.attackers if a is not src and a.controller is p and a.power < src.power]
        if weaker:
            pick = max(weaker, key=perm_value)
            pick.counters["+1/+1"] = pick.p1 + 1
    elif k == "battle_cry":
        for a in game.attackers:
            if a is not src and a.controller is p:
                a.pump_p += 1
    elif k == "living_weapon":
        from .cards import make_token
        game._equip_on_enter = src         # attached before the 0/0 Germ would die
        game.enter_battlefield(p, make_token("Phyrexian Germ", 0, 0, colors=frozenset({"B"})))
        game.log(f"{src.card.name} is attached to a Germ token", p)
