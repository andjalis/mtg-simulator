"""AI players. Swap in a smarter class with the same methods to compare.

HeuristicAI scores every decision with one evaluation: life totals on a concave
scale (the last points matter most, and burn in hand counts towards them) plus
the value of creatures on the battlefield. Combat is decided by simulating it:
the attacker tries attack sets against the blocks the defender would make, and
checks it isn't left dead to the crack-back. BaselineAI is the original simple
player, kept so the two can be played against each other.
"""
from __future__ import annotations

import dataclasses
import math
from itertools import combinations

from .cards import CardDef, Effect
from . import copies, counting, engine, learning, modal, proliferate, protection
from .engine import Game, Permanent, Player, can_block, payable

LETHAL = 1000.0
LIFE_SCALE = 5.0        # value of life = LIFE_SCALE * sqrt(life)
HOLD_BURN = 2.5         # value of keeping an any-target burn spell for a creature later
CRACK_WEIGHT = 0.5      # weight on (non-lethal) damage we expect to take back next turn
MAX_SETUP_SPELLS = 6    # spells considered when looking for a precombat kill (pump, burn, keywords)
MAX_ENUMERATE = 6       # try every attack set up to this many ready creatures
REMOVAL_BAR = 4.5       # least a creature must be worth to spend instant removal on it
PW_KEEP = 2.0           # value of a planeswalker still being on the battlefield next turn
SWEEP_BAR = 6.0         # least net value for a sweeper when we are not under pressure
SETUP_FIGHT_BUDGET = 100_000    # fight simulations one lethal_setup search may spend

# Armed while lethal_setup searches: fight_group decrements it and raises when spent, so a
# wide board with many setup spells degrades to the normal main phase instead of stalling
# the match for tens of minutes. Deterministic: the same game state always aborts the same way.
_fight_budget = None


class _FightBudgetExceeded(Exception):
    pass


def _arm_fight_budget():
    global _fight_budget
    _fight_budget = SETUP_FIGHT_BUDGET


def _disarm_fight_budget():
    global _fight_budget
    _fight_budget = None


def card_value(card: CardDef) -> float:
    if card.is_creature:
        v = card.cmc + ((card.power or 0) + (card.toughness or 0)) / 2 + 0.5 * len(card.keywords)
        return v + (1.0 if card.produces else 0.0)
    return card.cmc + getattr(card, "loyalty", 0)


def perm_value(p: Permanent) -> float:
    return card_value(p.card) + (p.power - (p.card.power or 0)) * 0.5


def life_value(life: float) -> float:
    return LIFE_SCALE * math.sqrt(life) if life > 0 else 0.0


def kills(x: Permanent, y: Permanent) -> bool:
    return x.power > 0 and not y.has("indestructible") and (
        x.has("deathtouch") or x.power >= y.toughness - y.damage)


def _targetable(game: Game, perm: Permanent, by: Player) -> bool:
    return game.targetable(perm, by) if hasattr(game, "targetable") else True


def _legal(game: Game, by: Player, eff: Effect, perm: Permanent, card: CardDef | None = None) -> bool:
    """Targetable, passing the effect's restrictions ("nonblack", "mana value 2 or less"), and
    with any ward on it payable on top of card's cost (without card: from the mana left now)."""
    if card is not None and hasattr(game, "targeting"):
        with game.targeting(card):
            ok = game.legal_target(by, eff, perm)
    else:
        ok = game.legal_target(by, eff, perm) if hasattr(game, "legal_target") else _targetable(game, perm, by)
    return ok and _ward_payable(game, by, perm, card)


def _ward_payable(game: Game, by: Player, perm, card: CardDef | None = None) -> bool:
    if not isinstance(perm, Permanent) or perm.controller is by:
        return True
    ward = getattr(perm, "ward", 0)
    if ward:
        cost = dict(game.cost_of(by, card) if card is not None and card.name and hasattr(game, "cost_of")
                    else (card.mana_cost if card is not None else {}))
        cost.pop("X", None)
        cost["generic"] = cost.get("generic", 0) + ward
        return payable(game.mana_sources(by), cost)
    life = getattr(perm.card, "ward_life", 0)
    if life:
        return by.life > life + 3
    if getattr(perm.card, "ward_discard", False):
        return len(by.hand) > (1 if card is not None and card in by.hand else 0)
    return True


CREATURE_TARGETS = ("permanent", "creature", "creature_pw", "any")


