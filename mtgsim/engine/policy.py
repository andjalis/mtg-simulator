"""Default decision policies.

Decisions the heuristic AI doesn't make are taken by these functions; an AI can
override each one by defining the hook of the same name (see README and DEFAULTS)."""
from __future__ import annotations

from typing import TYPE_CHECKING
from .. import copies, learning, proliferate, regeneration, removal
from ..cards import COLORS, CardDef, Effect
from .. import modal
from .mana import add_costs, payable
from .state import Permanent, StackItem, TARGETED, _gy_desc, is_basic_land

if TYPE_CHECKING:
    from .game import Game
    from .state import Player


def perm_value(x: Permanent) -> float:
    if x.is_planeswalker and not x.is_creature:
        return 4 + x.loyalty
    if x.card.token_kind:
        return 0.5
    return x.card.cmc + (x.power + x.toughness) / 2 + 0.5 * len(x.card.keywords)


def _threat(game: Game, me: Player, item: StackItem) -> float:
    """How much I want to counter an opponent's stack item."""
    score = item.card.cmc if item.card else 0
    for eff, tgt in zip(item.effects, item.targets):
        if tgt is me or (isinstance(tgt, Permanent) and tgt.controller is me):
            score += 2
        if isinstance(tgt, StackItem) and tgt.controller is me:
            score += 2 + (tgt.card.cmc if tgt.card else 0)
        if eff.kind == "damage" and tgt is me and eff.amount >= me.life:
            score += 100
        if eff.kind == "wrath" and me.creatures:
            score += 2 * len(me.creatures)
    if item.card and (item.card.is_creature or item.card.is_planeswalker):
        score += ((item.card.power or 0) + (item.card.toughness or 0)) / 4 + item.card.loyalty / 2
    return score


def default_choose_target(game: Game, me: Player, eff: Effect):
    """A reasonable target for eff, respecting hexproof and targeting restrictions."""
    opp = game.opponent(me)
    legal = game.legal_targets(me, eff)
    theirs = [x for x in legal if isinstance(x, Permanent) and x.controller is opp]
    mine = [x for x in legal if isinstance(x, Permanent) and x.controller is me]
    k = eff.kind
    if k == "damage":
        if eff.target == "player":
            return opp
        if eff.target == "any" and eff.amount >= opp.life:
            return opp
        killable = [x for x in theirs if (x.is_creature and x.toughness - x.damage <= eff.amount and
                                          not x.has("indestructible")) or (x.is_planeswalker and not x.is_creature
                                                                           and x.loyalty <= eff.amount)]
        if killable:
            return max(killable, key=perm_value)
        return opp if eff.target == "any" else None
    if k in removal.KINDS:
        return removal.choose(game, me, eff)
    if k == "mill":
        return opp
    if k == "tap":
        theirs = [x for x in theirs if not x.tapped]
        return max(theirs, key=perm_value, default=None)
    if k == "shrink":
        return max(theirs, key=perm_value, default=None)
    if k in ("destroy", "debuff_one", "bounce"):
        if k == "debuff_one":
            theirs = [x for x in theirs if x.toughness <= eff.amount2]
        theirs = [x for x in theirs if not (k == "destroy" and x.has("indestructible"))]
        return max(theirs, key=perm_value, default=None)
    if k in ("pump", "p1_counters", "double_power", "grant", "explore", "attach_self", "force_blocked"):
        return max(mine, key=perm_value, default=None)
    if k == "oring":
        return max(theirs, key=perm_value, default=None)
    if k in ("stun", "shuffle_away", "cant_block_turn", "force_block"):
        return max(theirs, key=perm_value, default=None)
    if k == "unblockable":
        ready = [x for x in mine if x.can_attack() and x.power > 0]
        return max(ready, key=lambda x: x.power, default=None)
    if k in ("counter", "bounce_spell"):
        return next((i for i in reversed(game.stack) if i in legal), None)
    if k in ("discard", "discard_choice"):
        return opp if opp.hand else None
    return None



