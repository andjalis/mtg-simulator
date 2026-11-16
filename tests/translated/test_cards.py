"""Verification scenarios for per-card translations (mtgsim.translated), one class per card.

Each class docstring states, from the Oracle text alone and before the translation was written or run, the
observable outcome the test asserts. The tests drive the real engine with a fixed seed.
"""
import unittest
from unittest import mock

from tests.translated.harness import DB_FILE, Scenario, smoke, vanilla


def smoke_ok(test, name, hostile=True, used=True, **kw):
    """HeuristicAI plays the card without errors (and, when hostile, never aims hostile effects at itself)."""
    res = smoke(name, **kw)
    test.assertEqual(res["errors"], [], name)
    if used:
        test.assertTrue(res["uses"], f"{name}: the AI never used the card's effects in {res['games']} games")
    if hostile:
        test.assertEqual(res["hostile_at_self"], [], name)
    return res


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class swarming_goblins(Scenario):
    """ETB: roll a d20. 1-9: one 1/1 red Goblin; 10-19: two; 20: three."""
    def run_roll(self, face):
        self.translated("Swarming Goblins")
        with mock.patch.object(self.game.rng, "randint", return_value=face):
            self.enter("Swarming Goblins")
        return [x for x in self.a.creatures if x.card.is_token and "Goblin" in x.card.name]

    def test_15_makes_two(self):
        gob = self.run_roll(15)
        self.assertEqual(len(gob), 2)
        self.assertEqual((gob[0].power, gob[0].toughness), (1, 1))

    def test_20_makes_three(self):
        self.assertEqual(len(self.run_roll(20)), 3)

    def test_5_makes_one(self):
        self.assertEqual(len(self.run_roll(5)), 1)

    def test_ai(self):
        smoke_ok(self, "Swarming Goblins", hostile=False)


