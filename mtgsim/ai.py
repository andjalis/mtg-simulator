"""AI players. Swap in a smarter class with the same methods to compare.

HeuristicAI scores every decision with one evaluation: life totals on a concave
scale (the last points matter most, and burn in hand counts towards them) plus
the value of creatures on the battlefield. Combat is decided by simulating it:
the attacker tries attack sets against the blocks the defender would make, and
checks it isn't left dead to the crack-back. BaselineAI is the original simple
player, kept so the two can be played against each other.
"""
from __future__ import annotations

import math
from itertools import combinations

from .cards import CardDef, Effect
from . import copies, engine, modal
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


CREATURE_TARGETS = ("creature", "creature_pw", "any")


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


def _is_trick(card: CardDef) -> bool:
    """Instant pumps and protection spells: kept for combat and for answering removal."""
    return card.instant_speed and not card.is_permanent and (_boost(card) is not None or _gives_hexproof(card))


def _aim(card: CardDef, eff, target) -> list:
    return [target if e is eff else None for e in card.spell_effects]


# Effects plan_spell values through _extra_value.
EXTRA_KINDS = {"tutor", "explore", "earthbend", "unblockable", "oring_all", "pump_all", "double_counters",
               "tap", "stun", "mill"} | copies.KINDS

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


def _is_counter(card: CardDef) -> bool:
    return any(e.kind == "counter" for e in card.spell_effects)


def fight(a: Permanent, b: Permanent) -> tuple[bool, bool]:
    """(a dies, b dies) if a and b deal combat damage to each other."""
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


def fight_group(a: Permanent, blockers) -> tuple:
    """Resolve one attacker and its (ordered) blockers on copies, mirroring Game.combat_damage.

    Fights are independent of each other, so a whole combat is the sum of its groups.
    Returns (dead permanents, damage to defending player, attacker life gain, defender life gain).
    """
    group = [a, *blockers]
    dmg = {c: c.damage for c in group}
    dt, dead = set(), set()
    to_player = att_gain = def_gain = 0
    first = any(_strikes_first(c) for c in group)

    def step(deals_now):
        nonlocal to_player, att_gain, def_gain
        if a in dead:
            return
        hits = []
        alive = [b for b in blockers if b not in dead]
        if deals_now(a) and a.power > 0:
            if not blockers:
                hits.append((a, None, a.power))
            else:
                remaining = a.power
                for i, b in enumerate(alive):
                    lethal = 1 if a.has("deathtouch") else max(0, b.toughness - dmg[b])
                    last = i == len(alive) - 1
                    amt = remaining if (last and not a.has("trample")) else min(remaining, lethal)
                    if amt:
                        hits.append((a, b, amt))
                    remaining -= amt
                if remaining > 0 and a.has("trample"):
                    hits.append((a, None, remaining))
        for b in alive:
            if deals_now(b) and b.power > 0:
                hits.append((b, a, b.power))
        for src, tgt, amt in hits:
            if tgt is None:
                to_player += amt
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
            if c not in dead and (c in dt or dmg[c] >= c.toughness) and not c.has("indestructible"):
                dead.add(c)

    if first:
        step(_strikes_first)
    step(lambda c: not first or c.has("double strike") or not c.has("first strike"))
    return dead, to_player, att_gain, def_gain


def simulate_combat(attackers, blocks, cache=None):
    """Sum of fight_group over all attackers; blocks maps attacker -> ordered blockers."""
    dead, to_player, att_gain, def_gain = set(), 0, 0, 0
    for a in attackers:
        bl = tuple(blocks.get(a, ()))
        key = (a, bl)
        if cache is not None and key in cache:
            r = cache[key]
        else:
            r = fight_group(a, bl)
            if cache is not None:
                cache[key] = r
        dead |= r[0]
        to_player += r[1]
        att_gain += r[2]
        def_gain += r[3]
    return dead, to_player, att_gain, def_gain