def choose_basic(game: Game, me: Player):
    """The basic land to fetch: one making the colour the hand needs most and the battlefield has least."""
    basics = [c for c in me.library if is_basic_land(c)]
    if not basics:
        return None
    have = {col: sum(col in x.card.produces for x in me.battlefield if x.card.is_land) for col in COLORS}
    need = {col: sum(c.mana_cost.get(col, 0) for c in me.hand + me.library) for col in COLORS}
    return max(basics, key=lambda c: max((need[col] / (1 + have[col]) for col in c.produces), default=0))



def choose_earthbend(game: Game, me: Player):
    """The land to earthbend: one already earthbent, else a tapped land, else any land."""
    lands = [x for x in me.battlefield if x.card.is_land]
    return max(lands, key=lambda x: (bool(x.animated), x.tapped, not is_basic_land(x.card)), default=None)


def play_extra_lands(game: Game, me: Player):
    """Land drops the AI doesn't make: additional lands (Icetill Explorer) and lands from the graveyard."""
    for _ in range(3):
        if me.land_played:
            return
        lands = [c for c in me.hand if c.is_land] + [c for c in game.impulse_cards(me) if c.is_land]
        if any(x.card.lands_from_gy for x in me.battlefield):
            lands += [c for c in me.graveyard if c.is_land]
        if not lands:
            return
        game.play_land(me, min(lands, key=lambda c: (c.enters_tapped, c in me.hand)))


def choose_tutor(game: Game, me: Player, cards: list[CardDef]) -> CardDef:
    """The card to search for: a land when short of lands, else the best spell we can soon cast."""
    lands = sum(x.card.is_land for x in me.battlefield)
    if _wants_land(game, me) and any(c.is_land for c in cards):
        return next(c for c in cards if c.is_land)
    spells = [c for c in cards if not c.is_land] or cards
    castable = [c for c in spells if c.cmc <= lands + 1] or spells
    return max(castable, key=lambda c: (c.cmc, (c.power or 0) + (c.toughness or 0)))


def choose_color(game: Game, me: Player) -> str:
    """The colour a land that enters as a chosen basic land type should make."""
    have = {col: sum(col in x.card.produces for x in me.battlefield if x.card.is_land) for col in COLORS}
    need = {col: sum(c.mana_cost.get(col, 0) for c in me.hand + me.library) for col in COLORS}
    return max(COLORS, key=lambda col: need[col] / (1 + have[col]))


def choose_target(game: Game, me: Player, eff: Effect):
    return default_choose_target(game, me, eff)


def _mode_value(game: Game, me: Player, effects: list) -> float:
    opp = game.opponent(me)
    total = 0.0
    for e in effects:
        if e.target in TARGETED:
            tgt = default_choose_target(game, me, e)
            if tgt is None:
                return -1
        else:
            tgt = None
        k = e.kind
        if k == "proliferate":
            total += e.amount * proliferate.value(game, me)
        elif k == "learn":
            total += learning.value(game, me)
        elif k == "regenerate":
            pass  # shields are selected in response to threats, not in safe main phases
        elif k == "wrath":
            total += sum(map(perm_value, opp.creatures)) - sum(map(perm_value, me.creatures))
        elif k == "wrath_pw":
            total += sum(map(perm_value, opp.planeswalkers)) - sum(map(perm_value, me.planeswalkers))
        elif k == "damage":
            total += perm_value(tgt) if isinstance(tgt, Permanent) else (100 if e.amount >= opp.life else 1)
        elif k in ("discard", "discard_choice"):
            total += 2 if opp.hand else 0
        elif k == "regrow":
            total += max((c.cmc for c in me.graveyard if c.is_creature), default=-1)
        elif k == "gy_move":
            ok = [c.cmc for c in me.graveyard if copies.fits(c, _gy_desc(e.data["what"]))]
            total += (max(ok) + 1) if ok else -1
        elif k in ("destroy", "bounce", "shuffle_away"):
            total += perm_value(tgt)
        elif k in ("bounce_spell", "counter"):
            total += tgt.card.cmc if isinstance(tgt, StackItem) and tgt.card else 1
        elif k in copies.KINDS:
            v = copies.value(game, me, e)
            if v < 0:
                return -1
            total += v
        elif k == "unblockable":
            # Only worth it before combat, when the opponent has a blocker.
            if game.step != "main1" or not any(not c.tapped for c in opp.creatures):
                return -1
            total += tgt.power
        else:
            total += 1
    return total