def _spell_options(game: Game, me: Player) -> list:
    """Hand cards plus adventures, flashback, foretold cards and other alternative casts."""
    cards = game.spell_options(me) if hasattr(game, "spell_options") else me.hand
    return list({c.name: c for c in cards if not c.is_land}.values())


# Rough value of effects the main evaluation has no special case for.
MINOR_EFFECTS = {"treasure": 1.0, "rummage": 0.3, "surveil": 0.3, "scry": 0.3, "dig_put": 2.0,
                 "draw_up_to": 1.5, "grant": 0.5, "add_counter": 0.5, "transform": 1.0}


def _boost(card: CardDef):
    """(effect, +power, +toughness) for a spell that pumps or puts +1/+1 counters on our creature."""
    for e in card.spell_effects:
        if e.kind == "pump":
            return e, e.amount, e.amount2
        if e.kind == "p1_counters" and e.target == "creature_mine":
            return e, e.amount, e.amount
    return None


def _gives_hexproof(card: CardDef) -> bool:
    return any(e.kind == "grant" and (e.data or {}).get("keyword") == "hexproof" for e in card.spell_effects)


def _gives_protection(card: CardDef) -> bool:
    """Protection from the color of your choice: an answer to colored removal."""
    return any(e.kind == "grant" and (e.data or {}).get("keyword") == protection.CHOICE for e in card.spell_effects)


def _is_trick(card: CardDef) -> bool:
    """Instant pumps and protection spells: kept for combat and for answering removal."""
    return card.instant_speed and not card.is_permanent and (
        _boost(card) is not None or _gives_hexproof(card) or _gives_protection(card))


def _aim(card: CardDef, eff, target) -> list:
    return [target if e is eff else None for e in card.spell_effects]


# Effects plan_spell values through _extra_value.
EXTRA_KINDS = {"reanimate_total", "reanimate_one", "tutor_gy", "regrow_perm", "regrow_any", "tutor", "explore", "earthbend", "unblockable", "oring_all", "pump_all", "double_counters", "learn",
               "tap", "stun", "mill", "proliferate"} | copies.KINDS

CARRIER_KINDS = ("pump", "grant", "p1_counters", "unblockable")   # aimed at the creature that attacks

# Effects lethal_setup knows how to add up before combat, and the keywords it models.
SETUP_KINDS = {"pump", "grant", "p1_counters", "damage", "draw", "scry", "surveil", "unblockable"}
SETUP_KEYWORDS = {"double strike", "first strike", "haste", "trample", "flying", "menace"}
CAST_EVENTS = {"cast_instant_sorcery": lambda c: c.is_instant or c.is_sorcery,
               "cast_noncreature": lambda c: not c.is_creature,
               "cast_spell": lambda c: True, "any_cast": lambda c: True}


def _setup_spell(card: CardDef) -> bool:
    """A noncreature spell whose every effect lethal_setup can model."""
    if card.is_permanent or getattr(card, "modes", None) or not card.spell_effects:
        return False
    for e in card.spell_effects:
        if e.kind not in SETUP_KINDS:
            return False
        if e.kind == "grant" and (e.data or {}).get("keyword") not in SETUP_KEYWORDS:
            return False
        if e.kind in ("pump", "grant", "p1_counters", "unblockable") and e.target not in ("creature", "creature_mine"):
            return False
        if e.kind == "damage" and e.target not in ("any", "player", "creature", "creature_pw"):
            return False
    return True


def _product(choices):
    """Every way to pick one item from each list in choices."""
    out = [[]]
    for opts in choices:
        out = [o + [x] for o in out for x in opts]
    return out


def _counter_effects(card: CardDef) -> list:
    """The counter effects of a spell, or of its first mode that counters ("counter target creature spell
    or choose one")."""
    effs = [e for e in card.spell_effects if e.kind == "counter"]
    if effs or not getattr(card, "modes", None):
        return effs
    return next(([e for e in mode if e.kind == "counter"] for mode in card.modes
                 if any(e.kind == "counter" for e in mode)), [])


def _is_counter(card: CardDef) -> bool:
    return bool(_counter_effects(card))


def fight(a: Permanent, b: Permanent) -> tuple[bool, bool]:
    """(a dies, b dies) if a and b deal combat damage to each other."""
    if any(c.has(k) for c in (a, b) for k in ("infect", "wither")) or a.regeneration_shields or b.regeneration_shields:
        dead = fight_group(a, [b])[0]
        return a in dead, b in dead
    a_first = a.has("first strike") or a.has("double strike")
    b_first = b.has("first strike") or b.has("double strike")
    a_kills, b_kills = kills(a, b), kills(b, a)
    if a_first and not b_first and a_kills:
        return False, True
    if b_first and not a_first and b_kills:
        return True, False
    return b_kills, a_kills