def combat_score(attackers, blocks, att: Player, dfn: Player, att_reach=0, def_reach=0, cache=None):
    """Value of a combat outcome from the attacker's side (the defender's is the negative)."""
    dead, to_player, att_gain, def_gain = simulate_combat(attackers, blocks, cache)
    def_life = dfn.life - to_player + def_gain
    att_life = att.life + att_gain
    if def_life <= 0:
        return LETHAL, dead, def_life
    score = (life_value(att_life - def_reach) - life_value(att.life - def_reach)
             - (life_value(def_life - att_reach) - life_value(dfn.life - att_reach)))
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
        need = getattr(perm.card, "min_blocker_power", 0) if perm is not None else 0
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
        lands = [c for c in me.hand if c.is_land]
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
            colors_needed = {k for c in me.hand if not c.is_land for k in c.mana_cost if k in "WUBRG"}
            have = {col for p in me.battlefield for col in p.card.produces}
            new_colors = len((card.produces - have) & colors_needed)
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

    def plan_spell(self, game: Game, me: Player, card: CardDef, precombat: bool = False):
        """Return (value, targets) if the AI wants to cast card in its main phase, else None."""
        opp = game.opponent(me)
        if card.is_permanent:
            if card.is_creature and precombat and "haste" not in card.keywords and not card.produces \
                    and any(_is_trick(c) for c in me.hand):
                return None  # keep mana open for the trick; cast it after combat
            return (card_value(card) + 0.5 * card.cmc + self._etb_value(game, me, card, precombat)
                    + self._static_value(game, me, card) - self._sac_cost(game, me, card), None)
        instant = card.instant_speed
        if getattr(card, "modes", None):
            # The engine picks modes and targets (choose_modes); value it the same way.
            if instant or not hasattr(engine, "_option_value"):
                return None
            v = engine._option_value(game, me, card)
            return (v, None) if v > 0 else None
        if not card.spell_effects:
            return None  # nothing we know how to do with it
        targets, value = [], 0.0
        for eff in card.spell_effects:
            if eff.kind == "pump" or eff.target == "spell" or _is_trick(card):
                return None  # tricks go in after_blocks / respond, counters in respond
            if eff.kind == "damage" and eff.target in ("any", "player", "creature", "creature_pw"):
                tgt, v = self.best_damage_target(game, me, eff, card, precombat or instant)
                if tgt is None:
                    return None
                if instant and tgt is not opp and v < LETHAL and not self._clears_blocker(game, me, tgt, precombat):
                    return None  # removal waits for their attack or end step
                targets.append(tgt)
                value += v
            elif eff.kind in ("destroy", "bounce", "debuff_one", "oring"):
                tgt = self.choose_target(game, me, eff, card)
                if tgt is None:
                    return None
                if instant and not self._clears_blocker(game, me, tgt, precombat):
                    return None
                targets.append(tgt)
                value += perm_value(tgt) + 1 if eff.kind != "bounce" else 0.5 * tgt.card.cmc + 1
            elif eff.kind in EXTRA_KINDS or (eff.kind == "p1_counters" and eff.target == "my_creatures"):
                got = self._extra_value(game, me, eff, card, precombat)
                if got is None:
                    return None
                targets.append(got[0])
                value += got[1]
            elif eff.kind in ("wrath", "debuff") or (eff.kind == "damage" and eff.target == "each_creature"):
                v = self.sweep_value(game, me, eff)
                # Under pressure any good sweep will do; otherwise wait until it takes out several cards.
                pressure = 2 * sum(combat_power(c) for c in opp.creatures) >= me.life
                if v <= (2.0 if pressure else SWEEP_BAR):
                    return None
                targets.append(None)
                value += v
            elif eff.kind in ("draw", "dig", "scry", "surveil"):
                if instant:
                    return None  # card draw at the opponent's end step
                targets.append(None)
                value += 1.5 * (eff.amount2 if eff.kind == "dig" else eff.amount) * \
                    (0.3 if eff.kind in ("scry", "surveil") else 1)
            elif eff.kind == "discard":
                targets.append(None)
                value -= 0.8 * eff.amount
            elif eff.kind == "gain_life":
                targets.append(None)
                value += life_value(me.life + eff.amount) - life_value(me.life)
            elif eff.kind == "lose_life":
                targets.append(None)
                value -= life_value(me.life) - life_value(me.life - eff.amount)
            elif eff.kind == "drain":
                targets.append(None)
                value += self.face_value(game, me, eff.amount, extra_reach=eff.amount)
            elif eff.kind == "token":
                targets.append(None)
                d = eff.data or {}
                value += max(1, eff.amount) * (1.0 + (d.get("power", 0) + d.get("toughness", 0)) / 2
                                               if "power" in d else MINOR_EFFECTS["treasure"])
            elif eff.kind == "p1_counters":
                tgt = self.choose_target(game, me, eff) if eff.target in engine.TARGETED else None
                if eff.target in engine.TARGETED and tgt is None:
                    return None
                targets.append(tgt)
                value += eff.amount
            elif eff.kind == "discard_choice":
                targets.append(opp if eff.target == "player" else None)
                value += 2.0 if opp.hand else -0.5
            elif eff.kind == "regrow":
                targets.append(None)
                value += max((card_value(c) for c in me.graveyard if c.is_creature), default=-1)
            elif eff.kind == "wrath_pw":
                targets.append(None)
                value += sum(perm_value(x) for x in getattr(opp, "planeswalkers", [])) - \
                    sum(perm_value(x) for x in getattr(me, "planeswalkers", []))
            elif eff.target in getattr(engine, "TARGETED", ()):
                tgt = self.choose_target(game, me, eff, card)
                if tgt is None:
                    return None
                targets.append(tgt)
                value += 1.0
            else:
                targets.append(None)
                value += MINOR_EFFECTS.get(eff.kind, 0.0) * max(1, eff.amount)
        return (value - self._sac_cost(game, me, card), targets)

    def _sac_cost(self, game: Game, me: Player, card: CardDef) -> float:
        """What the additional cost "sacrifice an artifact or creature" gives up (cheapest candidate)."""
        if not getattr(card, "extra_sacrifice", "") or not hasattr(game, "extra_sac_candidates"):
            return 0.0
        cands = game.extra_sac_candidates(me, card)
        if not cands:
            return 0.0      # pays the generic alternative instead (already in the cost)
        x = cands[0]
        return 0.5 if x.card.is_token and not x.is_creature else \
            (perm_value(x) if x.is_creature else 0.5 * x.card.cmc + 0.5)

    def _static_value(self, game: Game, me: Player, card: CardDef) -> float:
        """Static abilities card_value doesn't see: +1/+1 per artifact, extra land drops."""
        value = 0.0
        what = getattr(card, "pt_per", "")
        if what and card.is_creature:
            n = sum(1 for x in me.battlefield
                    if (x.is_creature if what == "creature" else what.capitalize() in x.card.types))
            value += n          # each +1/+1 is worth about 1 (half power, half toughness)
        if getattr(card, "extra_lands", 0) and any(c.is_land for c in me.hand if c is not card):
            value += 1.0
        if getattr(card, "lands_from_gy", False) and any(c.is_land for c in me.graveyard):
            value += 1.0
        return value

    def _extra_value(self, game: Game, me: Player, eff: Effect, card: CardDef, precombat: bool):
        """(target, value) for effects the main switch above has no case for, or None to hold."""
        opp = game.opponent(me)
        k = eff.kind
        ready = [c for c in me.creatures if c.can_attack() and c.power > 0]
        if k in copies.KINDS:
            v = copies.value(game, me, eff)
            return (None, v) if v > 0 else None
        if k == "tutor":
            return None, 2.0      # the best card of a kind, from the library
        if k == "explore":
            tgt = self.choose_target(game, me, eff, card) if eff.target == "creature_mine" else None
            if eff.target == "creature_mine" and tgt is None:
                return None
            return tgt, 1.2       # a land to hand, or a +1/+1 counter and a look at the top card
        if k == "oring_all":
            hit = lambda x: (x.is_creature or x.card.is_artifact) and x.card.cmc <= eff.amount
            v = sum(perm_value(x) for x in opp.battlefield if hit(x)) - \
                sum(perm_value(x) for x in me.battlefield if hit(x))
            return (None, v) if v > 0 else None
        if k == "pump_all":
            # A team pump matters for this turn's attack: before combat, with attackers ready.
            if not precombat or not ready:
                return None
            kw = 0.5 if (eff.data or {}).get("keyword") else 0.0
            return None, len(ready) * (0.5 * (eff.amount + eff.amount2) + kw)
        if k in ("p1_counters", "double_counters") and eff.target == "my_creatures":
            if not me.creatures:
                return None
            each = eff.amount if k == "p1_counters" else 0.5
            return None, len(me.creatures) * each
        if k in ("tap", "stun"):
            tgt = self.choose_target(game, me, eff, card)
            if tgt is None and eff.target in engine.TARGETED:
                return None
            return tgt, 0.5 * eff.amount if k == "stun" else 0.5
        if k == "mill":
            return None, 0.1 * eff.amount
        if k == "earthbend":
            # A land becomes an N/N haste creature (0/0 plus N +1/+1 counters) that stays a land.
            if not any(p.card.is_land for p in me.battlefield):
                return None
            return None, 1.0 + 0.75 * eff.amount
        if k == "unblockable":
            # Only before combat, and only when a blocker would otherwise stop the attack.
            tgt = self.choose_target(game, me, eff, card)
            if not precombat or tgt is None or not any(can_block(b, tgt) for b in opp.creatures):
                return None
            return tgt, 0.5 * combat_power(tgt)
        return None, 0.0

    def _etb_value(self, game: Game, me: Player, card: CardDef, precombat: bool) -> float:
        """Extra value of a permanent's enters-the-battlefield removal, tutor or explore."""
        # Mirrors Game.enter_battlefield: etb_effects only fire on a card without an etb trigger.
        effects = [e for t in card.triggers if t.event == "etb" for e in t.effects] or list(card.etb_effects)
        value = 0.0
        for eff in effects:
            if eff.kind == "oring":
                tgt = self.choose_target(game, me, eff, card)
                value += perm_value(tgt) if tgt is not None else 0.0
            # An earthbend ETB is left to card_value: valuing it on top made the landfall deck
            # cast Earthbender Ascension ahead of creatures and lose (47% vs the previous AI).
            elif eff.kind in EXTRA_KINDS and eff.kind != "earthbend" and eff.target in ("none", "self", "my_creatures"):
                got = self._extra_value(game, me, eff, card, precombat)
                value += got[1] if got is not None else 0.0
        for t in card.triggers:      # "When ~ enters, choose one —"
            if t.event == "etb" and t.modes:
                value += max(0.0, modal.value(game, me, t.modes, least=0))
        return value

    def _clears_blocker(self, game: Game, me: Player, tgt, precombat: bool) -> bool:
        """Is it worth using instant removal on tgt in our own main phase (to attack past it)?"""
        if not precombat or not isinstance(tgt, Permanent):
            return False
        ready = [c for c in me.creatures if c.can_attack() and c.power > 0]
        return any(can_block(tgt, a) and not tgt.tapped for a in ready)

    def sweep_value(self, game: Game, me: Player, eff: Effect) -> float:
        opp = game.opponent(me)

        def hit(c):
            if eff.kind == "wrath":
                return not c.has("indestructible")
            return c.toughness - c.damage <= eff.amount2 if eff.kind == "debuff" else \
                c.toughness - c.damage <= eff.amount
        mine = 0.0 if eff.target == "opp_creatures" else sum(card_value(c.card) for c in me.creatures if hit(c))
        theirs = sum(card_value(c.card) for c in opp.creatures if hit(c))
        return theirs - mine

    def best_damage_target(self, game: Game, me: Player, eff: Effect, card: CardDef, precombat: bool):
        """(target, value) for a damage effect, or (None, 0) to hold the spell."""
        opp = game.opponent(me)
        face = None
        if eff.target in ("any", "player"):
            face = self.face_value(game, me, eff.amount, extra_reach=face_burn(card))
            if face >= LETHAL:
                return opp, face
        best_kill, kill_val = None, 0.0
        if eff.target in CREATURE_TARGETS:
            for c in opp.creatures:
                if c.toughness - c.damage <= eff.amount and _legal(game, me, eff, c, card) \
                        and not c.has("indestructible"):
                    v = perm_value(c) + 0.5
                    if v > kill_val:
                        best_kill, kill_val = c, v
        if eff.target in ("any", "creature_pw"):
            for pw in getattr(opp, "planeswalkers", []):
                if not pw.is_creature and pw.loyalty <= eff.amount and _legal(game, me, eff, pw, card):
                    v = perm_value(pw) + 0.5
                    if v > kill_val:
                        best_kill, kill_val = pw, v
        if best_kill is not None and (face is None or kill_val >= face):
            return best_kill, kill_val
        if face is None:
            return None, 0.0
        if precombat:
            return None, 0.0   # face burn waits until after combat (or the opponent's end step)
        hold = HOLD_BURN if eff.target == "any" else 0.0
        if face < hold and len(me.hand) <= 6:
            return None, 0.0
        return opp, face

    def choose_target(self, game: Game, me: Player, eff: Effect, card: CardDef | None = None):
        opp = game.opponent(me)
        if eff.kind == "damage":
            if eff.target in ("any", "player", "creature", "creature_pw"):
                tgt, _ = self.best_damage_target(game, me, eff, card or CardDef("", {}, 0, frozenset()), False)
                if tgt is not None or eff.target in ("creature", "creature_pw"):
                    return tgt
                return opp
            return None
        if eff.kind in ("destroy", "bounce", "debuff_one", "oring", "tap", "stun"):
            pool = opp.creatures + [x for x in getattr(opp, "planeswalkers", []) if not x.is_creature]
            if eff.target == "nonland_perm":
                pool = [x for x in opp.battlefield if not x.card.is_land or x.is_creature]
            elif eff.target == "artifact":
                pool = [x for x in opp.battlefield if getattr(x.card, "is_artifact", False)]
            if eff.kind in ("tap", "stun"):
                pool = [c for c in opp.creatures if not c.tapped or eff.kind == "stun"]
            legal = [c for c in pool if _legal(game, me, eff, c, card)
                     and not (eff.kind == "destroy" and c.has("indestructible"))
                     and not (eff.kind == "debuff_one" and c.toughness - c.damage > eff.amount2)]
            return max(legal, key=perm_value, default=None)
        if eff.kind in ("pump", "p1_counters", "explore"):
            mine = [c for c in me.creatures if _legal(game, me, eff, c)]
            return max(mine, key=perm_value, default=None)
        if hasattr(engine, "default_choose_target"):
            return engine.default_choose_target(game, me, eff)
        return None

    # ------------------------------------------------------------- responses
    def respond(self, game: Game, me: Player):
        """Priority with something on the stack, or in an empty-stack window.
        Returns (card, targets) or None to pass."""
        options = [c for c in _spell_options(game, me) if c.instant_speed and game.can_cast_now(me, c)
                   and not getattr(c, "modes", None)]   # modal instants: engine.respond_extras
        if not options:
            return None
        if game.stack:
            top = game.stack[-1]
            if top.controller is me:
                return None
            return self.save_creature(game, me, top, options) or self.counter(game, me, top, options)
        if me is game.active:
            return None  # our own turn: main phases and after_blocks handle it
        if game.step == "declare_attackers":
            return self.kill_attacker(game, me, options)
        if game.step == "declare_blockers":
            return self.defensive_trick(game, me, options)
        if game.step == "end_step":
            return self.end_of_turn(game, me, options)
        return None

    def threat(self, game: Game, me: Player, item) -> float:
        """How much an opponent's spell or ability on the stack would cost us."""
        value = 0.0
        card = item.card
        if card is not None and card.is_permanent:
            value += card_value(card) if card.is_creature else card.cmc
            for t in getattr(card, "triggers", []):
                if t.event == "etb":
                    value += sum(self._effect_harm(game, me, e, None) for e in t.effects)
        for eff, tgt in zip(item.effects, item.targets):
            value += self._effect_harm(game, me, eff, tgt)
        return value

    def _effect_harm(self, game: Game, me: Player, eff: Effect, tgt) -> float:
        opp = game.opponent(me)
        if eff.kind in ("destroy", "bounce") and tgt is None:
            tgt = max(me.creatures, key=perm_value, default=None)  # an ETB that will pick a target
        if eff.kind == "destroy" and isinstance(tgt, Permanent) and tgt.controller is me:
            return perm_value(tgt) + 1
        if eff.kind == "bounce" and isinstance(tgt, Permanent) and tgt.controller is me:
            return 0.5 * tgt.card.cmc + 1
        if eff.kind == "damage":
            if tgt is me:
                if eff.amount >= me.life:
                    return LETHAL
                return life_value(me.life) - life_value(me.life - eff.amount)
            if isinstance(tgt, Permanent) and tgt.controller is me and tgt.toughness - tgt.damage <= eff.amount:
                return perm_value(tgt) + 1
            if eff.target == "each_creature":
                return sum(card_value(c.card) for c in me.creatures if c.toughness - c.damage <= eff.amount) - \
                    sum(card_value(c.card) for c in opp.creatures if c.toughness - c.damage <= eff.amount)
        if eff.kind == "wrath":
            return sum(card_value(c.card) for c in me.creatures) - sum(card_value(c.card) for c in opp.creatures)
        if eff.kind == "debuff":
            mine = sum(card_value(c.card) for c in me.creatures if c.toughness - c.damage <= eff.amount2)
            if eff.target == "opp_creatures":
                return mine
            return mine - sum(card_value(c.card) for c in opp.creatures if c.toughness - c.damage <= eff.amount2)
        if eff.kind in ("draw", "dig"):
            return 1.5 * (eff.amount2 if eff.kind == "dig" else eff.amount)
        if eff.kind in ("drain", "lose_life") and eff.target != "none":
            return life_value(me.life) - life_value(me.life - eff.amount)
        if eff.kind == "counter" and tgt is not None and getattr(tgt, "controller", None) is me:
            return self.threat(game, opp, tgt) + 1   # they are countering our spell
        return 0.0

    def save_creature(self, game: Game, me: Player, item, options):
        """Answer removal aimed at a creature of ours with hexproof, or pump it out of damage."""
        for eff, tgt in zip(item.effects, item.targets):
            if not isinstance(tgt, Permanent) or tgt.controller is not me or perm_value(tgt) < 2.5:
                continue
            lethal_damage = eff.kind == "damage" and tgt.toughness - tgt.damage <= eff.amount
            if not (lethal_damage or eff.kind in ("destroy", "bounce", "debuff_one")):
                continue
            for card in options:
                boost = _boost(card)
                if _gives_hexproof(card):
                    first = next((e for e in card.spell_effects if e.target in ("creature_mine", "creature")), None)
                    if first is not None:
                        return card, _aim(card, first, tgt)
                if lethal_damage and boost and tgt.toughness - tgt.damage + boost[2] > eff.amount:
                    return card, _aim(card, boost[0], tgt)
        return None

    def counter(self, game: Game, me: Player, item, options):
        if not item.is_spell or not game.counterable(item):
            return None
        opp = game.opponent(me)
        counters = []
        for card in options:
            effs = [e for e in card.spell_effects if e.kind == "counter"]
            if not effs or not all(game.can_counter(e, item, me) for e in effs):
                continue
            tax = max(e.amount for e in effs)
            if tax and payable(game.mana_sources(opp), {"generic": tax}):
                continue   # they would just pay
            counters.append(card)
        if not counters:
            return None
        threat = self.threat(game, me, item)
        # Spend a counter on anything that matters; be pickier while they hold more cards.
        bar = 3.0 + (1.5 if len(opp.hand) >= 3 else 0.0)
        if threat < bar:
            return None
        card = min(counters, key=lambda c: (c.cmc, card_value(c)))
        return card, [item if e.target == "spell" else None for e in card.spell_effects]

    def _removal_on(self, game: Game, me: Player, card: CardDef, pool):
        """(value, targets) for using removal card on the best creature in pool."""
        targets, value = [], 0.0
        for eff in card.spell_effects:
            if eff.kind in ("destroy", "bounce") or (eff.kind == "damage" and eff.target in CREATURE_TARGETS):
                legal = [c for c in pool if _legal(game, me, eff, c, card)
                         and not (eff.kind != "bounce" and c.has("indestructible"))
                         and (eff.kind != "damage" or c.toughness - c.damage <= eff.amount)]
                tgt = max(legal, key=perm_value, default=None)
                if tgt is None:
                    return None
                targets.append(tgt)
                value += perm_value(tgt) + (0.5 if eff.kind == "bounce" else 1)
                if eff.kind == "bounce":
                    value -= 0.5 * card_value(tgt.card)
            elif eff.kind == "lose_life":
                targets.append(None)
                value -= life_value(me.life) - life_value(me.life - eff.amount)
            elif eff.target in ("any", "creature", "player", "spell"):
                return None
            else:
                targets.append(None)
        return value, targets

    def kill_attacker(self, game: Game, me: Player, options):
        opp = game.opponent(me)
        attackers = [a for a in game.attackers if a in opp.battlefield]
        incoming = sum(combat_power(a) for a in attackers)
        best = None
        for card in options:
            if card.is_creature:
                continue
            plan = self._removal_on(game, me, card, attackers)
            if plan is None:
                continue
            value = plan[0]
            if any(e.kind == "damage" and e.target == "any" for e in card.spell_effects):
                value -= self.face_value(game, me, max(e.amount for e in card.spell_effects
                                                       if e.kind == "damage"), 0) * 0.5
            if incoming >= me.life:
                value += 10
            if value >= REMOVAL_BAR and (best is None or value > best[0]):
                best = (value, card, plan[1])
        return (best[1], best[2]) if best else None

    def defensive_trick(self, game: Game, me: Player, options):
        opp = game.opponent(me)
        blocks = {a: [b for b in bl if b in me.battlefield] for a, bl in game.blocks.items()
                  if a in opp.battlefield}
        attackers = [a for a in game.attackers if a in opp.battlefield]
        if not blocks:
            return None
        base = combat_score(attackers, blocks, opp, me)[0]
        best = None
        for card in options:
            boost = _boost(card)
            if boost is None:
                continue
            _, dp, dt = boost
            for b in {b for bl in blocks.values() for b in bl}:
                b.pump_p += dp
                b.pump_t += dt
                gain = base - combat_score(attackers, blocks, opp, me)[0]
                b.pump_p -= dp
                b.pump_t -= dt
                if gain > 1.5 and (best is None or gain > best[0]):
                    best = (gain, card, b)
        if best is None:
            return None
        _, card, b = best
        return card, _aim(card, _boost(card)[0], b)

    def end_of_turn(self, game: Game, me: Player, options):
        """Opponent's end step: our mana untaps next, so use it on removal, burn, flash, draw."""
        opp = game.opponent(me)
        best = None
        for card in options:
            if card.is_creature:
                value, targets = card_value(card), None
            elif _is_trick(card) or any(e.target == "spell" for e in card.spell_effects):
                continue
            elif all(e.kind in ("draw", "dig", "scry", "surveil", "discard", "gain_life") for e in card.spell_effects):
                plan = self.plan_spell(game, me, CardDef(card.name, card.mana_cost, card.cmc,
                                                         card.types - {"Instant"} | {"Sorcery"},
                                                         spell_effects=card.spell_effects), False)
                if plan is None:
                    continue
                value, targets = plan
            elif any(e.kind == "damage" and e.target in ("any", "player") for e in card.spell_effects):
                eff = next(e for e in card.spell_effects if e.kind == "damage")
                tgt, value = self.best_damage_target(game, me, eff, card, False)
                if tgt is None:
                    continue
                targets = [tgt if e is eff else None for e in card.spell_effects]
            else:
                plan = self._removal_on(game, me, card, opp.creatures)
                if plan is None or plan[0] < REMOVAL_BAR:
                    continue
                value, targets = plan
            if value > 0 and (best is None or value > best[0]):
                best = (value, card, targets)
        return (best[1], best[2]) if best else None

    # -------------------------------------------------------- planeswalkers
    def use_abilities(self, game: Game, me: Player):
        """Loyalty abilities by our own policy, then the engine's defaults for everything else."""
        skipped = []
        for pw in list(me.planeswalkers):
            if pw.loyalty_used or game.over or pw not in me.battlefield:
                continue
            idx = self.choose_loyalty(game, me, pw)
            if idx is None or not game.activate_loyalty(me, pw, idx):
                pw.loyalty_used = True    # so the engine default doesn't pick one for it
                skipped.append(pw)
        try:
            if not game.over:
                engine.use_abilities(game, me)
        finally:
            for pw in skipped:
                pw.loyalty_used = False

    def choose_loyalty(self, game: Game, me: Player, pw: Permanent):
        """Index of the loyalty ability to use, or None. Each ability is worth its effect plus
        keeping the planeswalker: a + ability that leaves it out of reach of the opponent's
        attackers beats a - ability that gets it killed, and a walker that dies anyway uses its
        best effect while it can."""
        opp = game.opponent(me)
        best, best_score = None, -1e9
        for i, (cost, effects) in enumerate(pw.card.loyalty_abilities):
            after = pw.loyalty + cost
            if after < 0:
                continue
            value = engine._mode_value(game, me, effects)
            if value < 0:
                continue
            score = value
            if after > 0 and after > self._pw_danger(game, me, opp, effects):
                score += PW_KEEP + 0.5 * after
            if cost <= -7:
                score += 20   # an ultimate usually wins the game
            if score > best_score:
                best, best_score = i, score
        return best

    def _pw_danger(self, game: Game, me: Player, opp: Player, effects) -> int:
        """Damage the opponent's creatures could put on our planeswalker next turn, after effects."""
        gone, tokens = set(), []
        for e in effects:
            if e.kind in ("destroy", "bounce", "damage", "debuff_one") and e.target in engine.TARGETED:
                tgt = engine.default_choose_target(game, me, e)
                if isinstance(tgt, Permanent) and (e.kind != "damage" or tgt.toughness - tgt.damage <= e.amount):
                    gone.add(tgt)
            elif e.kind == "wrath":
                gone |= set(opp.creatures)
            elif e.kind == "token" and "power" in (e.data or {}):
                d = e.data
                fly = "flying" in d.get("keywords", ())
                tokens += [(d["power"], fly, "reach" in d.get("keywords", ()), None)] * max(1, e.amount)
        theirs = [(combat_power(c), c.has("flying"), c.has("menace"), c) for c in opp.creatures
                  if c not in gone and not c.has("defender") and c.power > 0]
        if not theirs:
            return 0
        mine = [(c.power, c.has("flying"), c.has("reach"), c) for c in me.creatures if c not in gone]
        return unblocked_damage(theirs, mine + tokens, chump=True)

    # ---------------------------------------------------------------- combat
    def _pending_blockers(self, game: Game, me: Player):
        """A creature in hand we could still cast this turn, as (power, flying, reach, None)."""
        for c in me.hand:
            if c.is_creature and game.can_pay(me, self._cost(game, me, c)):
                return [(c.power or 0, "flying" in c.keywords, "reach" in c.keywords, None)]
        return []

    def crack_back(self, game: Game, me: Player, opp: Player, my_untapped, their_creatures, my_life):
        """Penalty for what the opponent can hit us for next turn."""
        crew_power = sum(c.power for c in their_creatures)
        vehicles = [v for v in opp.battlefield if getattr(v.card, "crew", 0) and not v.is_creature
                    and crew_power >= v.card.crew and v not in their_creatures]
        theirs = [(combat_power(c), c.has("flying"), c.has("menace"), c) for c in their_creatures + vehicles
                  if not c.has("defender") and c.power > 0]
        if not theirs:
            return 0.0
        mine = [(c.power, c.has("flying"), c.has("reach"), c) for c in my_untapped]
        mine += self._pending_blockers(game, me)
        worst = unblocked_damage(theirs, mine, chump=True)
        if worst >= my_life:
            return LETHAL / 2
        likely = unblocked_damage(theirs, [m for m in mine if m[3] is not None], chump=False)
        likely = min(likely, my_life - 1)
        return CRACK_WEIGHT * (life_value(my_life) - life_value(my_life - likely))

    def score_attack(self, game, me, opp, attack, my_reach, cache):
        blockers = [c for c in opp.creatures if not c.tapped]
        blocks = search_blocks(attack, blockers, me, opp, 0, 0, cache) if attack else {}
        score, dead, opp_life = combat_score(attack, blocks, me, opp, my_reach, 0, cache)
        if score >= LETHAL:
            return score
        if my_reach >= opp_life:
            return LETHAL * 0.9   # burn in hand finishes them after combat
        my_untapped = [c for c in me.creatures
                       if c not in dead and (c not in attack or c.has("vigilance"))]
        their = [c for c in opp.creatures if c not in dead]
        return score - self.crack_back(game, me, opp, my_untapped, their, me.life)

    def choose_attackers(self, game: Game, me: Player, opp: Player) -> list[Permanent]:
        ready = [c for c in me.creatures if c.can_attack() and c.power > 0]
        if not ready:
            return []
        my_reach = reach(me)
        cache, fights = {}, {}

        def score(attack):
            key = frozenset(attack)
            if key not in cache:
                cache[key] = self.score_attack(game, me, opp, list(attack), my_reach, fights)
            return cache[key]

        def preference(attack):
            value = score(attack)
            if value < LETHAL * 0.9:
                return value, 0, 0, -len(attack)
            # Lethal/reach scores saturate. Among tied plans, first preserve
            # material and blockers in case interaction stops the kill, then
            # prefer more damage (redundancy against removal or failed reach).
            # No hidden-hand inspection and no incentive to sacrifice blockers
            # merely to increase overkill.
            blocks = search_blocks(attack, [c for c in opp.creatures if not c.tapped],
                                   me, opp, 0, 0, fights) if attack else {}
            dead, damage, gain, _ = simulate_combat(attack, blocks, fights)
            untapped = [c for c in me.creatures if c not in dead and not c.tapped
                        and (c not in attack or c.has("vigilance"))]
            exposure = sum(perm_value(c) for c in dead if c.controller is me)
            exposure += self.crack_back(game, me, opp, untapped,
                                        [c for c in opp.creatures if c not in dead], me.life + gain)
            return value, -exposure, damage, -len(attack)

        if len(ready) <= MAX_ENUMERATE:
            subsets = [[c for i, c in enumerate(ready) if mask >> i & 1] for mask in range(1 << len(ready))]
            best = max(score(s) for s in subsets)
            return max((s for s in subsets if score(s) == best), key=preference)
        current = max([[], list(ready)], key=preference)
        improved = True
        while improved:
            improved = False
            for c in ready:
                trial = [x for x in current if x is not c] if c in current else current + [c]
                if preference(trial) > preference(current):
                    current, improved = trial, True
        return current

    def choose_blocks(self, game: Game, me: Player, opp: Player, attackers) -> dict:
        return search_blocks(attackers, me.creatures, opp, me, 0, reach(me))

    def after_blocks(self, game: Game, me: Player, attackers, blocks):
        """Use pump spells where they win a fight or deal the last points of damage."""
        opp = game.opponent(me)
        for card in [c for c in me.hand if _is_trick(c) and _boost(c)]:
            if card not in me.hand or not self._can_cast(game, me, card):
                continue
            eff, dp, dt = _boost(card)
            live = [a for a in attackers if a in me.battlefield]
            live_blocks = {a: [b for b in bl if b in opp.battlefield] for a, bl in blocks.items() if a in live}
            base = combat_score(live, live_blocks, me, opp)[0]
            best, target = 1.5, None   # a trick should gain more than a card's worth
            for a in live:
                a.pump_p += dp
                a.pump_t += dt
                gain = combat_score(live, live_blocks, me, opp)[0] - base
                a.pump_p -= dp
                a.pump_t -= dt
                if gain > best:
                    best, target = gain, a
            if target is not None:
                game.cast(me, card, _aim(card, eff, target))