def default_choose_modes(game: Game, me: Player, modes: list, n: int, up_to: bool) -> list[int]:
    """Pick the n most valuable modes (only worthwhile ones for "choose up to")."""
    scored = sorted(((_mode_value(game, me, m), i) for i, m in enumerate(modes)), reverse=True)
    if up_to:
        return [i for v, i in scored[:n] if v > 0]
    usable = [i for v, i in scored if v >= 0]
    return (usable or [i for _, i in scored])[:n]


def _targets_for(game: Game, me: Player, card: CardDef, stack_target=None):
    """Targets for each of card's effects, or None if a needed target is missing."""
    opp = game.opponent(me)
    out = []
    for eff in card.spell_effects:
        if eff.target == "spell":
            out.append(stack_target)
        elif eff.target in ("creature", "creature_pw", "nonland_perm") and \
                game.step in ("declare_attackers", "declare_blockers") and game.active is opp:
            pool = [a for a in game.attackers if a in game.legal_targets(me, eff)]
            if eff.kind == "damage":
                pool = [c for c in pool if c.toughness - c.damage <= eff.amount]
            tgt = max(pool, key=perm_value, default=None)
            if tgt is None:
                return None
            out.append(tgt)
        elif eff.target in TARGETED:
            tgt = default_choose_target(game, me, eff)
            if tgt is None or (eff.kind == "damage" and tgt is opp and eff.target != "player"):
                return None
            out.append(tgt)
        else:
            out.append(None)
    return out


def _removal(card: CardDef) -> bool:
    return any(e.kind in ("destroy", "bounce") or (e.kind == "damage" and e.target in ("creature", "any", "creature_pw"))
               for e in card.spell_effects)


def respond(game: Game, me: Player):
    """A simple instant-speed policy: counter opponents' meaningful spells, protect creatures
    from removal, kill attackers, flash in The Wandering Emperor to exile an attacker, and
    use leftover mana at the opponent's end step on removal, flash creatures, card draw and
    Clues. Returns an action (see Game.do_action) or None to pass."""
    protect = regeneration.respond(game, me)
    if protect is not None:
        return protect
    opp = game.opponent(me)
    options = {c.name: c for c in game.spell_options(me) if c.instant_speed and game.can_cast_now(me, c)}
    top = game.stack[-1] if game.stack else None
    if top is not None:
        if top.controller is me:
            return None
        # Protect a creature targeted by removal (Snakeskin Veil).
        aimed = [t for t in top.targets if isinstance(t, Permanent) and t.controller is me]
        if aimed and any(e.kind in ("destroy", "damage", "bounce", "debuff_one") for e in top.effects):
            for c in options.values():
                if any(e.kind == "grant" and e.data.get("keyword") == "hexproof" for e in c.spell_effects):
                    return c, [aimed[0]] + [None] * (len(c.spell_effects) - 1)
        if not top.is_spell or not game.counterable(top) or _threat(game, me, top) < 3:
            return None
        counters = [c for c in options.values()
                    if any(game.can_counter(e, top, me) for e in c.spell_effects if e.kind == "counter")]
        if not counters:
            return None
        card = min(counters, key=lambda c: c.cmc)
        return card, _targets_for(game, me, card, top)
    # Empty stack.
    extra = respond_extras(game, me)
    if extra or me is game.active:
        return extra
    removal = [c for c in options.values() if _removal(c)]
    if game.step == "declare_attackers" and game.attackers:
        for card in sorted(removal, key=lambda c: c.cmc):
            targets = _targets_for(game, me, card)
            if targets:
                return card, targets
    if game.step == "end_step":
        for card in sorted(removal, key=lambda c: c.cmc):
            targets = _targets_for(game, me, card)
            if targets and any(isinstance(t, Permanent) and perm_value(t) >= 3 for t in targets):
                return card, targets
        flash = [c for c in options.values() if c.is_creature or c.is_planeswalker]
        if flash:
            return max(flash, key=lambda c: c.cmc), None
        draw = [c for c in options.values()
                if c.spell_effects and all(e.kind in ("draw", "dig", "scry", "surveil", "discard", "gain_life")
                                           for e in c.spell_effects)]
        if draw:
            card = max(draw, key=lambda c: c.cmc)
            return card, [None] * len(card.spell_effects)
    return None