def combat_power(c: Permanent) -> int:
    return c.power * (2 if c.has("double strike") else 1)


def face_burn(card: CardDef) -> int:
    """Damage this card can deal to a player."""
    return sum(e.amount for e in card.spell_effects
               if e.kind == "damage" and e.target in ("any", "player")) + \
        sum(e.amount for e in card.spell_effects if e.kind == "drain")


def reach(p: Player) -> int:
    """Burn in hand that could go face: counts towards the opponent's effective life."""
    return sum(face_burn(c) for c in p.hand if not c.is_land and not c.is_permanent)


# ------------------------------------------------------------------ combat model
def _strikes_first(c) -> bool:
    return c.has("first strike") or c.has("double strike")


def fight_group(a: Permanent, blockers, bonus=0, include_poison=False) -> tuple:
    """Resolve one attacker and its (ordered) blockers on copies, mirroring Game.combat_damage.

    Fights are independent of each other, so a whole combat is the sum of its groups.
    Returns (dead permanents, damage to defending player, attacker life gain, defender life gain).
    """
    global _fight_budget
    if _fight_budget is not None:
        _fight_budget -= 1
        if _fight_budget <= 0:
            raise _FightBudgetExceeded
    group = [a, *blockers]
    dmg = {c: c.damage for c in group}
    minus = {c: 0 for c in group}
    power = lambda c: c.power + (bonus if c is a else 0) - minus[c]
    toughness = lambda c: c.toughness + (bonus if c is a else 0) - minus[c]
    dt, dead = set(), set()
    removed = set()
    shields = {c: c.regeneration_shields if not c.regeneration_blocked else 0 for c in group}
    to_player = att_gain = def_gain = poison = 0
    first = any(_strikes_first(c) for c in group)

    def step(deals_now):
        nonlocal to_player, att_gain, def_gain, poison
        if a in dead or a in removed:
            return
        hits = []
        alive = [b for b in blockers if b not in dead and b not in removed]
        if deals_now(a) and power(a) > 0:
            if not blockers:
                hits.append((a, None, power(a)))
            else:
                remaining = power(a)
                for i, b in enumerate(alive):
                    lethal = 1 if a.has("deathtouch") else max(0, toughness(b) - dmg[b])
                    last = i == len(alive) - 1
                    amt = remaining if (last and not a.has("trample")) else min(remaining, lethal)
                    if amt:
                        hits.append((a, b, amt))
                    remaining -= amt
                if remaining > 0 and a.has("trample"):
                    hits.append((a, None, remaining))
        for b in alive:
            if deals_now(b) and power(b) > 0:
                hits.append((b, a, power(b)))
        for src, tgt, amt in hits:
            if tgt is None:
                if src.has("infect"):
                    poison += amt
                else:
                    to_player += amt
            else:
                if src.has("infect") or src.has("wither"):
                    minus[tgt] += amt
                else:
                    dmg[tgt] += amt
                if src.has("deathtouch"):
                    dt.add(tgt)
            if src.has("lifelink"):
                if src is a:
                    att_gain += amt
                else:
                    def_gain += amt
        for c in group:
            if c in dead or c in removed:
                continue
            if toughness(c) <= 0:
                dead.add(c)
            elif (c in dt or dmg[c] >= toughness(c)) and not c.has("indestructible"):
                if shields[c]:
                    shields[c] -= 1
                    dmg[c] = 0
                    dt.discard(c)
                    removed.add(c)
                else:
                    dead.add(c)

    if first:
        step(_strikes_first)
    step(lambda c: not first or c.has("double strike") or not c.has("first strike"))
    result = dead, to_player, att_gain, def_gain
    return result + (poison,) if include_poison else result


def simulate_combat(attackers, blocks, cache=None, include_poison=False):
    """Sum of fight_group over all attackers; blocks maps attacker -> ordered blockers."""
    attackers = list(attackers)
    bonus = (sum(x.exalted_count for x in attackers[0].controller.battlefield)
             if len(attackers) == 1 and not attackers[0].controller.attacked_with else 0)
    dead, to_player, att_gain, def_gain, poison = set(), 0, 0, 0, 0
    for a in attackers:
        bl = tuple(blocks.get(a, ()))
        key = (a, bl, bonus)
        if cache is not None and key in cache:
            r = cache[key]
        else:
            r = fight_group(a, bl, bonus, include_poison=True)
            if cache is not None:
                cache[key] = r
        dead |= r[0]
        to_player += r[1]
        att_gain += r[2]
        def_gain += r[3]
        poison += r[4]
    result = dead, to_player, att_gain, def_gain
    return result + (poison,) if include_poison else result


