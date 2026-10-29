"""Cards in hand and library: draw, discard, scry, surveil, dig, mill, tutor, explore, connive."""
from __future__ import annotations

from ... import learning, milling
from ...cards import make_token
from ..policy import choose_basic, choose_tutor, perm_value
from ..state import Permanent, Player, card_matches, is_basic_land
from . import NO_SBA, kind


@kind("draw")
def draw(game, p, eff, opp, **_):
    who = opp if eff.target == "each_opponent" else p
    if eff.data.get("control_type") and not any(eff.data["control_type"] in x.card.types for x in p.battlefield):
        return
    n = eff.amount
    if eff.data.get("x_count"):
        n = sum(card_matches(x.card, "a " + eff.data["x_count"]) for x in p.battlefield)
    game.draw(who, n)


@kind("draw_delayed")
def draw_delayed(game, p, eff, item, source, **_):
    src = item.source if item is not None else None
    game.delayed_upkeep.append((p, eff.amount, src, f"{source}: delayed draw", eff.data["upkeep"]))


@kind("tuck_self")
def tuck_self(game, p, eff, item, **_):
    src = item.source if item else None
    if src is not None and src in p.battlefield and game.leave_battlefield(src, "graveyard"):
        if not src.front.is_token:
            p.graveyard.remove(src.front)
            p.library.insert(max(0, len(p.library) - (eff.amount - 1)), src.front)


@kind("draw_up_to")
def draw_up_to(game, p, eff, **_):
    game.draw(p, max(0, eff.amount - len(p.hand)))


@kind("scry")
def scry(game, p, eff, **_):
    game.scry(p, eff.amount)
    game.fire(p, "scry_surveil")


@kind("surveil")
def surveil(game, p, eff, item, **_):
    before = {c.physical_id for c in p.graveyard}
    game.scry(p, eff.amount, to_graveyard=True)
    if item is not None:
        item.surveilled = {p: [p.graveyard.reference(c) for c in p.graveyard if c.physical_id not in before]}
    game.fire(p, "scry_surveil")


@kind("dig")
def dig(game, p, eff, item, **_):
    n = item.mana_spent if eff.data.get("x_mana") and item is not None and item.mana_spent else eff.amount
    if eff.data.get("x_lands"):
        n = sum(x.card.is_land for x in p.battlefield)
    if eff.data.get("x_count"):
        n = sum(card_matches(x.card, "a " + eff.data["x_count"]) for x in p.battlefield)
    keep = eff.amount2
    if eff.data.get("instead_two") and any(c.is_instant for c in p.graveyard) and \
            any(c.is_sorcery for c in p.graveyard):
        keep = 2
    game.dig(p, n, keep, eff.data.get("filter"))


@kind("dig_put")
def dig_put(game, p, eff, **_):
    game.dig_put(p, eff.amount, eff.amount2, eff.data.get("count", 1), eff.data.get("noncreature", False))


@kind("discard")
def discard(game, p, eff, target, **_):
    who = target if isinstance(target, Player) else p
    basics = [c for c in who.hand if is_basic_land(c)] if eff.data.get("unless") == "basic_land" else []
    if basics:
        # One basic land instead of the larger discard (Thirst for Discovery); for an
        # AI that is nearly always the cheaper option.
        card = max(basics, key=lambda c: sum(c.name == x.name for x in who.hand))
        game.discard_card(who, card)
        game.log(f"discards {card.name}", who)
    who.discarded_last = []
    for _ in range(0 if basics else min(eff.amount, len(who.hand))):
        card = game.rng.choice(who.hand) if eff.data.get("random") else who.ai.choose_discard(game, who)
        game.discard_card(who, card)
        who.discarded_last.append(card)
        game.log(f"discards {card.name}", who)


@kind("discard_choice")
def discard_choice(game, p, eff, target, **_):
    if isinstance(target, Player):
        card = game.hook(p, "choose_discard_from")(game, p, target)
        if eff.filter == "noncreature":    # Duress: a noncreature, nonland card
            legal = [c for c in target.hand if not c.is_land and not c.is_creature]
            if card not in legal:
                card = max(legal, key=lambda c: c.cmc, default=None)
        if card is not None:
            game.discard_card(target, card)
            game.log(f"makes {target} discard {card.name}", p)