DEMON = vanilla("Test Demon", 5, 5, "{3}{B}{B}", "Creature — Demon")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class raving_oni_slave(Scenario):
    """When it enters or leaves: you lose 3 life unless you control a Demon (checked on resolution)."""
    def test_enters_without_demon(self):
        self.translated("Raving Oni-Slave")
        self.enter("Raving Oni-Slave")
        self.assertEqual(self.a.life, 17)

    def test_enters_with_demon(self):
        self.put(DEMON)
        self.enter("Raving Oni-Slave")
        self.assertEqual(self.a.life, 20)

    def test_leaves_without_demon(self):
        x = self.enter("Raving Oni-Slave")
        self.game.destroy(x)
        self.game.settle()
        self.assertEqual(self.a.life, 14)
        self.assertEqual(self.b.life, 20)

    def test_ai(self):
        smoke_ok(self, "Raving Oni-Slave", hostile=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class guildsworn_prowler(Scenario):
    """Dies outside combat: its controller draws a card. Dies while blocking: no card."""
    def test_dies_in_main_phase_draws(self):
        self.translated("Guildsworn Prowler")
        x = self.put("Guildsworn Prowler")
        hand = len(self.a.hand)
        self.game.destroy(x)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_dies_blocking_no_draw(self):
        x = self.put("Guildsworn Prowler")
        att = self.put(vanilla("Big", 4, 4), self.b)
        hand = len(self.a.hand)
        self.game.active_idx = 1
        self.game.attackers = [att]
        self.game.blocks = {att: [x]}
        self.game.combat_damage(self.b, self.a, [att], {att: [x]}, lambda c: True)
        self.game.settle()
        self.assertNotIn(x, self.a.battlefield)
        self.assertEqual(len(self.a.hand), hand)

    def test_dies_attacking_draws(self):
        x = self.put("Guildsworn Prowler")
        blk = self.put(vanilla("Big", 4, 4), self.b)
        hand = len(self.a.hand)
        self.game.attackers = [x]
        self.game.blocks = {x: [blk]}
        self.game.combat_damage(self.a, self.b, [x], {x: [blk]}, lambda c: True)
        self.game.settle()
        self.assertNotIn(x, self.a.battlefield)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_ai(self):
        smoke_ok(self, "Guildsworn Prowler", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class oni_cult_anvil(Scenario):
    """During your turn, an artifact you control leaving makes one 1/1 colorless Construct artifact creature
    token, at most once per turn; on the opponent's turn nothing."""
    def constructs(self):
        return [x for x in self.a.battlefield if x.card.is_token and "Construct" in x.card.name]

    def test_your_turn_once(self):
        self.translated("Oni-Cult Anvil")
        self.put("Oni-Cult Anvil")
        rocks = [self.put(vanilla("Rock", 0, 0, "{1}", "Artifact")) for _ in range(2)]
        for r in rocks:
            self.game.destroy(r)
            self.game.settle()
        c = self.constructs()
        self.assertEqual(len(c), 1)
        self.assertTrue(c[0].card.is_artifact and c[0].is_creature)
        self.assertEqual((c[0].power, c[0].toughness), (1, 1))

    def test_opponents_turn_nothing(self):
        self.put("Oni-Cult Anvil")
        rock = self.put(vanilla("Rock", 0, 0, "{1}", "Artifact"))
        self.game.active_idx = 1
        self.game.destroy(rock)
        self.game.settle()
        self.assertEqual(self.constructs(), [])

    def test_ai(self):
        smoke_ok(self, "Oni-Cult Anvil", used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class bellowing_elk(Scenario):
    """Has trample and indestructible only if ANOTHER creature entered under your control this turn."""
    def test_alone_entering_no_keywords(self):
        self.translated("Bellowing Elk")
        elk = self.enter("Bellowing Elk")
        self.assertFalse(elk.has("trample"))
        self.assertFalse(elk.has("indestructible"))

    def test_another_creature_entered(self):
        elk = self.enter("Bellowing Elk")
        self.enter(vanilla())
        self.assertTrue(elk.has("trample"))
        self.assertTrue(elk.has("indestructible"))

    def test_old_elk_new_creature(self):
        elk = self.put("Bellowing Elk")
        elk.entered_turn = 0
        self.assertFalse(elk.has("trample"))
        self.enter(vanilla())
        self.assertTrue(elk.has("indestructible"))

    def test_ai(self):
        smoke_ok(self, "Bellowing Elk", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class homarid_warrior(Scenario):
    """{U}: it gains shroud until end of turn, becomes tapped, and stays tapped through your next untap step."""
    def test_activate(self):
        self.translated("Homarid Warrior")
        x = self.put("Homarid Warrior")
        self.lands("U")
        self.assertTrue(self.activate(x, 0))
        self.assertTrue(x.has("shroud"))
        self.assertTrue(x.tapped)
        self.game.untap_step(self.a)
        self.assertTrue(x.tapped)

    def test_ai(self):
        smoke_ok(self, "Homarid Warrior", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class mirkwood_bats(Scenario):
    """Whenever you create a token, and whenever you sacrifice a token: each opponent loses 1 life (you don't
    gain any)."""
    def test_create_token(self):
        self.translated("Mirkwood Bats")
        self.put("Mirkwood Bats")
        self.lands("W1")
        self.assertTrue(self.cast(self.get("Raise the Alarm")))        # two 1/1 Soldier tokens
        self.assertEqual(self.b.life, 18)
        self.assertEqual(self.a.life, 20)

    def test_sacrifice_token(self):
        self.put("Mirkwood Bats")
        tok = self.put(vanilla("Soldier", 1, 1, "", "Token Creature — Soldier"))
        tok.card.is_token = True
        self.game.sacrifice(tok)
        self.game.settle()
        self.assertEqual(self.b.life, 19)

    def test_opponent_token_nothing(self):
        self.put("Mirkwood Bats")
        self.lands("W1", self.b)
        self.assertTrue(self.cast(self.get("Raise the Alarm"), who=self.b))
        self.assertEqual(self.b.life, 20)

    def test_ai(self):
        smoke_ok(self, "Mirkwood Bats", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ellie_vengeful_hunter(Scenario):
    """Pay 2 life + sacrifice another creature: 2 damage to target player (the AI/test picks the opponent) and
    Ellie gains indestructible until end of turn. Can't be paid by sacrificing Ellie herself."""
    def test_activate(self):
        self.translated("Ellie, Vengeful Hunter")
        e = self.put("Ellie, Vengeful Hunter")
        bear = self.put(vanilla())
        self.assertTrue(self.activate(e, 0, [self.b]))
        self.assertEqual((self.a.life, self.b.life), (18, 18))
        self.assertNotIn(bear, self.a.battlefield)
        self.assertTrue(e.has("indestructible"))

    def test_needs_another_creature(self):
        e = self.put("Ellie, Vengeful Hunter")
        self.assertFalse(self.activate(e, 0, [self.b]))

    def test_ai(self):
        smoke_ok(self, "Ellie, Vengeful Hunter", used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class adamaro_first_to_desire(Scenario):
    """P/T = cards in the (only) opponent's hand."""
    def test_pt(self):
        self.translated("Adamaro, First to Desire")
        x = self.put("Adamaro, First to Desire")
        self.b.hand = [vanilla()] * 5
        self.a.hand = [vanilla()] * 2
        self.assertEqual((x.power, x.toughness), (5, 5))
        self.b.hand = []
        self.assertEqual((x.power, x.toughness), (0, 0))

    def test_ai(self):
        smoke_ok(self, "Adamaro, First to Desire", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class alistair_the_brigadier(Scenario):
    """Attack trigger: may pay {8}; if paid, creatures you control get +X/+X until end of turn, X = historic
    permanents you control (artifacts, legendaries, Sagas). Unpaid: nothing."""
    def test_paid(self):
        self.translated("Alistair, the Brigadier")
        al = self.put("Alistair, the Brigadier")         # legendary: historic
        self.put(vanilla("Rock", 0, 0, "{1}", "Artifact"))   # historic
        bear = self.put(vanilla())
        self.lands("8")
        self.game.attackers = [al]
        self.fire("attacks", source=al)
        self.assertEqual((bear.power, bear.toughness), (4, 4))
        self.assertEqual(al.power, 3 + 2)

    def test_unpaid(self):
        al = self.put("Alistair, the Brigadier")
        bear = self.put(vanilla())
        self.lands("3")
        self.game.attackers = [al]
        self.fire("attacks", source=al)
        self.assertEqual((bear.power, bear.toughness), (2, 2))

    def test_ai(self):
        smoke_ok(self, "Alistair, the Brigadier", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class bloodroot_apothecary(Scenario):
    """ETB: you create a Treasure and target opponent creates a Treasure (one each)."""
    def test_enter(self):
        self.translated("Bloodroot Apothecary")
        self.enter("Bloodroot Apothecary")
        mine = [x for x in self.a.battlefield if x.card.token_kind == "treasure"]
        theirs = [x for x in self.b.battlefield if x.card.token_kind == "treasure"]
        self.assertEqual((len(mine), len(theirs)), (1, 1))

    def test_ai(self):
        smoke_ok(self, "Bloodroot Apothecary", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class daybreak_ranger(Scenario):
    """Nightfall Predator (back face): {R}, {T}: it fights target creature: each deals damage equal to its
    power to the other. A 4/4 fighting a 2/2 kills the 2/2 and takes 2 damage."""
    def test_fight(self):
        self.translated("Daybreak Ranger")
        c = self.get("Daybreak Ranger")
        x = self.put(c)
        self.game.transform(x) if hasattr(self.game, "transform") else None
        self.assertEqual(x.card.name, "Nightfall Predator")
        bear = self.put(vanilla(), self.b)
        self.lands("R")
        idx = next(i for i, a in enumerate(x.activated) if a.cost.get("R"))
        self.assertTrue(self.activate(x, idx, [bear]))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(x, self.a.battlefield)
        self.assertEqual(x.damage, 2)
        self.assertTrue(x.tapped)

    def test_ai(self):
        smoke_ok(self, "Daybreak Ranger", used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class krang_master_mind(Scenario):
    """ETB: if you have fewer than four cards in hand, draw until you have four (1 in hand -> draw 3; 5 -> 0)."""
    def test_one_card(self):
        self.translated("Krang, Master Mind")
        self.a.hand = [vanilla()]
        self.enter("Krang, Master Mind")
        self.assertEqual(len(self.a.hand), 4)

    def test_full_hand(self):
        self.a.hand = [vanilla()] * 5
        self.enter("Krang, Master Mind")
        self.assertEqual(len(self.a.hand), 5)

    def test_ai(self):
        smoke_ok(self, "Krang, Master Mind", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class nils_discipline_enforcer(Scenario):
    """Your end step: +1/+1 counter on up to one target creature you control and on up to one target creature
    the opponent controls (one each).
    Spec corrected after the first run: "up to one" lets the controller choose no target, and the AI (rightly)
    doesn't put a counter on the opponent's creature, so that half is checked as "at most one"."""
    def test_end_step(self):
        self.translated("Nils, Discipline Enforcer")
        self.put("Nils, Discipline Enforcer")
        bear = self.put(vanilla("Opp Bear"), self.b)
        self.end_step()
        mine = sum(x.counters.get("+1/+1", 0) for x in self.a.battlefield)
        self.assertEqual(mine, 1)
        self.assertLessEqual(bear.counters.get("+1/+1", 0), 1)

    def test_opponent_half_resolves(self):
        """The opponent-side effect puts the counter when given its target."""
        c = self.get("Nils, Discipline Enforcer")
        bear = self.put(vanilla("Opp Bear"), self.b)
        from mtgsim.engine import StackItem
        trig = c.triggers[0]
        self.game.stack.append(StackItem(self.a, trig.effects, [None, bear], name="Nils"))
        self.game.resolve_top()
        self.assertEqual(bear.counters.get("+1/+1", 0), 1)

    def test_ai(self):
        smoke_ok(self, "Nils, Discipline Enforcer", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class aeon_engine(Scenario):
    """{T}, exile it: reverse turn order. With two players the order is unchanged: the ability can be activated
    (Aeon Engine goes to exile) and nothing else happens; the opponent still takes the next turn."""
    def test_activate(self):
        self.translated("Aeon Engine")
        x = self.put("Aeon Engine")
        self.assertTrue(self.activate(x, 0))
        self.assertEqual(self.names(self.a.exile), ["Aeon Engine"])
        self.assertEqual(self.game.opponent(self.a), self.b)

    def test_ai(self):
        smoke_ok(self, "Aeon Engine", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class unstable_molecule_suit(Scenario):
    """'Equip commander {2}' can never be used (no commanders here): the only usable equip cost is {4}."""
    def test_equip_cost(self):
        c = self.translated("Unstable Molecule Suit")
        self.assertEqual(c.equip_cost, {"generic": 4})

    def test_ai(self):
        smoke_ok(self, "Unstable Molecule Suit", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class the_unbeatable_squirrel_girl(Scenario):
    """Enters or attacks: one 1/1 green Squirrel token. {1}{G}{G}{G}: X 1/1 green Squirrels, X = Squirrels you
    control, counted on resolution.
    Spec corrected after the first run: her type line is Human Squirrel Hero, so she counts too (two tokens + her:
    X=3, five Squirrel tokens), not X=2 as first written."""
    def squirrels(self):
        return [x for x in self.a.creatures if x.card.is_token and "Squirrel" in x.card.subtypes]

    def test_enter_and_attack(self):
        self.translated("The Unbeatable Squirrel Girl")
        g = self.enter("The Unbeatable Squirrel Girl")
        self.assertEqual(len(self.squirrels()), 1)
        tok = self.squirrels()[0]
        self.assertEqual((tok.power, tok.toughness), (1, 1))
        self.assertIn("G", tok.card.colors)
        self.game.attackers = [g]
        self.fire("attacks", source=g)
        self.assertEqual(len(self.squirrels()), 2)

    def test_activated_counts_squirrels(self):
        g = self.enter("The Unbeatable Squirrel Girl")
        self.game.attackers = [g]
        self.fire("attacks", source=g)                   # two Squirrels now
        self.game.attackers = []
        self.lands("GGG1")
        idx = next(i for i, a in enumerate(g.activated) if a.cost.get("G") == 3)
        self.assertTrue(self.activate(g, idx))
        self.assertEqual(len(self.squirrels()), 5)

    def test_ai(self):
        smoke_ok(self, "The Unbeatable Squirrel Girl", hostile=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class keeper_of_the_beasts(Scenario):
    """{G},{T}: only while the opponent controls more creatures than you; makes a 2/2 green Beast token. With
    equal creature counts the ability can't be activated."""
    def beasts(self):
        return [x for x in self.a.creatures if x.card.is_token and "Beast" in x.card.subtypes]

    def test_more_creatures(self):
        self.translated("Keeper of the Beasts")
        k = self.put("Keeper of the Beasts")
        self.put(vanilla(), self.b)
        self.put(vanilla(), self.b)
        self.lands("G")
        self.assertTrue(self.activate(k, 0))
        self.assertEqual(len(self.beasts()), 1)
        self.assertEqual((self.beasts()[0].power, self.beasts()[0].toughness), (2, 2))

    def test_equal_creatures(self):
        k = self.put("Keeper of the Beasts")
        self.put(vanilla(), self.b)
        self.lands("G")
        self.assertFalse(self.activate(k, 0))
        self.assertEqual(self.beasts(), [])

    def test_ai(self):
        smoke_ok(self, "Keeper of the Beasts", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class voice_of_many(Scenario):
    """ETB: draw one card if the opponent controls fewer creatures than you (it counts itself); else none."""
    def test_fewer(self):
        self.translated("Voice of Many")
        hand = len(self.a.hand)
        self.enter("Voice of Many")                       # you 1, opponent 0
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_equal(self):
        self.put(vanilla(), self.b)
        self.put(vanilla(), self.b)
        self.put(vanilla())
        hand = len(self.a.hand)
        self.enter("Voice of Many")                       # you 2, opponent 2
        self.assertEqual(len(self.a.hand), hand)

    def test_ai(self):
        smoke_ok(self, "Voice of Many", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class mr_wiggles_helpful_butterfly(Scenario):
    """The commander-only line never applies here: a 1/x flier with no game-start effect."""
    def test_plain(self):
        c = self.translated("Mr. Wiggles, Helpful Butterfly")
        self.assertIn("flying", c.keywords)
        self.assertEqual(c.triggers, [])

    def test_ai(self):
        smoke_ok(self, "Mr. Wiggles, Helpful Butterfly", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class agent_of_acquisitions(Scenario):
    """Draft-only text: in a game it is a vanilla 2/1."""
    def test_plain(self):
        c = self.translated("Agent of Acquisitions")
        self.assertEqual((c.power, c.toughness), (2, 1))
        self.assertEqual((c.triggers, c.activated), ([], []))

    def test_ai(self):
        smoke_ok(self, "Agent of Acquisitions", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class wall_of_resistance(Scenario):
    # The translation (results/pilot_translate_20261116/failed/wall_of_resistance.json) FAILED these tests: the
    # hist condition doesn't track "~ is dealt damage" per permanent. Kept to document the failure; skipped
    # because the card is not translated.
    """Each end step: if THIS creature was dealt damage this turn, it gets a +0/+1 counter (0/5 -> 0/6).
    Damage to another creature, or no damage, gives nothing."""
    def setUp(self):
        self.skipTest("translation failed verification; card left partial")

    def test_damaged(self):
        self.translated("Wall of Resistance")
        w = self.put("Wall of Resistance")
        self.game.deal_damage(w, 1, self.b)
        self.end_step()
        self.assertEqual(w.counters.get("+0/+1", 0), 1)
        self.assertEqual(w.toughness, 6)

    def test_other_creature_damaged(self):
        w = self.put("Wall of Resistance")
        bear = self.put(vanilla("Other", 2, 4))
        self.game.deal_damage(bear, 1, self.b)
        self.end_step()
        self.assertEqual(w.counters.get("+0/+1", 0), 0)

    def test_opponents_end_step_too(self):
        w = self.put("Wall of Resistance")
        self.game.active_idx = 1
        self.game.deal_damage(w, 1, self.b)
        self.end_step(self.b)
        self.assertEqual(w.counters.get("+0/+1", 0), 1)

    def test_ai(self):
        smoke_ok(self, "Wall of Resistance", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class the_raven_man(Scenario):
    """Each end step: if any player discarded a card this turn, you create a 1/1 black flying Bird that can't
    block. No discard: nothing."""
    def birds(self):
        return [x for x in self.a.creatures if x.card.is_token and "Bird" in x.card.subtypes]

    def test_opponent_discarded(self):
        self.translated("The Raven Man")
        self.put("The Raven Man")
        c = vanilla()
        self.b.hand = [c]
        self.game.discard_card(self.b, c)
        self.end_step()
        b = self.birds()
        self.assertEqual(len(b), 1)
        self.assertTrue(b[0].has("flying"))
        self.assertEqual((b[0].power, b[0].toughness), (1, 1))
        self.assertTrue(b[0].card.cant_block)

    def test_no_discard(self):
        self.put("The Raven Man")
        self.end_step()
        self.assertEqual(self.birds(), [])

    def test_ai(self):
        smoke_ok(self, "The Raven Man", used=False)     # no discards happened in the smoke games


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class mistway_spy(Scenario):
    """Turned face up: for the rest of the turn, each time a creature you control deals combat damage to a
    player you investigate (a Clue token)."""
    def test_face_up_then_damage(self):
        self.translated("Mistway Spy")
        spy = self.put("Mistway Spy")
        self.fire("turned_face_up", source=spy)
        bear = self.put(vanilla())
        self.game.attackers = [bear]
        self.game.combat_damage(self.a, self.b, [bear], {}, lambda c: True)
        self.game.settle()
        clues = [x for x in self.a.battlefield if x.card.token_kind == "clue"]
        self.assertEqual(len(clues), 1)

    def test_no_face_up_no_clue(self):
        self.put("Mistway Spy")
        bear = self.put(vanilla())
        self.game.attackers = [bear]
        self.game.combat_damage(self.a, self.b, [bear], {}, lambda c: True)
        self.game.settle()
        self.assertEqual([x for x in self.a.battlefield if x.card.token_kind == "clue"], [])

    def test_ai(self):
        smoke_ok(self, "Mistway Spy", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class transmogrants_crown(Scenario):
    """Equip can be paid with {B} alone, or with {2}; equipped creature gets +2/+0 (corrected from Oracle before running)."""
    def test_equip_for_b(self):
        self.translated("Transmogrant's Crown")
        crown = self.put("Transmogrant's Crown")
        bear = self.put(vanilla())
        self.lands("B")
        idx = next(i for i, a in enumerate(crown.activated) if a.cost.get("B"))
        self.assertTrue(self.activate(crown, idx, [bear]))
        self.assertIs(crown.attached_to, bear)
        self.assertEqual((bear.power, bear.toughness), (4, 2))

    def test_equip_for_two(self):
        crown = self.put("Transmogrant's Crown")
        bear = self.put(vanilla())
        self.lands("2")
        self.assertTrue(self.game.equip(self.a, crown, bear) if hasattr(self.game, "equip") else False)
        self.assertIs(crown.attached_to, bear)

    def test_ai(self):
        smoke_ok(self, "Transmogrant's Crown", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class proctor_of_potential(Scenario):
    """{W}{U} from the graveyard: returns to the battlefield with a finality counter, only on a turn you scried
    or surveilled."""
    def test_after_scry(self):
        self.translated("Proctor of Potential")
        c = self.get("Proctor of Potential")
        self.a.graveyard = [c]
        self.lands("WU")
        self.assertFalse(self.game.can_activate_graveyard(self.a, c, 0))
        from mtgsim.cards import Effect
        from mtgsim.engine import StackItem
        self.game.stack.append(StackItem(self.a, [Effect("surveil", 1)], [None], name="test surveil"))
        self.game.resolve_top()
        self.assertTrue(self.game.can_activate_graveyard(self.a, c, 0))
        self.assertTrue(self.game.activate_graveyard(self.a, c, 0))
        self.game.settle()
        back = [x for x in self.a.battlefield if x.card.name == "Proctor of Potential"]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].counters.get("finality", 0), 1)

    def test_ai(self):
        smoke_ok(self, "Proctor of Potential", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class clawing_torment(Scenario):
    """On a creature: it gets -1/-1 and can't block (its controller still loses 1 life each upkeep)."""
    def test_cast_on_opponent(self):
        self.translated("Clawing Torment")
        bear = self.put(vanilla("Opp Bear", 3, 3), self.b)
        self.lands("B")
        self.assertTrue(self.cast("Clawing Torment"))
        aura = next(x for x in self.a.battlefield if x.card.name == "Clawing Torment")
        self.assertIs(aura.aura_host, bear)
        self.assertEqual((bear.power, bear.toughness), (2, 2))
        self.assertTrue(bear.has("cant_block_now"))

    def test_ai(self):
        smoke_ok(self, "Clawing Torment", used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class return_the_past(Scenario):
    """During your turn, instants/sorceries in your graveyard can be cast by paying their mana cost (flashback:
    exiled afterwards). Not during the opponent's turn."""
    def test_flashback_own_turn(self):
        self.translated("Return the Past")
        self.put("Return the Past")
        shock = self.get("Shock")
        self.a.graveyard = [shock]
        self.lands("R")
        opts = [c for c in self.game.spell_options(self.a) if c.name.startswith("Shock")]
        self.assertTrue(opts)
        self.assertTrue(self.game.cast(self.a, opts[0], [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 18)
        self.assertEqual(self.names(self.a.exile), ["Shock"])

    def test_not_opponents_turn(self):
        self.put("Return the Past")
        self.a.graveyard = [self.get("Shock")]
        self.lands("R")
        self.game.active_idx = 1
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith("Shock")])

    def test_ai(self):
        smoke_ok(self, "Return the Past", hostile=False, used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class telekinetic_bonds(Scenario):
    """Whenever any player discards a card: you may pay {1}{U}; if you do, tap or untap target permanent.
    With mana and an untapped opposing creature, it gets tapped and you paid two mana."""
    def test_discard(self):
        self.translated("Telekinetic Bonds")
        self.put("Telekinetic Bonds")
        foe = self.put(vanilla("Opp Bear", 3, 3), self.b)
        lands = self.lands("U1")
        c = vanilla()
        self.b.hand = [c]
        self.game.discard_card(self.b, c)
        self.game.settle()
        self.assertTrue(foe.tapped)
        self.assertTrue(all(x.tapped for x in lands))

    def test_ai(self):
        smoke_ok(self, "Telekinetic Bonds", used=False)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class thunder_salvo(Scenario):
    """X = 2 + other spells you cast this turn. First spell of the turn: 2 damage; after one other spell: 3."""
    def test_first_spell(self):
        self.translated("Thunder Salvo")
        foe = self.put(vanilla("Opp Big", 5, 5), self.b)
        self.lands("R1")
        self.assertTrue(self.cast("Thunder Salvo", [foe]))
        self.assertEqual(foe.damage, 2)

    def test_after_another_spell(self):
        self.translated("Thunder Salvo")     # loaded before play, as a deck's cards are (history heads register on load)
        foe = self.put(vanilla("Opp Big", 5, 5), self.b)
        self.lands("RR1")
        self.assertTrue(self.cast("Shock", [self.b]))
        self.assertTrue(self.cast("Thunder Salvo", [foe]))
        self.assertEqual(foe.damage, 3)

    def test_ai(self):
        smoke_ok(self, "Thunder Salvo")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class brackish_blunder(Scenario):
    # The translation (results/pilot_translate_20261116/failed/brackish_blunder.json) FAILED test_untapped: the
    # prev_is tapped gate doesn't read the bounced creature's state (a Map was made for an untapped creature).
    def setUp(self):
        self.skipTest("translation failed verification; card left partial")

    """Bounce target creature; if it was tapped, you create a Map token. Untapped: no Map."""
    def maps(self):
        return [x for x in self.a.battlefield if x.card.token_kind == "map"]

    def test_tapped(self):
        self.translated("Brackish Blunder")
        foe = self.put(vanilla("Opp Bear"), self.b, tapped=True)
        self.lands("U1")
        self.assertTrue(self.cast("Brackish Blunder", [foe]))
        self.assertIn("Opp Bear", self.names(self.b.hand))
        self.assertEqual(len(self.maps()), 1)

    def test_untapped(self):
        foe = self.put(vanilla("Opp Bear"), self.b)
        self.lands("U1")
        self.assertTrue(self.cast("Brackish Blunder", [foe]))
        self.assertEqual(self.maps(), [])

    def test_ai(self):
        smoke_ok(self, "Brackish Blunder")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class death_baron(Scenario):
    """Your Skeletons and your other Zombies get +1/+1 and deathtouch; a creature that is both gets +1/+1 once;
    other creatures and the opponent's Zombies get nothing."""
    def test_anthem(self):
        self.translated("Death Baron")
        self.put("Death Baron")
        sk = self.put(vanilla("Sk", 1, 1, "{B}", "Creature — Skeleton"))
        zo = self.put(vanilla("Zo", 2, 2, "{B}", "Creature — Zombie"))
        both = self.put(vanilla("Both", 2, 2, "{B}", "Creature — Zombie Skeleton"))
        bear = self.put(vanilla())
        theirs = self.put(vanilla("OppZo", 2, 2, "{B}", "Creature — Zombie"), self.b)
        self.assertEqual((sk.power, sk.toughness, zo.power, both.power), (2, 2, 3, 3))
        self.assertTrue(sk.has("deathtouch") and zo.has("deathtouch") and both.has("deathtouch"))
        self.assertEqual((bear.power, theirs.power), (2, 2))
        self.assertFalse(bear.has("deathtouch") or theirs.has("deathtouch"))

    def test_ai(self):
        smoke_ok(self, "Death Baron", hostile=False, used=False)


SNOW_LAND = vanilla("Snow-Covered Test", 0, 0, "", "Basic Snow Land — Forest")
SNOW_LAND.power = SNOW_LAND.toughness = None


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class icequake(Scenario):
    """Destroy target land; if it was a snow land, 1 damage to its controller (the opponent)."""
    def test_snow(self):
        self.translated("Icequake")
        land = self.put(self.get("Snow-Covered Forest"), self.b)
        self.lands("BB1")
        self.assertTrue(self.cast("Icequake", [land]))
        self.assertNotIn(land, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_not_snow(self):
        land = self.put(self.get("Forest"), self.b)
        self.lands("BB1")
        self.assertTrue(self.cast("Icequake", [land]))
        self.assertNotIn(land, self.b.battlefield)
        self.assertEqual(self.b.life, 20)

    def test_ai(self):
        smoke_ok(self, "Icequake")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class remorseless_punishment(Scenario):
    """Twice: the opponent loses 5 life unless they discard two cards or sacrifice a creature/planeswalker.
    With an empty hand and no creatures, they lose 10; with exactly one creature and no hand, they can avoid one
    of the two losses at most (loses >= 5)."""
    def test_nothing_to_give(self):
        self.translated("Remorseless Punishment")
        self.b.hand = []
        self.lands("BB3")
        self.assertTrue(self.cast("Remorseless Punishment"))
        self.assertEqual(self.b.life, 10)
        self.assertEqual(self.a.life, 20)

    def test_one_creature(self):
        self.b.hand = []
        self.put(vanilla("Opp Bear"), self.b)
        self.lands("BB3")
        self.assertTrue(self.cast("Remorseless Punishment"))
        self.assertLessEqual(self.b.life, 15)
        self.assertGreaterEqual(self.b.life, 10)

    def test_ai(self):
        smoke_ok(self, "Remorseless Punishment")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class blizzard_brawl(Scenario):
    # The translation (results/pilot_translate_20261116/failed/blizzard_brawl.json) passed test_no_snow/test_snow
    # but FAILED test_ai: HeuristicAI never cast it in 8 games (it does cast the plain fight_mark+fight pattern).
    def setUp(self):
        self.skipTest("translation failed verification (AI never uses it); card left partial")

    """Your creature fights the opponent's creature; with 3+ snow permanents yours first gets +1/+0 and
    indestructible until end of turn. 2/2 vs 3/3: without snow both... the 2/2 dies and the 3/3 survives;
    with three snow lands the 3/2 indestructible survives and the 3/3 dies."""
    def test_no_snow(self):
        self.translated("Blizzard Brawl")
        mine = self.put(vanilla("Mine", 2, 2))
        foe = self.put(vanilla("Foe", 3, 3), self.b)
        self.lands("G")
        self.assertTrue(self.cast("Blizzard Brawl", [mine, None, foe]))
        self.assertNotIn(mine, self.a.battlefield)
        self.assertIn(foe, self.b.battlefield)
        self.assertEqual(foe.damage, 2)

    def test_snow(self):
        mine = self.put(vanilla("Mine", 2, 2))
        foe = self.put(vanilla("Foe", 3, 3), self.b)
        for _ in range(3):
            self.put(self.get("Snow-Covered Forest"))
        self.assertTrue(self.cast("Blizzard Brawl", [mine, None, foe]))
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(foe, self.b.battlefield)
        self.assertEqual(mine.power, 3)

    def test_ai(self):
        smoke_ok(self, "Blizzard Brawl")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class breathkeeper_seraph(Scenario):
    """Flying and soulbond: it can pair with another creature as either enters; while paired, the partner (and
    the Seraph) has the delayed-return death trigger. Entering next to a creature pairs them."""
    def test_flying_and_pairing(self):
        c = self.translated("Breathkeeper Seraph")
        self.assertIn("flying", c.keywords)
        bear = self.put(vanilla())
        seraph = self.enter("Breathkeeper Seraph")
        from mtgsim.batch1_templates import paired
        self.assertIs(paired(seraph), bear)

    def test_ai(self):
        smoke_ok(self, "Breathkeeper Seraph", hostile=False, used=False)