class BaselineAI:
    """The original simple player, kept for before/after comparisons. It has no respond
    hook, so the engine's default_respond plays its instants on the opponent's turn."""

    def keep_hand(self, hand: list[CardDef], mulligans: int) -> bool:
        lands = sum(c.is_land for c in hand)
        return 2 <= lands <= 5 or mulligans >= 2

    def cards_to_bottom(self, hand: list[CardDef], n: int) -> list[CardDef]:
        out, hand = [], list(hand)
        for _ in range(n):
            lands = [c for c in hand if c.is_land]
            spells = [c for c in hand if not c.is_land]
            pick = (max(spells, key=lambda c: c.cmc) if spells and len(lands) >= 3 or not lands
                    else lands[0])
            hand.remove(pick)
            out.append(pick)
        return out

    def choose_discard(self, game: Game, me: Player) -> CardDef:
        lands_out = sum(p.card.is_land for p in me.battlefield)
        lands = [c for c in me.hand if c.is_land]
        if lands and lands_out >= 5:
            return lands[0]
        spells = [c for c in me.hand if not c.is_land]
        return max(spells or me.hand, key=lambda c: c.cmc)

    def main_phase(self, game: Game, me: Player):
        HeuristicAI.play_land(self, game, me)
        while not game.over:
            best = None
            for card in {c.name: c for c in me.hand if not c.is_land}.values():
                if not game.can_pay(me, HeuristicAI._cost(game, me, card)):
                    continue
                plan = self.plan_spell(game, me, card)
                if plan is None:
                    continue
                if best is None or plan[0] > best[0]:
                    best = (plan[0], card, plan[1])
            if best is None:
                return
            game.cast(me, best[1], best[2])

    def plan_spell(self, game: Game, me: Player, card: CardDef):
        if card.is_permanent:
            return (10 * card.cmc + card_value(card), None)
        targets, score = [], 10 * card.cmc
        for eff in card.spell_effects:
            if eff.kind == "pump" or eff.target == "spell":
                return None
            if eff.target in ("any", "creature", "player"):
                tgt = self.choose_target(game, me, eff)
                if tgt is None:
                    return None
                targets.append(tgt)
                score += 1000 if tgt is game.opponent(me) and eff.amount >= tgt.life else 0
                score += 10 * perm_value(tgt) if isinstance(tgt, Permanent) else 0
            else:
                targets.append(None)
        if not card.spell_effects:
            return None
        return (score, targets)

    def choose_target(self, game: Game, me: Player, eff: Effect):
        opp = game.opponent(me)
        if eff.kind == "damage":
            if eff.target == "player":
                return opp
            if eff.target == "any" and eff.amount >= opp.life:
                return opp
            killable = [c for c in opp.creatures if c.toughness - c.damage <= eff.amount]
            if killable:
                return max(killable, key=perm_value)
            return opp if eff.target == "any" else None
        if eff.kind == "destroy":
            return max(opp.creatures, key=perm_value, default=None)
        if eff.kind == "pump":
            return max(me.creatures, key=perm_value, default=None)
        return None

    def choose_attackers(self, game: Game, me: Player, opp: Player) -> list[Permanent]:
        ready = [c for c in me.creatures if c.can_attack()]
        if not ready:
            return []
        blockers = [c for c in opp.creatures if not c.tapped]
        powers = sorted((combat_power(c) for c in ready), reverse=True)
        if sum(powers[len(blockers):]) >= opp.life:
            return ready
        attackers = []
        for a in ready:
            can = [b for b in blockers if can_block(b, a)]
            safe = all(not fight(a, b)[0] or (fight(a, b)[1] and perm_value(b) >= perm_value(a))
                       for b in can)
            if safe:
                attackers.append(a)

        def crack_back(kept):
            theirs = sorted((combat_power(c) for c in opp.creatures), reverse=True)
            return sum(theirs[len(kept):])

        kept = [c for c in me.creatures if c not in attackers or c.has("vigilance")]
        while attackers and crack_back(kept) >= me.life:
            back = max((a for a in attackers if not a.has("vigilance")), key=lambda c: c.toughness, default=None)
            if back is None:
                break
            attackers.remove(back)
            kept.append(back)
        return attackers

    def choose_blocks(self, game: Game, me: Player, opp: Player, attackers) -> dict:
        avail = [c for c in me.creatures if not c.tapped]
        blocks = {}
        for a in sorted(attackers, key=combat_power, reverse=True):
            if a.has("menace"):
                continue
            cands = [b for b in avail if can_block(b, a)]
            good = [b for b in cands if fight(a, b) == (True, False)]
            safe = [b for b in cands if not fight(a, b)[1]]
            trade = [b for b in cands if fight(a, b) == (True, True) and perm_value(a) >= perm_value(b)]
            pick = next((min(group, key=perm_value) for group in (good, safe, trade) if group), None)
            if pick:
                blocks[a] = [pick]
                avail.remove(pick)

        def incoming():
            return sum(combat_power(a) for a in attackers if a not in blocks)

        for a in sorted((a for a in attackers if a not in blocks and not a.has("menace")),
                        key=combat_power, reverse=True):
            if incoming() < me.life:
                break
            cands = [b for b in avail if can_block(b, a)]
            if cands and not a.has("trample"):
                chump = min(cands, key=perm_value)
                blocks[a] = [chump]
                avail.remove(chump)
        return blocks

    def after_blocks(self, game: Game, me: Player, attackers, blocks):
        opp = game.opponent(me)
        for card in [c for c in me.hand if c.is_instant and any(e.kind == "pump" for e in c.spell_effects)]:
            if card not in me.hand or not game.can_pay(me, card.mana_cost):
                continue
            eff = next(e for e in card.spell_effects if e.kind == "pump")
            target = None
            unblocked = sum(combat_power(a) for a in attackers if a not in blocks and a in me.battlefield)
            for a, bl in blocks.items():
                if a not in me.battlefield or len(bl) != 1:
                    continue
                before = fight(a, bl[0])
                a.pump_p += eff.amount
                a.pump_t += eff.amount2
                after = fight(a, bl[0])
                a.pump_p -= eff.amount
                a.pump_t -= eff.amount2
                if (before[0] and not after[0]) or (not before[1] and after[1]):
                    target = a
                    break
            if target is None and unblocked and unblocked + eff.amount >= opp.life:
                target = next(a for a in attackers if a not in blocks and a in me.battlefield)
            if target is not None:
                game.cast(me, card, [target if e.kind == "pump" else None for e in card.spell_effects])