@kind("learn")
def learn(game, p, **_):
    learning.resolve(game, p)


@kind("rummage")
def rummage(game, p, eff, **_):
    cards = game.hook(p, "choose_rummage")(game, p, eff.amount)
    for c in cards:
        p.hand.remove(c)
        p.graveyard.append(c)
    game.draw(p, len(cards))


@kind("tutor")
def tutor(game, p, eff, **_):
    cands = [c for c in p.library if card_matches(c, eff.data["what"])]
    if cands:
        card = choose_tutor(game, p, cands)
        p.library.remove(card)
        p.hand.append(card)
        game.log(f"searches for {card.name}", p)
    p.library.shuffle(game.rng)


@kind("mill")
def mill(game, p, eff, target, item, opp, **_):
    players = game.players if eff.target == "each_player" else [opp] if eff.target == "each_opponent" else \
        [target] if isinstance(target, Player) else [p]
    for who in players:
        who.milled_last = []
        for _ in range(min(eff.amount, len(who.library))):
            who.milled_last.append(who.library.pop())
            who.graveyard.append(who.milled_last[-1])
        if item is not None:
            if not hasattr(item, "milled"):
                item.milled = {}
            item.milled[who] = list(who.milled_last)


@kind("exile_top")
def exile_top(game, p, eff, **_):
    p.impulse_new = []
    for _ in range(min(eff.amount, len(p.library))):
        c = p.library.pop()
        p.exile.append(c)
        p.impulse_new.append(c)
    game.log(f"exiles the top {len(p.impulse_new)} card(s) of their library", p)


@kind("may_play_exiled")
def may_play_exiled(game, p, eff, **_):
    new = p.impulse_new
    if eff.data.get("one") and new:     # "Choose one of them. Until end of turn, you may play that card."
        from ...ai import card_value
        new = [max(new, key=card_value)]
    p.impulse += [(c, game.turn + eff.amount) for c in new]
    p.impulse_new = []


@kind("mill_pick")
def mill_pick(game, p, eff, item, **_):
    milling.resolve_pick(game, p, eff, item)


@kind("mill_repeat")
def mill_repeat(game, p, eff, item, **_):
    milling.resolve_repeat(game, p, eff, item)


@kind("discard_tutor")
def discard_tutor(game, p, eff, **_):
    cands = [c for c in p.library if card_matches(c, eff.data["desc"])]
    if p.hand and cands:
        card = p.ai.choose_discard(game, p)
        game.discard_card(p, card)
        found = choose_tutor(game, p, cands)
        p.library.remove(found)
        p.hand.append(found)
        p.library.shuffle(game.rng)
        game.log(f"discards {card.name} and searches for {found.name}", p)


@kind("stun_discarded")
def stun_discarded(game, p, opp, **_):
    n = sum(not c.is_land for c in p.discarded_last)
    for _ in range(n):
        tgt = max((c for c in opp.creatures if not c.counters.get("stun") and game.targetable(c, p)),
                  key=perm_value, default=None)
        if tgt is None:
            break
        tgt.tapped = True
        tgt.counters["stun"] = 1
        game.log(f"taps and stuns {tgt.card.name}", p)


@kind("shuffle_away")
def shuffle_away(game, p, target, item, **_):
    for perm in (target, item.source if item else None):
        if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
            owner = perm.controller
            if game.leave_battlefield(perm, "graveyard") and not perm.front.is_token:
                owner.graveyard.remove(perm.front)
                owner.library.append(perm.front)
                owner.library.shuffle(game.rng)
            game.log(f"shuffles {perm.card.name} into its owner's library", p)


@kind("connive")
def connive(game, target, item, **_):
    who = target if isinstance(target, Permanent) else (item.source if item is not None else None)
    if isinstance(who, Permanent) and who in who.controller.battlefield:
        ctl = who.controller
        game.draw(ctl)
        if ctl.hand:
            card = ctl.ai.choose_discard(game, ctl)
            game.discard_card(ctl, card)
            game.log(f"{who.card.name} connives, discarding {card.name}", ctl)
            if not card.is_land:
                who.counters["+1/+1"] = who.p1 + 1