def _option_value(game: Game, me: Player, c: CardDef) -> float:
    if c.is_permanent:
        return 1
    rest = _mode_value(game, me, c.spell_effects) if c.spell_effects else 0
    return modal.value(game, me, c.modes, n=c.modes_choose) + max(rest, 0) if c.modes else rest


def respond_extras(game: Game, me: Player):
    """Empty-stack actions for mechanics an AI may not handle: The Wandering Emperor (flash her
    in when attacked, use her abilities the turn she enters), and at the opponent's end step
    Clues plus instant-speed options cast from other zones or with modes (flashback, adventure,
    channel, Kolaghan's Command)."""
    protect = regeneration.respond(game, me)
    if protect is not None:
        return protect
    if game.stack:
        return None
    for pw in me.planeswalkers:
        if pw.card.pw_instant_on_entry and pw.entered_turn == game.turn and not pw.loyalty_used:
            idx = default_loyalty_choice(game, me, pw)
            if idx is not None:
                return ("loyalty", pw, idx)
    if me is game.active:
        if game.step == "declare_blockers":
            return combat_pump(game, me)
        return None
    options = [c for c in game.spell_options(me) if c.instant_speed and game.can_cast_now(me, c)]
    if game.step == "declare_attackers" and game.attackers:
        flash_pw = [c for c in options if c.is_planeswalker]
        if flash_pw:
            return flash_pw[0], None
    if game.step == "end_step":
        for c in options:
            if c in me.hand and not c.modes:
                continue   # plain hand cards are the AI's call
            if _option_value(game, me, c) > 0:
                return c, None
        clues = [x for x in me.battlefield if x.card.token_kind == "clue"]
        if clues and game.can_pay(me, {"generic": 2}):
            return ("activate", clues[0], "clue")
        ability = choose_ability(game, me, instant=True)
        if ability is not None:
            return ability
    return None


def _self_pump(act) -> bool:
    return bool(act.effects) and all(e.target == "self" and e.kind in ("pump", "grant", "p1_counters")
                                     for e in act.effects)


def ability_worth(game: Game, me: Player, perm: Permanent, idx: int, reserve: int = 0) -> bool:
    """Whether to activate perm's general ability idx now, outside combat."""
    act = perm.card.activated[idx]
    c = act.extra_costs
    if _self_pump(act) and not any(e.kind == "p1_counters" for e in act.effects):
        return False    # used in combat (combat_pump)
    if not game.can_activate(me, perm, idx):
        return False
    need = add_costs(act.cost, {"generic": reserve})
    if not payable(game.mana_sources(me, perm if c.get("tap") else None, "ability"), need):
        return False
    value = _mode_value(game, me, act.effects)
    if act.modes:
        value += modal.value(game, me, act.modes, perm)
    if value <= 0:
        return False
    if c.get("sac_self") or c.get("exile_self"):
        if perm.is_creature or perm.is_planeswalker:
            return value >= perm_value(perm)
        if perm.card.is_land and sum(x.card.is_land for x in me.battlefield) < 6:
            return False
    if c.get("sacrifice"):
        for victim in game.sacrifice_candidates(me, perm, c["sacrifice"])[:c.get("sac_n", 1)]:
            if not victim.card.is_token and perm_value(victim) > 1:
                return False
    if c.get("discard") and not choose_rummage(game, me, 1) and len(me.hand) <= 4:
        return False
    if c.get("life") and me.life <= 10:
        return False
    return True


