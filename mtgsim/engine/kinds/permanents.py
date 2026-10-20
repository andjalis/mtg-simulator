"""Permanents: removal, bounce, tokens, transforming, control and zone swaps."""
from __future__ import annotations

import dataclasses

from ... import copies
from ...cards import CardDef, Effect, jace_token, make_token, role_token
from ..policy import choose_basic, perm_value
from ..state import Permanent, Player, is_basic_land
from . import NO_SBA, kind


@kind("destroy")
def destroy(game, p, eff, target, item, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        src = item.source if item is not None else None
        if eff.data.get("azog") and target is src:
            return NO_SBA
        ctl, power = target.controller, max(0, target.power)
        game.destroy(target, no_regen=eff.data.get("no_regen", False))
        if eff.data.get("azog"):
            if power:
                game.resolve(ctl, Effect("amass", power, data={"type": eff.data["azog"]}), None, item)
            if ctl is p:
                game.draw(p)


@kind("wrath")
def wrath(game, p, eff, opp, **_):
    for perm in p.creatures + opp.creatures:
        game.destroy(perm, no_regen=eff.data.get("no_regen", False))


@kind("wrath_pw")
def wrath_pw(game, p, eff, opp, **_):
    for perm in p.planeswalkers + opp.planeswalkers:
        game.destroy(perm, no_regen=eff.data.get("no_regen", False))


@kind("bounce")
def bounce(game, p, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        game.log(f"{target.card.name} returns to hand", p)
        game.leave_battlefield(target, "hand")


@kind("return_own")
def return_own(game, p, eff, item, **_):
    """Bounce lands, Storm Sculptor: return a land / creature you control. Tapped lands go first (a basic
    before a nonbasic), then the cheapest creature; the source itself only when nothing else is left."""
    src = item.source if item is not None else None
    land = eff.data["kind"] == "land"
    pool = [x for x in p.battlefield if (x.card.is_land if land else x.is_creature)]
    if not pool:
        return
    pick = min(pool, key=lambda x: (x is src, not x.tapped, not is_basic_land(x.card)) if land else
               (x is src, perm_value(x)))
    game.log(f"returns {pick.card.name} to hand", p)
    game.leave_battlefield(pick, "hand")


@kind("sac_own")
def sac_own(game, p, **_):
    """"Sacrifice a creature": p's least valuable one."""
    if p.creatures:
        game.sacrifice(min(p.creatures, key=perm_value))


@kind("tuck_top")
def tuck_top(game, p, target, **_):
    """Put target creature on top of its owner's library (a token just leaves)."""
    if isinstance(target, Permanent) and game.leave_battlefield(target, "graveyard") and not target.front.is_token:
        owner = target.owner
        if target.front in owner.graveyard:
            owner.graveyard.remove(target.front)
            owner.library.append(target.front)
            game.log(f"{target.card.name} goes on top of its owner's library", p)


@kind("regenerate")
def regenerate(game, p, eff, target, opp, **_):
    victims = (p.creatures if eff.target == "creatures_mine" else p.creatures + opp.creatures
               if eff.target == "each_creature" else [target])
    for perm in victims:
        if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
            perm.regeneration_shields += eff.amount


@kind("token")
def token(game, p, eff, target, item, **_):
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    n = None
    if eff.data.get("x"):
        n = (getattr(item.source, "entered_x", 0) if item.source is not None else getattr(item, "x", 0)) \
            if item is not None else 0
    game.create_token(who, eff, n)


@kind("copy_token")
def copy_token(game, p, **_):
    tokens = [x for x in p.creatures if x.card.is_token]
    if tokens:
        best = max(tokens, key=lambda t: t.power + t.toughness)
        game.enter_battlefield(p, best.card)
        game.log(f"copies {best.card.name}", p)


@kind("transform")
def transform(game, target, **_):
    if isinstance(target, Permanent):
        game.transform(target)


@kind("bounce_self")
def bounce_self(game, p, item, **_):
    src = item.source if item is not None else None
    if src is not None and src in src.controller.battlefield:
        game.log(f"{src.card.name} returns to hand", p)
        game.leave_battlefield(src, "hand")


@kind("role")
def role(game, p, eff, target, item, **_):
    host = target if isinstance(target, Permanent) else (item.source if item is not None else None)
    if isinstance(host, Permanent) and host in host.controller.battlefield and host.is_creature:
        for old in [a for a in host.auras if "Role" in a.card.subtypes and a.controller is p]:
            game.leave_battlefield(old, "graveyard")
        game._aura_host = host
        game.enter_battlefield(p, role_token(eff.data["role"]))
        game._aura_host = None


@kind("exile_instead")
def exile_instead(game, target, **_):
    if isinstance(target, Permanent):
        target.exile_turn = game.turn


@kind("empower")
def empower(game, p, eff, **_):
    amount = eff.amount
    cnt = eff.data.get("count")
    if cnt == "creatures":
        amount = len(p.creatures)
    elif cnt == "exiled":
        amount = getattr(game, "exiled_creatures", 0)
    elif cnt == "islands":
        amount = sum("Island" in x.card.subtypes for x in p.battlefield)
    eff = dataclasses.replace(eff, amount=amount)
    jace = next((x for x in p.battlefield if x.is_planeswalker and x.card.is_token and "Jace" in x.card.subtypes),
                None)
    if jace is not None:
        jace.counters["loyalty"] = jace.loyalty + eff.amount
    else:
        game.enter_battlefield(p, jace_token(eff.amount))
    game.log(f"empowers Jace by {eff.amount}", p)


@kind("cover_up")
def cover_up(game, p, opp, **_):
    if opp.graveyard:
        pick = max(opp.graveyard, key=lambda c: c.cmc)
        opp.graveyard.remove(pick)
        opp.exile.append(pick)
        from_hand = 0
        for zone in (opp.graveyard, opp.hand, opp.library):
            for c in [x for x in zone if x.name == pick.name]:
                zone.remove(c)
                opp.exile.append(c)
                if zone is opp.hand:
                    from_hand += 1
        opp.library.shuffle(game.rng)
        game.library_searched(opp)
        game.draw(opp, from_hand)
        game.log(f"exiles every {pick.name} of {opp}", p)


@kind("starcage")
def starcage(game, p, item, **_):
    src = item.source if item is not None else None
    if src is not None:
        exiled, src.exiled_cards = src.exiled_cards, []
        for card, owner in exiled:
            if card in owner.exile:
                owner.exile.remove(card)
                owner.graveyard.append(card)
        for _ in exiled:
            game.enter_battlefield(p, dataclasses.replace(make_token("Robot", 2, 2, artifact=True),
                                                          subtypes=frozenset({"Robot"})))
        if src in p.battlefield:
            game.sacrifice(src)


@kind("harness")
def harness(game, item, **_):
    src = item.source if item is not None else None
    if src is not None:
        src.harnessed = True


@kind("blink_own")
def blink_own(game, p, item, **_):
    src = item.source if item is not None else None
    cands = [x for x in p.battlefield if x is not src and not x.card.is_land and not x.card.is_token
             and (x.card.etb_effects or any(t.event == "etb" for t in x.card.triggers))]
    if cands:
        best = max(cands, key=perm_value)
        card = best.front
        if game.leave_battlefield(best, "exile"):
            p.exile.remove(card)
            game.enter_battlefield(p, card)


@kind("blink_end")
def blink_end(game, p, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        owner, card = target.controller, target.front
        if game.leave_battlefield(target, "exile"):
            owner.exile.remove(card)
            game.blinked.append((card, owner))


@kind("irencrag")
def irencrag(game, p, item, **_):
    src = item.source if item is not None else None
    if src is not None and src in p.battlefield and not src.card.name.startswith("Everflame"):
        src.card = dataclasses.replace(src.card, name="Everflame, Heroes' Legacy", produces=frozenset(),
                                       types=frozenset({"Artifact"}),
                                       subtypes=frozenset({"Equipment"}), equip_cost={"generic": 3},
                                       equip_bonus=(3, 3), triggers=[], activated=[])
        game.log("The Irencrag becomes Everflame", p)


@kind("threaten")
def threaten(game, p, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        victim, owner = target, target.controller
        owner.battlefield.remove(victim)
        victim.controller = p
        p.battlefield.append(victim)
        victim.tapped = False
        victim.sick = False
        game.stolen.append((victim, owner))
        game.log(f"gains control of {victim.card.name}", p)


@kind("mass_bounce")
def mass_bounce(game, p, eff, **_):
    keep = eff.data.get("except", "")
    only = eff.data.get("only")
    for v in [x for pl in game.players for x in pl.creatures if keep not in x.card.subtypes
              and (only != "attacking" or x in game.attackers)]:
        game.log(f"{v.card.name} returns to hand", p)
        game.leave_battlefield(v, "hand")


@kind("exile_all_creatures")
def exile_all_creatures(game, p, **_):
    victims = [x for pl in game.players for x in pl.creatures]
    for v in victims:
        game.leave_battlefield(v, "exile")
    game.exiled_creatures = len(victims)
    game.log(f"exiles {len(victims)} creatures", p)


@kind("discover_treasures")
def discover_treasures(game, p, **_):
    found = getattr(p, "discovered_cmc", None)
    if found is not None and found < 10:
        for _ in range(10 - found):
            perm = game.enter_battlefield(p, make_token("", 0, 0, (), None, "treasure", True))
            perm.tapped = True


@kind("land_swap")
def land_swap(game, p, eff, opp, **_):
    lands = [x for x in opp.battlefield if x.card.is_land and not is_basic_land(x.card) and game.targetable(x, p)]
    if lands:
        victim = max(lands, key=perm_value)
        game.destroy(victim)
        for who in ((opp, p) if eff.data.get("both") else (opp,)):
            land = choose_basic(game, who)
            if land is not None:
                who.library.remove(land)
                game.log(f"fetches {land.name}", who)
                perm = game.enter_battlefield(who, land)
                if not eff.data.get("both"):
                    perm.tapped = True
                    perm.counters["stun"] = 1
            who.library.shuffle(game.rng)
            game.library_searched(who)


@kind("amass")
def amass(game, p, eff, **_):
    kind = eff.data["type"]
    army = next((x for x in p.creatures if "Army" in x.card.subtypes), None)
    if army is None:
        game.enter_battlefield(p, dataclasses.replace(make_token(f"{kind} Army", 0, 0), etb_counters=eff.amount))
    else:
        if kind not in army.card.subtypes:
            army.card = dataclasses.replace(army.card, subtypes=army.card.subtypes | {kind})
        army.counters["+1/+1"] = army.p1 + eff.amount
    game.log(f"amasses {kind} {eff.amount}", p)


@kind("edict")
def edict(game, p, eff, opp, **_):
    victims = sorted(opp.creatures, key=perm_value)[:eff.amount]
    for v in victims:
        if eff.data.get("exile"):
            game.leave_battlefield(v, "exile")
            game.log(f"{opp} exiles {v.card.name}", p)
        else:
            game.sacrifice(v)


@kind("endure")
def endure(game, p, eff, target, item, **_):
    src = target if isinstance(target, Permanent) else (item.source if item is not None else None)
    if src is not None and src in src.controller.battlefield and src.is_creature:
        src.counters["+1/+1"] = src.p1 + eff.amount
        game.log(f"{src.card.name} endures {eff.amount} (counters)", p)
    else:
        game.create_token(p, Effect("token", 1, data={"name": "Spirit", "power": eff.amount,
                                                      "toughness": eff.amount, "keywords": frozenset()}))


@kind("manifest_dread")
def manifest_dread(game, p, **_):
    top = [p.library.pop() for _ in range(min(2, len(p.library)))]
    if top:
        top.sort(key=lambda c: copies.score(c))
        keep, rest = top[0], top[1:]       # manifest the cheaper card, the other goes to the graveyard
        game.enter_battlefield(p, CardDef(name="Manifest", mana_cost={"generic": 0}, cmc=0,
                                                 types=frozenset({"Creature"}), power=2, toughness=2,
                                                 is_token=False), physical_card=keep)
        for c in rest:
            p.graveyard.append(c)
        game.log("manifests dread", p)


@kind("oring")
def oring(game, target, item, **_):
    src = item.source if item is not None else None
    if isinstance(target, Permanent) and isinstance(src, Permanent) and src in src.controller.battlefield:
        game.exile_until_leaves(src, [target])


@kind("oring_all")
def oring_all(game, eff, item, **_):
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in src.controller.battlefield:
        game.exile_until_leaves(src, [x for pl in game.players for x in pl.battlefield if x is not src and
                                      (x.is_creature or x.card.is_artifact) and x.card.cmc <= eff.amount])


@kind("token_copy")
def token_copy(game, p, eff, **_):
    game.enter_battlefield(p, eff.data["card"])
    game.log(f"creates {eff.data['card'].name}", p)


@kind("sacrifice_self")
def sacrifice_self(game, p, eff, target, **_):
    if isinstance(target, Permanent) and target.controller is p and target in p.battlefield:
        game.sacrifice(target)


@kind("decayed_delay")
def decayed_delay(game, p, target, **_):
    if isinstance(target, Permanent):
        game.delayed_end_combat.append((p, target))