def combat_score(attackers, blocks, att: Player, dfn: Player, att_reach=0, def_reach=0, cache=None):
    """Value of a combat outcome from the attacker's side (the defender's is the negative)."""
    dead, to_player, att_gain, def_gain, poison = simulate_combat(attackers, blocks, cache, include_poison=True)
    def_life = dfn.life - to_player + def_gain
    att_life = att.life + att_gain
    old_poison = dfn.counters.get("poison", 0)
    if def_life <= 0 or old_poison + poison >= 10:
        return LETHAL, dead, def_life
    score = (life_value(att_life - def_reach) - life_value(att.life - def_reach)
             - (life_value(def_life - att_reach) - life_value(dfn.life - att_reach)))
    if poison:
        score += life_value(2 * (10 - old_poison)) - life_value(2 * (10 - old_poison - poison))
    for c in dead:
        score += card_value(c.card) if c.controller is dfn else -card_value(c.card)
    return score, dead, def_life


def legal_blocks(assign: dict, attackers) -> dict:
    """blocker->attacker assignment to attacker->[blockers], dropping single blocks on menace."""
    blocks = {}
    for b, a in assign.items():
        if a is not None:
            blocks.setdefault(a, []).append(b)
    for a in list(blocks):
        if a.has("menace") and len(blocks[a]) < 2:
            del blocks[a]
        else:
            blocks[a].sort(key=perm_value, reverse=True)
    return blocks


def search_blocks(attackers, blockers, att: Player, dfn: Player, att_reach=0, def_reach=0,
                  cache=None) -> dict:
    """Greedy local search for the defender's best blocks (minimising the attacker's score)."""
    cache = {} if cache is None else cache
    attackers = [a for a in attackers]
    blockers = [b for b in blockers if not b.tapped and b.is_creature]
    options = {b: [a for a in attackers if can_block(b, a)] for b in blockers}
    blockers = [b for b in blockers if options[b]]
    assign = {b: None for b in blockers}

    def value(asg):
        return combat_score(attackers, legal_blocks(asg, attackers), att, dfn, att_reach, def_reach, cache)[0]

    best = value(assign)
    for _ in range(2 * len(blockers) + 2):
        move = None
        for b in blockers:
            for a in options[b] + [None]:
                if assign[b] is a:
                    continue
                trial = dict(assign)
                trial[b] = a
                v = value(trial)
                if v < best - 1e-9:
                    best, move = v, trial
        # Pairs of blockers onto one attacker: double blocks and menace.
        free = [b for b in blockers if assign[b] is None]
        for b1, b2 in combinations(free, 2):
            for a in options[b1]:
                if a not in options[b2]:
                    continue
                trial = dict(assign)
                trial[b1] = trial[b2] = a
                v = value(trial)
                if v < best - 1e-9:
                    best, move = v, trial
        if move is None:
            break
        assign = move
    return legal_blocks(assign, attackers)


def unblocked_damage(attackers, blockers, chump=True) -> int:
    """Damage a set of attackers gets through blockers that each stop one attacker.

    With chump=False a blocker only stops attackers it survives or trades with.
    """
    left = sorted(attackers, key=lambda c: -c[0])
    free = list(blockers)
    total = 0
    for power, flying, menace, perm in left:
        pick = None
        need = max(getattr(perm.card, "min_blocker_power", 0), perm.temp_min_blocker) if perm is not None else 0
        for b in free:
            if flying and not (b[1] or b[2]):
                continue
            if need and b[0] < need:
                continue
            if not chump and fight(perm, b[3])[1] and not fight(perm, b[3])[0]:
                continue
            pick = b
            break
        if pick is not None and not menace:
            free.remove(pick)
        else:
            total += power
    return total