def choose_equip_target(game: Game, me: Player, equipment: Permanent):
    """The creature to equip: the best one that can attack this turn, else the best one."""
    cands = [c for c in me.creatures if (not c.card.is_token or c.power > 0) and game.targetable(c, me)]
    if not cands:
        return None
    ready = [c for c in cands if not c.sick or c.has("haste") or "haste" in equipment.card.equip_keywords]
    pool = ready if ready and game.step == "main1" else cands
    return max(pool, key=lambda c: (c.card.equip_discount, perm_value(c) - len(c.equipment)))


def equip_all(game: Game, me: Player):
    """Attach unattached Equipment with spare mana (main phase 1, so it helps this combat)."""
    for eq in [x for x in me.battlefield if x.card.equip_cost is not None and x.attached_to is None]:
        tgt = game.hook(me, "choose_equip_target")(game, me, eq)
        if tgt is None:
            continue
        need = add_costs(game.equip_cost(eq, tgt), {"generic": _reserve(game, me)})
        if payable(game.mana_sources(me, spell="ability"), need):
            game.equip(me, eq, tgt)


def choose_ability(game: Game, me: Player, instant: bool):
    """An ("activate", permanent, "ability:N") action worth taking now, or None. With instant=True
    only abilities without "Activate only as a sorcery"."""
    for perm in list(me.battlefield):
        for i, act in enumerate(perm.card.activated):
            if act.kind != "ability" or (instant and act.sorcery):
                continue
            if ability_worth(game, me, perm, i, 0 if instant else _reserve(game, me)):
                return ("activate", perm, f"ability:{i}")
    return None


def combat_pump(game: Game, me: Player):
    """After blockers: pump unblocked attackers with their own "+N/+N until end of turn" abilities."""
    for a in game.attackers:
        if a.controller is not me or a in game.blocks or a not in me.battlefield:
            continue
        for i, act in enumerate(a.card.activated):
            if act.kind != "ability" or not _self_pump(act) or not game.can_activate(me, a, i):
                continue
            if act.extra_costs.get("life") and me.life <= 10:
                continue
            if any(e.kind == "pump" and e.amount > 0 for e in act.effects):
                return ("activate", a, f"ability:{i}")
    return None


def _wants_land(game: Game, me: Player) -> bool:
    lands = sum(p.card.is_land for p in me.battlefield) + sum(c.is_land for c in me.hand)
    return lands < 5


def scry(game: Game, me: Player, cards: list[CardDef]) -> list[CardDef]:
    """Cards to put on the bottom (or into the graveyard): lands when we have plenty,
    expensive spells when short."""
    want = _wants_land(game, me)
    return [c for c in cards if (c.is_land and not want) or (not c.is_land and want and c.cmc >= 5)]


def choose_dig(game: Game, me: Player, cards: list[CardDef], keep: int) -> list[CardDef]:
    want = _wants_land(game, me)
    score = lambda c: (2 if want else -1) if c.is_land else 1 + c.cmc / 10
    return sorted(cards, key=score, reverse=True)[:keep]


def pay_unless(game: Game, me: Player, amount: int, item: StackItem) -> bool:
    return True


def pay_optional(game: Game, me: Player, cost: dict, what: str) -> bool:
    return True


def pay_shock(game: Game, me: Player, card: CardDef) -> bool:
    return me.life > 8


def choose_discard_from(game: Game, me: Player, victim: Player):
    spells = [c for c in victim.hand if not c.is_land]
    return max(spells, key=lambda c: c.cmc, default=None)


def choose_rummage(game: Game, me: Player, n: int) -> list[CardDef]:
    lands_out = sum(x.card.is_land for x in me.battlefield)
    lands = [c for c in me.hand if c.is_land]
    out = lands[:max(0, len(lands) - 1)] if lands_out >= 4 else []
    out += [c for c in me.hand if not c.is_land and c.cmc > lands_out + 3]
    return out[:n]