@kind("sac_draw_treasure")
def sac_draw_treasure(game, p, item, **_):
    src = item.source if item is not None else None
    spare = [x for x in p.battlefield if x is not src and (x.card.is_artifact or x.is_creature)
             and (x.card.is_token or x.card.token_kind) and not (x.card.token_kind == "treasure" and False)]
    if spare:
        victim = min(spare, key=perm_value)
        game.sacrifice(victim)
        game.draw(p)
        game.enter_battlefield(p, make_token("", 0, 0, (), None, "treasure", True))


@kind("bay_search")
def bay_search(game, p, item, **_):
    src = item.source if item is not None else None
    want = getattr(src, "last_sacrificed_cmc", None)
    if want is not None:
        cands = [c for c in p.library if c.is_artifact and c.cmc == want + 1]
        if cands:
            card = max(cands, key=lambda c: c.cmc)
            p.library.remove(card)
            game.enter_battlefield(p, card)
            game.log(f"fetches {card.name}", p)
        p.library.shuffle(game.rng)


@kind("draw_each")
def draw_each(game, eff, **_):
    for pl in game.players:
        game.draw(pl, eff.amount)


@kind("opp_exile_hand")
def opp_exile_hand(game, p, opp, **_):
    if opp.hand:
        card = opp.ai.choose_discard(game, opp)
        opp.hand.remove(card)
        opp.exile.append(card)
        game.log(f"{opp} exiles {card.name} from hand", p)


@kind("opt_cost_draw")
def opt_cost_draw(game, p, eff, item, k, **_):
    src = item.source if item is not None else None
    cost = eff.data["cost"]
    paid = False
    if cost in ("discard", "either") and p.hand:
        card = p.ai.choose_discard(game, p)
        if cost == "discard" or (card.is_land and sum(x.card.is_land for x in p.battlefield) >= 5):
            game.discard_card(p, card)
            paid = True
    if not paid and cost != "discard":
        kinds = ("artifact",) if cost == "either" else tuple(cost.split(":", 1)[1].split("|"))
        spare = [x for x in p.battlefield
                 if not (cost.startswith("sacother") and x is src)
                 and any(card_matches(x.card, "a " + k) for k in kinds)
                 and (x.card.is_token or perm_value(x) <= 2)]
        if spare:
            game.sacrifice(min(spare, key=perm_value))
            paid = True
        elif cost == "either" and p.hand:
            game.discard_card(p, p.ai.choose_discard(game, p))
            paid = True
    if paid:
        game.draw(p, eff.amount)


@kind("wheel_self")
def wheel_self(game, p, **_):
    for c in list(p.hand):
        game.discard_card(p, c)
    game.draw(p, 2)


@kind("reveal_land")
def reveal_land(game, p, opp, **_):
    if opp.library and opp.library[-1].is_land:
        opp.hand.append(opp.library.pop())
        game.log(f"{opp} puts a revealed land into their hand", p)


@kind("fetch_basic")
def fetch_basic(game, p, eff, target, item, **_):
    if eff.data.get("sacrifice"):
        if item is None or item.source not in p.battlefield:
            return NO_SBA
        game.sacrifice(item.source)
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    land = choose_basic(game, who)
    if land is not None:
        who.library.remove(land)
        game.log(f"fetches {land.name}", who)
        perm = game.enter_battlefield(who, land)
        lands = sum(x.card.is_land for x in who.battlefield)
        perm.tapped = not (eff.data.get("untap4") and lands >= 4)
    who.library.shuffle(game.rng)


@kind("explore")
def explore(game, p, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield and p.library:
        top = p.library[-1]
        if top.is_land:
            p.hand.append(p.library.pop())
        else:
            target.counters["+1/+1"] = target.p1 + 1
            if game.hook(p, "scry")(game, p, [top]):
                p.graveyard.append(p.library.pop())
        game.log(f"{target.card.name} explores", p)
