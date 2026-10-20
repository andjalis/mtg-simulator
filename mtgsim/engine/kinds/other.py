"""Other effect kinds: the stack, mana, costs and one-off mechanics."""
from __future__ import annotations

import dataclasses

from ...cards import Activated, make_token
from ..policy import choose_earthbend
from ..state import FIREBEND_MANA, Permanent, StackItem, pool_mana
from . import kind


@kind("airbend")
def airbend(game, p, target, **_):
    """Exile a permanent; its owner may cast it for {2} for as long as it stays exiled."""
    if isinstance(target, Permanent) and target in target.controller.battlefield and \
            game.leave_battlefield(target, "exile") and not target.front.is_token:
        owner = target.owner
        owner.exile.remove(target.front)
        owner.airbent.append(target.front)
        game.log(f"airbends {target.card.name}", p)


@kind("emblem")
def emblem(game, p, eff, **_):
    p.emblems.append((eff.data["subtype"], eff.amount, eff.amount2))
    game.log(f"gets an emblem: {eff.data['subtype']}s get +{eff.amount}/+{eff.amount2}", p)


@kind("counter_ability")
def counter_ability(game, p, item, **_):
    """Counter the newest activated or triggered ability an opponent controls; if its source is an
    artifact, creature or planeswalker that stays out, it loses all abilities while this does."""
    me = item.source if item is not None else None
    for it in reversed(game.stack):
        if it is item or it.is_spell or it.controller is p:
            continue
        game.stack.remove(it)
        game.log(f"counters {it.name}", p)
        src = it.source
        if isinstance(src, Permanent) and src in src.controller.battlefield and me is not None and \
                (src.card.is_artifact or src.is_creature or src.is_planeswalker):
            src.silenced_by = me
        return


@kind("gy_type_spree")
def gy_type_spree(game, p, eff, **_):
    """Uldaros Theorix: exile the best nonland card of each type from the graveyard, then cast free spells among
    them with total mana value <= the limit. Approximation: the cards themselves are cast, not token copies."""
    best = {}
    for c in p.graveyard:
        if c.is_land:
            continue
        for t in ("Artifact", "Creature", "Enchantment", "Instant", "Planeswalker", "Sorcery", "Battle"):
            if t in c.types and (t not in best or c.cmc > best[t].cmc):
                best[t] = c
    chosen = list(dict.fromkeys(best.values()))
    for c in chosen:
        game.move_card(c, p.graveyard, p.exile, reason="exile")
    picked, total = [], 0
    for c in sorted(chosen, key=lambda c: -c.cmc):
        if total + c.cmc <= eff.amount:
            picked.append(c)
            total += c.cmc
    for c in picked:
        game.cast_free(p, c)
    game.log(f"exiles {len(chosen)} cards and casts {len(picked)} free", p)


@kind("flip_from_gy")
def flip_from_gy(game, item, **_):
    if item is not None:
        item.flip_gy = True


@kind("reveal_top_to_hand")
def reveal_top_to_hand(game, p, eff, **_):
    if not p.library:
        return
    top = p.library[-1]
    what = eff.data["what"]
    ok = top.is_land if what == "land" else top.is_creature if what == "creature" \
        else not ({"Instant", "Sorcery"} & set(top.types))
    game.log(f"reveals {top.name}", p)
    if ok:
        p.hand.append(p.library.pop())


@kind("craft")
def craft(game, p, item, **_):
    card = item.source.front if item and item.source else None
    if card is not None and card in p.exile and card.back is not None:
        p.exile.remove(card)
        game.enter_battlefield(p, card.back, physical_card=card)
        game.log(f"crafts {card.back.name}", p)


@kind("counter", "bounce_spell")
def counter(game, p, eff, target, item, **_):
    if eff.data.get("tw") and getattr(item, "teamwork", False):
        eff = dataclasses.replace(eff, amount=eff.data["tw"])
    game.counter(p, eff, target)


@kind("add_mana")
def add_mana(game, p, eff, **_):
    for color in eff.data["colors"]:
        p.pool.append(Permanent(pool_mana(color), p))
    game.log(f"adds {''.join(eff.data['colors'])}", p)


@kind("firebend")
def firebend(game, p, eff, item, **_):
    src = item.source if item is not None else None
    n = eff.amount
    if eff.data.get("x") == "power" and isinstance(src, Permanent):
        n = max(0, src.power)
    elif eff.data.get("x") == "creatures":
        n = len(p.creatures)
    for _ in range(n):
        mana = Permanent(FIREBEND_MANA, p)
        p.pool.append(mana)
    game.log(f"adds {n} red mana (firebending)", p)


@kind("pay_gate")
def pay_gate(game, p, eff, item, **_):
    if item is not None:
        item.gate_paid = False
        if "gate" in eff.data:
            item.gate_paid = game.pay_gate_cost(p, eff.data["gate"], item)
        elif game.can_pay(p, eff.data["cost"]) and game.hook(p, "pay_optional")(game, p, eff.data["cost"], "gate"):
            game.pay(p, eff.data["cost"])
            item.gate_paid = True


@kind("job_select")
def job_select(game, p, item, **_):
    src = item.source if item is not None else None
    hero = game.enter_battlefield(p, dataclasses.replace(make_token("Hero", 1, 1), subtypes=frozenset({"Hero"})))
    if src is not None and src in p.battlefield and src.card.equip_cost is not None:
        src.attached_to = hero
        game.log(f"{src.card.name} attaches to the Hero", p)


@kind("discover")
def discover(game, p, eff, target, **_):
    skipped = []
    found = None
    limit = eff.amount
    if eff.data.get("x_of"):
        limit = target.card.cmc if isinstance(target, StackItem) and target.card else 0
    p.discovered_cmc = None
    while p.library:
        c = p.library.pop()
        p.exile.append(c)
        if not c.is_land and c.cmc <= limit:
            found = c
            break
        skipped.append(c)
    if found is not None:
        p.discovered_cmc = found.cmc
        game.log(f"discovers {found.name}", p)
        if not game.cast_free(p, found):
            game.log(f"puts {found.name} into their hand", p)
    game.rng.shuffle(skipped)
    for c in skipped:
        p.exile.remove(c)
    p.library[0:0] = skipped


@kind("earthbend")
def earthbend(game, p, eff, **_):
    land = choose_earthbend(game, p)
    if land is not None:
        # Target land you control becomes a 0/0 creature with haste that's still a land.
        land.animated = Activated("animate", {}, 0, 0, frozenset({"haste"}), text="earthbend")
        land.counters["+1/+1"] = land.p1 + eff.amount
        game.log(f"earthbends {land.card.name} ({eff.amount})", p)


@kind("end_of_combat")
def end_of_combat(game, p, item, prev, eff, **_):
    """A delayed "... at end of combat": the effects resolve then, with "that creature" kept."""
    game.end_combat_effects.append((p, eff.data["effects"], item.source if item is not None else None, prev))