def saddle_creatures(game: Game, me: Player, mount: Permanent):
    """Creatures to tap to saddle mount (total power at least its saddle number): summoning-sick ones first,
    then the smallest. Not worth it when a creature as strong as the Mount would be tapped."""
    cands = sorted((c for c in me.creatures if c is not mount and not c.tapped), key=lambda c: (not c.sick, c.power))
    crew, total = [], 0
    for c in cands:
        if total >= mount.card.saddle:
            break
        if not c.sick and c.power >= mount.power:
            break
        crew.append(c)
        total += c.power
    return crew if total >= mount.card.saddle else None


def choose_crew(game: Game, me: Player, vehicle: Permanent):
    """Creatures to tap to crew vehicle: summoning-sick ones first, then the smallest."""
    if vehicle.sick or vehicle.tapped:
        return None
    cands = sorted((c for c in me.creatures if c is not vehicle and not c.tapped),
                   key=lambda c: (not c.sick, c.power))
    crew, total = [], 0
    for c in cands:
        if total >= vehicle.card.crew:
            break
        if not c.sick and c.power >= vehicle.card.power:
            break
        crew.append(c)
        total += c.power
    return crew if total >= vehicle.card.crew else None


def _reserve(game: Game, me: Player) -> int:
    """Mana to keep open for instant-speed cards in hand."""
    return min((c.cmc for c in me.hand if not c.is_land and c.instant_speed), default=0)


def before_attacks(game: Game, me: Player):
    """Crew vehicles and animate manlands with spare mana before attackers are chosen."""
    for v in [x for x in me.battlefield if x.card.crew and not x.is_creature]:
        game.activate(me, v, "crew")
    for m in [x for x in me.battlefield if x.card.saddle and not x.saddled and not x.sick and not x.tapped]:
        game.activate(me, m, "saddle")
    for land in [x for x in me.battlefield if x.card.activated and not x.sick and not x.tapped]:
        for act in land.card.activated:
            if act.kind not in ("animate", "barrens"):
                continue
            need = add_costs(act.cost, {"generic": _reserve(game, me)})
            if payable(game.mana_sources(me, exclude=land), need):
                game.activate(me, land, act.kind)
                break


def choose_attack_targets(game: Game, me: Player, attackers: list) -> dict:
    """Send attackers at opposing planeswalkers unless the player is dead on board."""
    opp = game.opponent(me)
    if not opp.planeswalkers or sum(a.power for a in attackers) >= opp.life:
        return {}
    out, free = {}, sorted(attackers, key=lambda a: a.power)
    for pw in sorted(opp.planeswalkers, key=lambda x: -x.loyalty):
        assigned = 0
        for a in list(free):
            if assigned >= pw.loyalty:
                break
            out[a] = pw
            assigned += a.power
            free.remove(a)
    return out


def default_loyalty_choice(game: Game, me: Player, pw: Permanent):
    """Index of the loyalty ability to use, or None."""
    abilities = pw.card.loyalty_abilities
    best, best_score = None, -1e9
    for i, (cost, effects) in enumerate(abilities):
        if pw.loyalty + cost < 0:
            continue
        value = _mode_value(game, me, effects)
        if value < 0:
            continue
        if cost <= -7:
            value += 20
        if cost < 0 and pw.loyalty + cost < 2:
            value -= 2
        score = value + cost * 0.5
        if score > best_score:
            best, best_score = i, score
    return best