def _sized_inner(game: Game, me: Player, eff: Effect) -> list:
    """A grammar wrapper's inner effects with the amounts they will resolve with: X paid (the wrapper's amount,
    as plan_spell sized it) and "for each" / "where X is" counts, as cx_group / cx_players apply them."""
    inner = eff.data["effects"]
    # keyed on the inner Part: _sized puts X in the wrapper's amount and clears the wrapper's own x flag
    inner = [dataclasses.replace(e, amount=eff.amount, amount2=eff.amount if e.data.get("x2") else e.amount2)
             if e.data.get("x") else e for e in inner]
    if eff.data.get("xq"):
        n = game.x_quantity(me, eff.data["xq"], None, None)
        inner = [dataclasses.replace(e, amount=e.amount * n, amount2=e.amount2 * n) for e in inner]
    return inner


class HeuristicAI:
    """Evaluation-driven player: simulates combat, holds instants for the opponent's turn."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Clear per-game state (run_match calls this on a fresh copy for every game)."""
        self._idle_turns = 0       # own turns in a row we kept mana up for a counter and cast nothing

    # -------------------------------------------------------------- mulligan
    def keep_hand(self, hand: list[CardDef], mulligans: int) -> bool:
        if mulligans >= 2:
            return True
        lands = sum(c.is_land or c.land_face is not None for c in hand)
        cheap = sum(not c.is_land and c.cmc <= 3 for c in hand)
        if lands < 2 or lands > 5:
            return False
        return lands >= 3 or cheap >= 1

    def cards_to_bottom(self, hand: list[CardDef], n: int) -> list[CardDef]:
        out, hand = [], list(hand)
        ideal_lands = 2 if len(hand) - n <= 5 else 3
        for _ in range(n):
            lands = [c for c in hand if c.is_land]
            spells = [c for c in hand if not c.is_land]
            if lands and (len(lands) > ideal_lands or not spells):
                pick = max(lands, key=lambda c: (c.enters_tapped, -len(c.produces)))
            else:
                pick = max(spells, key=lambda c: (c.cmc, -card_value(c)))
            hand.remove(pick)
            out.append(pick)
        return out

    def choose_discard(self, game: Game, me: Player) -> CardDef:
        lands_out = sum(p.card.is_land for p in me.battlefield)
        lands = [c for c in me.hand if c.is_land]
        if lands and lands_out >= 5:
            return lands[0]
        spells = [c for c in me.hand if not c.is_land]
        castable_soon = [c for c in spells if c.cmc <= lands_out + 1]
        pool = [c for c in spells if c not in castable_soon] or spells or me.hand
        return max(pool, key=lambda c: (c.cmc, -card_value(c)))

    # ---------------------------------------------------------- untap choice
    def choose_stay_tapped(self, game: Game, me: Player):
        """"You may choose not to untap ~ during your untap step" (Amber Prison and ~40
        similar permanents): stay tapped while being tapped keeps one of the opponent's
        permanents locked (a "doesn't untap ... as long as ~ remains tapped" freeze).
        The lock links are read tolerantly; with no active lock the flag is never set."""
        opp = game.opponent(me)
        for perm in me.battlefield:
            if not perm.tapped:
                continue
            if any(getattr(t, link, None) is perm
                   for t in opp.battlefield for link in ("frozen_by", "locked_by", "net_locked_by")):
                perm.stay_tapped = True

    # ------------------------------------------------------------ main phase
    def main_phase(self, game: Game, me: Player):
        precombat = getattr(game, "step", "main1") != "main2"
        self.play_land(game, me)
        cast_any = precombat and self.lethal_setup(game, me)
        while not game.over:
            choice = self.choose_spell(game, me, precombat, reserve=self._reserve(game, me))
            if choice is None:
                break
            if not game.cast(me, *choice):
                break
            cast_any = True
        if not precombat:
            held = bool(self._reserve(game, me))
            self._idle_turns = self._idle_turns + 1 if held and not cast_any else 0

    # ------------------------------------------------------- precombat kill
    def _best_attack_score(self, game: Game, me: Player, opp: Player) -> float:
        attack = self.choose_attackers(game, me, opp)
        return self.score_attack(game, me, opp, attack, 0, {}) if attack else 0.0

    def lethal_setup(self, game: Game, me: Player) -> bool:
        """Before combat, cast the fewest spells (pump, double strike, haste, burn to the face or
        at a blocker, plus the prowess-style cast triggers they set off) that make an attack
        lethal through the opponent's best blocks. Returns True if it cast anything."""
        opp = game.opponent(me)
        if not me.creatures or not opp.life > 0:
            return False
        spells = [c for c in _spell_options(game, me) if _setup_spell(c) and self._can_cast(game, me, c)
                  and "X" not in c.mana_cost]
        if not spells:
            return False
        spells = sorted(spells, key=lambda c: c.cmc)[:MAX_SETUP_SPELLS]
        if self._best_attack_score(game, me, opp) >= LETHAL:
            return False   # already lethal: keep the spells
        sources = game.mana_sources(me)
        best = None
        _arm_fight_budget()
        try:
            for r in range(1, min(len(spells), 4) + 1):
                for combo in combinations(spells, r):
                    cost = {}
                    for c in combo:
                        for k, v in self._cost(game, me, c).items():
                            cost[k] = cost.get(k, 0) + v
                    if not payable(sources, cost):
                        continue
                    plan = self._setup_plan(game, me, opp, combo)
                    if plan is not None:
                        key = (r, sum(c.cmc for c in combo))
                        if best is None or key < best[0]:
                            best = (key, plan)
                if best is not None:
                    break   # fewest spells first
        except _FightBudgetExceeded:
            return False    # too many boards and spells to search; play the normal main phase
        finally:
            _disarm_fight_budget()
        if best is None:
            return False
        cast = False
        for card, targets in best[1]:
            live = [t for t in targets if isinstance(t, Permanent)]
            if any(t not in t.controller.battlefield for t in live) or card not in _spell_options(game, me):
                break   # they answered a piece of the plan; fall back to the normal main phase
            if not game.cast(me, card, targets):
                break
            cast = True
            if game.over:
                break
        return cast

    def _setup_plan(self, game: Game, me: Player, opp: Player, combo):
        """[(card, targets)] if casting combo now makes some attack lethal, else None."""
        carriers = [c for c in me.creatures if not c.tapped and not c.has("defender")]
        needs_carrier = any(e.kind in CARRIER_KINDS for c in combo for e in c.spell_effects)
        caps = [int(e.filter[10:]) for c in combo for e in c.spell_effects
                if e.kind == "unblockable" and e.filter.startswith("max_power:")]
        carriers = [c for c in carriers if all(c.power <= cap for cap in caps)]
        burn = [c for c in combo if any(e.kind == "damage" for e in c.spell_effects)]
        blockers = [b for b in opp.creatures if not b.tapped]
        for carrier in (carriers if needs_carrier else [None]):
            # Burn goes face, or at one blocker it kills (each burn spell picks independently).
            choices = []
            for card in burn:
                eff = next(e for e in card.spell_effects if e.kind == "damage")
                opts = [opp] if eff.target in ("any", "player") else []
                if eff.target in CREATURE_TARGETS:
                    opts += [b for b in blockers if b.toughness - b.damage <= eff.amount
                             and not b.has("indestructible") and _legal(game, me, eff, b, card)][:3]
                if not opts:
                    break
                choices.append(opts)
            else:
                for aims in _product(choices):
                    burn_aim = dict(zip(burn, aims))
                    if self._lethal_after(game, me, opp, combo, carrier, burn_aim):
                        out = []
                        for card in combo:
                            out.append((card, [burn_aim.get(card) if e.kind == "damage" else
                                               carrier if e.kind in CARRIER_KINDS else None
                                               for e in card.spell_effects]))
                        # Keyword grants and pumps first, then burn (it may clear a blocker).
                        out.sort(key=lambda x: any(e.kind == "damage" for e in x[0].spell_effects))
                        return out
        return None

    def _lethal_after(self, game: Game, me: Player, opp: Player, combo, carrier, burn_aim) -> bool:
        """Apply combo's effects on scratch state, test for a lethal attack, then undo them."""
        undo_pump, undo_kw, removed, life = [], [], [], opp._life
        try:
            for card in combo:
                for c in me.creatures:
                    for t in c.triggers:
                        test = CAST_EVENTS.get(t.event)
                        if test is None or not test(card) or t.filter:
                            continue
                        for e in t.effects:
                            if e.kind == "pump" and e.target == "self":
                                c.pump_p += e.amount
                                c.pump_t += e.amount2
                                undo_pump.append((c, e.amount, e.amount2))
                for e in card.spell_effects:
                    if e.kind in ("pump", "p1_counters"):
                        dt = e.amount2 if e.kind == "pump" else e.amount
                        carrier.pump_p += e.amount
                        carrier.pump_t += dt
                        undo_pump.append((carrier, e.amount, dt))
                    elif e.kind in ("grant", "unblockable"):
                        kw = e.data["keyword"] if e.kind == "grant" else "unblockable"
                        if kw not in carrier.temp_kw:
                            carrier.temp_kw.add(kw)
                            undo_kw.append((carrier, kw))
                    elif e.kind == "damage":
                        tgt = burn_aim.get(card)
                        if tgt is opp:
                            opp._life -= e.amount
                        elif isinstance(tgt, Permanent) and tgt in opp.battlefield:
                            removed.append((opp.battlefield.index(tgt), tgt))
                            opp.battlefield.remove(tgt)
            if opp._life <= 0:
                return True
            return self._best_attack_score(game, me, opp) >= LETHAL
        finally:
            opp._life = life
            for c, dp, dt in undo_pump:
                c.pump_p -= dp
                c.pump_t -= dt
            for c, kw in undo_kw:
                c.temp_kw.discard(kw)
            for i, perm in reversed(removed):
                opp.battlefield.insert(i, perm)

    def _can_cast(self, game: Game, me: Player, card: CardDef) -> bool:
        if hasattr(game, "can_cast_now"):
            return game.can_cast_now(me, card)
        return game.can_pay(me, card.mana_cost)

    @staticmethod
    def _cost(game: Game, me: Player, card: CardDef) -> dict:
        return game.cost_of(me, card) if hasattr(game, "cost_of") else card.mana_cost

    def _reserve(self, game: Game, me: Player) -> dict:
        """Mana to keep open on our own turn for a counterspell, if we hold one."""
        opp = game.opponent(me)
        counters = [c for c in me.hand if _is_counter(c)]
        if not counters or not opp.hand or self._idle_turns >= 1:
            return {}
        if len(game.mana_sources(opp)) < 2 and any(
                (c.is_creature or c.is_planeswalker) and self._can_cast(game, me, c) for c in me.hand):
            return {}   # they are tapped out: the window to resolve a threat past their counters
        return self._cost(game, me, min(counters, key=lambda c: c.cmc))

    def choose_spell(self, game: Game, me: Player, precombat: bool, reserve=None):
        """Pick the next spell to cast, preferring the set of spells that uses the most mana."""
        castable = [c for c in _spell_options(game, me) if self._can_cast(game, me, c)]
        plans = {}
        for card in castable:
            plan = self.plan_spell(game, me, card, precombat)
            if plan is not None and plan[0] > 0:
                plans[card] = plan
        if not plans:
            return None
        sources = game.mana_sources(me)
        best_set, best_key = None, None
        for r in range(1, min(len(plans), 4) + 1):
            for combo in combinations(plans, r):
                cost = dict(reserve or {})
                for c in combo:
                    for k, v in self._cost(game, me, c).items():
                        if k != "X":
                            cost[k] = cost.get(k, 0) + v
                    cost["generic"] = cost.get("generic", 0) + sum(
                        getattr(t, "ward", 0) for t in plans[c][1] or ()
                        if isinstance(t, Permanent) and t.controller is not me)
                if not payable(sources, cost):
                    continue
                key = (sum(plans[c][0] for c in combo), sum(c.cmc for c in combo))
                if best_key is None or key > best_key:
                    best_set, best_key = combo, key
        if best_set is None:
            return None
        card = max(best_set, key=lambda c: (sum(v for k, v in c.mana_cost.items() if k in "WUBRGC"), c.cmc))
        return card, plans[card][1]

    def play_land(self, game: Game, me: Player):
        from . import cx_top
        top = cx_top.top(me)
        lands = ([top] if cx_top.land_ok(me, top) else []) + [c for c in me.hand if c.is_land]   # the top first
        if me.land_played:
            return
        if not lands:
            card = HeuristicAI.mdfc_land(self, game, me)
            if card is not None:
                game.play_land(me, card, back=True)
            return

        def castable_with(card):
            extra = None if card.enters_tapped else Permanent(card, me)
            if extra:
                extra.sick = False
            return sum(game.can_pay(me, HeuristicAI._cost(game, me, c), extra) for c in me.hand if not c.is_land)

        now = sum(game.can_pay(me, HeuristicAI._cost(game, me, c)) for c in me.hand if not c.is_land)

        def score(card):
            gain = castable_with(card) - now
            # Coloured sources we still lack for the pips in hand: {R}{R} wants two red lands, so a
            # second red source counts as much as the first (Smaug the Magnificent, {2}{R}{R}).
            pips = {}
            for c in me.hand:
                if not c.is_land:
                    for k, v in c.mana_cost.items():
                        if k in "WUBRG":
                            pips[k] = max(pips.get(k, 0), v)
            new_colors = sum(1 for col in card.produces if col in pips and
                             sum(col in p.card.produces for p in me.battlefield if p.card.is_land) < pips[col])
            # A tapped land is best played on a turn where it costs nothing.
            tapped_bonus = 1 if card.enters_tapped and gain <= 0 else 0
            return (gain, new_colors, tapped_bonus, -len(card.produces))

        game.play_land(me, max(lands, key=score))

    def mdfc_land(self, game: Game, me: Player):
        """A modal double-faced card to play as its land side (Kazandu Mammoth, Jwari Disruption)
        when we have no other land: early on, or when its spell side is out of reach anyway."""
        mdfcs = [c for c in me.hand if c.land_face is not None]
        if not mdfcs:
            return None
        lands_out = sum(p.card.is_land for p in me.battlefield)
        card = min(mdfcs, key=lambda c: (card_value(c), c.cmc))
        return card if lands_out < 4 or card.cmc > lands_out + 1 else None

    def face_value(self, game: Game, me: Player, amount: int, extra_reach=0) -> float:
        opp = game.opponent(me)
        if amount >= opp.life:
            return LETHAL
        eff = opp.life - (reach(me) - extra_reach)
        return life_value(eff) - life_value(eff - amount)

    @staticmethod
    def _sized(game: Game, me: Player, card: CardDef):
        """An X spell with X fixed at the largest value the remaining mana pays for, else None."""
        x = 0
        cost = game.cost_of(me, card)
        while x < 20 and engine.find_payment(game.mana_sources(me, spell=card), engine.add_costs(
                cost, {"generic": x + 1})) is not None:
            x += 1
        if x < 1:
            return None
        sized = [dataclasses.replace(e, amount=x, amount2=x if e.data.get("x2") else e.amount2,
                                    data={**e.data, "x": False})
                 if (e.data or {}).get("x") else e for e in card.spell_effects]
        return dataclasses.replace(card, spell_effects=sized)

    def plan_spell(self, game: Game, me: Player, card: CardDef, precombat: bool = False):
        """Return (value, targets) if the AI wants to cast card in its main phase, else None."""
        opp = game.opponent(me)
        if not card.is_permanent and any((e.data or {}).get("x") for e in card.spell_effects):
            sized = self._sized(game, me, card)
            return None if sized is None else self.plan_spell(game, me, sized, precombat)
        if card.is_permanent:
            if card.is_creature and precombat and "haste" not in card.keywords and not card.produces \
                    and any(_is_trick(c) for c in me.hand):
                return None  # keep mana open for the trick; cast it after combat
            if me is game.active and not card.is_creature and self._flash_removal(card):
                return None  # a flash "when this enters, deal damage to a creature": cast it on their turn
            if card.advanced_rules.get("mutating"):
                from .batch2_templates import mutate_worth
                worth = mutate_worth(game, me, card)
                return None if worth is None else (worth, None)
            if card.advanced_rules.get("bestowed"):
                from .batch1_templates import bestow_worth
                worth = bestow_worth(game, me, card)
                return None if worth is None else (worth, None)
            etb = self._etb_value(game, me, card, precombat)
            if etb < 0:
                return None  # its enters trigger costs us more than the permanent is worth
            return (card_value(card) + 0.5 * card.cmc + etb
                    + self._static_value(game, me, card) - self._sac_cost(game, me, card), None)
        instant = card.instant_speed
        if any('anchor' in e.data or e.kind in ('allocated_counter', 'return_tribal_grave', 'grave_library_top',
                'control_permanent', 'populate', 'advanced_quantity_stats', 'selected_mass_move', 'filtered_grave_return', 'graveyard_exile_all', 'graveyard_exile_choice') for e in card.spell_effects):
            from .engine.policy import _mode_value
            with game.targeting(card):
                value = _mode_value(game, me, card.spell_effects)
                targets = game.auto_targets(me, card.spell_effects)
                if value > 0 and game.valid_action_targets(me, card.spell_effects, targets, card):
                    return value, targets
            return None
        if getattr(card, "modes", None):
            # The engine picks modes and targets (choose_modes); value it the same way.
            if instant or not hasattr(engine, "_option_value"):
                return None
            v = engine._option_value(game, me, card)
            return (v, None) if v > 0 else None
        if not card.spell_effects:
            return None  # nothing we know how to do with it
        targets, value, pending = [], 0.0, []
        stolen, group_value, group_combat = False, None, False
        for eff in card.spell_effects:
            for e in _sized_inner(game, me, eff):
                if e.kind == "lose_life" and pl is opp and e.amount >= opp.life:
                    return target, LETHAL
                value += member_value(game, me, e, pl)[0]