def use_abilities(game: Game, me: Player):
    """Sorcery-speed choices the heuristic AI doesn't make: loyalty abilities, Bloodtithe
    Harvester, Blood tokens and (in the second main phase) foretelling."""
    for pw in list(me.planeswalkers):
        if not pw.loyalty_used:
            idx = default_loyalty_choice(game, me, pw)
            if idx is not None:
                game.activate_loyalty(me, pw, idx)
    blood = sum(1 for x in me.battlefield if x.card.token_kind == "blood")
    for h in [x for x in me.battlefield if any(a.kind == "sac_debuff" for a in x.card.activated)]:
        opp = game.opponent(me)
        kills = [c for c in opp.creatures if c.toughness <= 2 * blood and game.targetable(c, me)
                 and perm_value(c) > perm_value(h)]
        if blood and kills and not h.sick and not h.tapped:
            game.activate(me, h, "sac_debuff")
    play_extra_lands(game, me)
    equip_all(game, me)
    if game.step == "main1":    # "can't be blocked this turn" before combat
        for perm in list(me.battlefield):
            for i, act in enumerate(perm.card.activated):
                if act.kind == "ability" and act.effects and act.effects[0].kind == "unblockable" and \
                        perm in me.battlefield and ability_worth(game, me, perm, i):
                    game.activate(me, perm, f"ability:{i}")
    # Spells from other zones or with alternative costs the AI may not look at.
    for c in game.spell_options(me):
        if (c in me.hand and not c.modes) or c.instant_speed or not game.can_cast_now(me, c):
            continue
        need = add_costs(game.cost_of(me, c), {"generic": _reserve(game, me)})
        if not payable(game.mana_sources(me), need):
            continue
        if _option_value(game, me, c) > 0:
            game.cast(me, c, None)
    if game.step == "main2":
        for st in [x for x in me.battlefield if x.card.station]:
            need = max((a.min_charge for a in st.card.activated), default=0)
            ready = sorted((c for c in me.creatures if c is not st and not c.tapped and c.power > 0),
                           key=lambda c: c.power)
            if need and st.counters.get("charge", 0) < need and len(ready) > 1:
                game.station(me, st, ready[-1])
        for _ in range(10):     # general activated abilities, a few at most
            ability = choose_ability(game, me, instant=False)
            if ability is None or not game.do_action(me, ability):
                break
        for b in [x for x in me.battlefield if x.card.token_kind == "blood"]:
            if choose_rummage(game, me, 1) and game.can_pay(me, {"generic": 1 + _reserve(game, me)}):
                game.activate(me, b, "blood")
        for card in [c for c in me.hand if any(a.kind == "plot" for a in c.alt_costs)]:
            alt = next(a for a in card.alt_costs if a.kind == "plot")
            if game.can_pay(me, add_costs(alt.cost, {"generic": _reserve(game, me)}), spell="ability"):
                game.plot(me, card)
        for card in [c for c in me.hand if any(a.kind == "foretell" for a in c.alt_costs)]:
            if game.can_pay(me, {"generic": 2 + _reserve(game, me)}):
                game.foretell(me, card)


def default_sneak(game: Game, me: Player, attackers, blocks):
    """Sneak a creature in for its sneak cost when it beats the cheapest unblocked attacker it would return."""
    loose = sorted((a for a in attackers if a in me.battlefield and a not in blocks), key=perm_value)
    if not loose:
        return
    for card in sorted(me.hand, key=lambda c: -c.cmc):
        alt = next((a for a in card.alt_costs if a.kind == "sneak"), None)
        if alt is None or not game.can_pay(me, alt.cost):
            continue
        weakest = loose[0]
        if card.is_creature:
            worth = (card.power or 0) > weakest.power and card.cmc > weakest.card.cmc
        else:
            worth = weakest.card.is_token or weakest.card.cmc <= 2
        if worth and game.sneak(me, card, alt, weakest):
            return


DEFAULTS = {
    "choose_replacement": lambda game, me, choices, event: choices[0],
    "choose_legend": lambda game, me, choices: max(choices, key=perm_value),
    "choose_learn": learning.choose,
    "choose_rebound": lambda game, me, card: True,
    "choose_cascade": lambda game, me, card: True,
    "choose_proliferate": proliferate.choose,
    "sneak": default_sneak,
    "respond": respond, "choose_target": choose_target, "choose_modes": default_choose_modes,
    "scry": scry, "choose_dig": choose_dig, "pay_unless": pay_unless, "pay_optional": pay_optional,
    "pay_shock": pay_shock, "choose_discard_from": choose_discard_from, "choose_rummage": choose_rummage,
    "choose_crew": choose_crew, "before_attacks": before_attacks, "choose_attack_targets": choose_attack_targets,
    "use_abilities": use_abilities, "respond_extras": respond_extras, "choose_equip_target": choose_equip_target,
}
# Older names, kept for compatibility.
default_respond = respond
default_scry = scry
default_dig = choose_dig
