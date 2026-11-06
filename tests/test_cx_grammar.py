"""The compositional effect grammar (mtgsim.cx_grammar): subject + verb chain + duration."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards import parse as P
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
WOLF = card("Test Wolf", "{G}", "Creature — Wolf", "", 2, 2)
FLIER = card("Test Flier", "{U}", "Creature — Bird", "Flying", 1, 1)
RED = card("Test Red", "{R}", "Creature — Human", "", 2, 2)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c, targets=None, by=None):
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effects, targets or [None] * len(effects), card=c, name=c.name))
        self.game.resolve_top()

    def spell(self, text, types="Instant"):
        c = card("Test Spell", "{1}", types, text)
        self.assertEqual(c.unsupported, [], text)
        return c

    def end_turn(self):
        self.game.expire_continuous_effects()
        for x in self.a.battlefield + self.b.battlefield:
            x.pump_p = x.pump_t = 0
            x.temp_kw.clear()


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_rejects_what_it_cannot_execute(self):
        for s in ("Those creatures gain trample until end of turn.",       # "those": no referent here
                  "Foo creatures get +1/+1 until end of turn.",            # not a subtype
                  "Target creature gets +2/+2.",                           # a one-shot pump needs a duration
                  "Target creature gains banding until end of turn.",      # not a keyword the engine has
                  "Target creature can't block.",                          # no duration
                  "Target creature gets +1/+1 until end of turn and draws a card.",
                  "Creature gets +1/+1 until end of turn.",                # bare singular subject
                  "Target creature becomes a 3/3 Golem until end of turn."):
            self.assertIsNone(parse_sentence(s), s)

    def test_subjects(self):
        self.assertEqual(self.kinds("Target red or green creature gets -2/-0 until end of turn."), ["debuff_one"])
        self.assertEqual(self.kinds("Up to two target creatures each get +1/+0 and gain menace until end of turn."),
                         ["pump", "grant", "pump", "grant"])
        self.assertEqual(self.kinds("Creatures target player controls get +2/+0 until end of turn."), ["cx_group"])
        self.assertEqual(self.kinds("Other Villains you control gain flying until end of turn."), ["cx_group"])
        self.assertEqual(self.kinds("Equipped creatures you control gain indestructible until end of turn."), ["cx_group"])

    def test_verbs_and_durations(self):
        self.assertEqual(self.kinds("Until end of turn, target creature loses flying and becomes black."),
                         ["cx_lose_kw", "cx_color"])
        self.assertEqual(self.kinds("Target creature becomes white."), ["cx_color"])
        self.assertEqual(self.kinds("Cowards can't block this turn."), ["cx_group"])
        self.assertEqual(self.kinds("It can't be blocked this combat."), ["cx_temp_kw"])
        self.assertEqual(self.kinds("Target creature an opponent controls attacks this turn if able."), ["cx_temp_kw"])

    def test_fallback_runs_after_templates(self):
        effects, bad = P._parse_effects("Target creature gets +2/+0 and gains first strike until end of turn.")
        self.assertEqual([e.kind for e in effects], ["pump"])       # the existing template still wins
        effects, bad = P._parse_effects("You may have target creature gain flying until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[-1].kind, "grant")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Canopy Claws", "Rank and File", "Aphotic Wisps", "Cutthroat Maneuver", "Sky Weaver",
                     "How to Start a Riot", "Pyrophobia", "Battle Cry Goblin", "Swarm Surge", "Hold the Line"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_lose_flying_until_end_of_turn(self):
        flier = self.perm(FLIER, self.b)
        self.cast(self.spell("Target creature loses flying until end of turn."), [flier])
        self.assertFalse(flier.has("flying"))
        self.end_turn()
        self.assertTrue(flier.has("flying"))

    def test_group_pump_with_subtype_and_controller(self):
        mine, other, theirs = self.perm(GOBLIN, self.a), self.perm(BEAR, self.a), self.perm(GOBLIN, self.b)
        self.cast(self.spell("Goblin creatures you control get +1/+1 and gain haste until end of turn."))
        self.assertEqual((mine.power, mine.toughness), (2, 2))
        self.assertTrue(mine.has("haste"))
        self.assertEqual(other.power, BEAR.power)
        self.assertEqual(theirs.power, 1)
        self.end_turn()
        self.assertEqual(mine.power, 1)

    def test_group_is_fixed_on_resolution(self):
        self.perm(BEAR, self.a)
        self.cast(self.spell("Creatures you control get +1/+0 until end of turn."))
        late = self.perm(BEAR, self.a)
        self.assertEqual(late.power, BEAR.power)

    def test_becomes_color_until_end_of_turn(self):
        bear = self.perm(BEAR, self.b)
        self.cast(self.spell("Target creature becomes black and gains fear until end of turn."), [bear, None])
        self.assertEqual(set(bear.card.colors), {"B"})
        self.assertTrue(bear.has("fear"))
        self.end_turn()
        self.assertEqual(set(bear.card.colors), set(BEAR.colors))

    def test_colour_alternative_target(self):
        spell = self.spell("Target red or green creature gains trample until end of turn.")
        red, blue = self.perm(RED, self.a), self.perm(FLIER, self.a)
        with self.game.targeting(spell):
            legal = self.game.legal_targets(self.a, spell.spell_effects[0])
        self.assertIn(red, legal)
        self.assertNotIn(blue, legal)

    def test_two_targets_each(self):
        x, y = self.perm(BEAR, self.a), self.perm(WOLF, self.a)
        spell = self.spell("Two target creatures each get +2/+2 and gain flying until end of turn.")
        self.cast(spell, [x, None, y, None])
        self.assertEqual((x.power, y.power), (BEAR.power + 2, 4))
        self.assertTrue(x.has("flying") and y.has("flying"))

    def test_creatures_target_player_controls(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.cast(self.spell("Creatures target player controls can't block this turn."), [self.b])
        self.assertTrue(theirs.has("cant_block_now"))
        self.assertFalse(mine.has("cant_block_now"))

    def test_attacking_subtype_group(self):
        wolf, bear = self.perm(WOLF, self.a), self.perm(BEAR, self.a)
        self.game.attackers = [wolf, bear]
        self.cast(self.spell("Attacking Wolves you control gain indestructible until end of turn."))
        self.assertTrue(wolf.has("indestructible"))
        self.assertFalse(bear.has("indestructible"))

    def test_until_your_next_turn_lasts(self):
        from mtgsim.advanced_templates import begin_turn
        flier = self.perm(FLIER, self.b)
        self.cast(self.spell("Target creature loses flying until your next turn."), [flier])
        self.end_turn()
        self.game.turn += 1
        begin_turn(self.game, self.b)
        self.assertFalse(flier.has("flying"))
        self.end_turn()
        self.game.turn += 1
        begin_turn(self.game, self.a)
        self.assertTrue(flier.has("flying"))

    def test_ai_targets_the_opponent_for_a_restriction(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(WOLF, self.b)
        spell = self.spell("Target creature loses trample until end of turn.")
        self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), theirs)
        self.assertIsNot(mine, theirs)


if __name__ == "__main__":
    unittest.main()


class StaticGrants(Base):
    def lord(self, text, types="Creature — Elf", p=2, t=2):
        c = card("Test Lord", "{2}", types, text, p, t)
        self.assertEqual(c.unsupported, [], text)
        return c

    def test_lord_pt_and_keyword_for_every_player(self):
        lord = self.perm(self.lord("Other Goblin creatures get +1/+1 and have haste."), self.a)
        mine, theirs, bear = self.perm(GOBLIN, self.a), self.perm(GOBLIN, self.b), self.perm(BEAR, self.a)
        self.assertEqual((mine.power, theirs.power, bear.power), (2, 2, BEAR.power))
        self.assertTrue(mine.has("haste") and theirs.has("haste"))
        self.assertEqual(lord.power, 2)               # "other"
        self.game.leave_battlefield(lord, "graveyard")
        self.assertEqual(mine.power, 1)

    def test_richer_noun_phrase(self):
        self.perm(self.lord("Nonblack creatures get -1/-1."), self.a)
        red = self.perm(RED, self.b)
        self.assertEqual(red.toughness, 1)

    def test_restriction_grant(self):
        self.perm(self.lord("Creatures without flying can't attack."), self.a)
        bear, flier = self.perm(BEAR, self.b), self.perm(FLIER, self.b)
        self.assertTrue(bear.has("cant_attack_now"))
        self.assertFalse(flier.has("cant_attack_now"))

    def test_no_self_referential_keyword_grant(self):
        c = card("Test Lord", "{2}", "Creature — Elf", "Creatures with flying have vigilance.", 2, 2)
        self.assertEqual(c.unsupported, ["Creatures with flying have vigilance."])

    def test_no_power_conditioned_anthem(self):
        c = card("Test Lord", "{2}", "Creature — Elf", "Creatures with power 2 or less get +1/+1.", 2, 2)
        self.assertEqual(c.unsupported, ["Creatures with power 2 or less get +1/+1."])

    def test_equipment_with_a_negative_bonus(self):
        gear = card("Test Gear", "{1}", "Artifact — Equipment", "Equipped creature gets +2/-1 and has menace.\nEquip {1}")
        self.assertEqual(gear.unsupported, [])
        bear = self.perm(BEAR, self.a)
        g = self.perm(gear, self.a)
        g.attached_to = bear
        self.assertEqual((bear.power, bear.toughness), (BEAR.power + 2, BEAR.toughness - 1))
        self.assertTrue(bear.has("menace"))

    def test_not_on_a_non_equipment(self):
        c = card("Test Thing", "{1}", "Artifact", "Equipped creature gets +2/-1.")
        self.assertEqual(c.unsupported, ["Equipped creature gets +2/-1."])


class PlayerSubjects(Base):
    def test_each_player_verb_by_verb(self):
        self.a.hand, self.b.hand = [BEAR], [BEAR]
        self.cast(self.spell("Each player discards a card, then draws a card."))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 1))
        self.assertEqual((len(self.a.graveyard), len(self.b.graveyard)), (2, 1))      # a: the spell too

    def test_defending_player_and_you(self):
        life = (self.a.life, self.b.life)
        self.cast(self.spell("Defending player loses 2 life. You draw two cards and lose 1 life."))
        self.assertEqual((self.a.life, self.b.life), (life[0] - 1, life[1] - 2))
        self.assertEqual(len(self.a.hand), 2)

    def test_that_creatures_controller(self):
        bear = self.perm(BEAR, self.b)
        spell = self.spell("Tap target creature. That creature's controller loses 3 life.")
        self.cast(spell, [bear, None])
        self.assertEqual(self.b.life, 20 - 3)

    def test_unknown_player_verbs_are_rejected(self):
        self.assertIsNone(parse_sentence("Each player gains 2 life and explores."))


class Quantities(Base):
    def test_group_for_each(self):
        elf = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
        x, y = self.perm(elf, self.a), self.perm(elf, self.a)
        self.cast(self.spell("Creatures you control get +1/+0 until end of turn for each Elf you control."))
        self.assertEqual((x.power, y.power, x.toughness), (3, 3, 1))

    def test_group_where_x(self):
        g = self.perm(GOBLIN, self.a)
        self.a.hand = [BEAR, BEAR, BEAR]
        self.cast(self.spell("Goblins you control get +X/+X until end of turn, where X is the number of cards in your hand."))
        self.assertEqual((g.power, g.toughness), (4, 4))

    def test_players_for_each(self):
        self.perm(BEAR, self.a), self.perm(BEAR, self.a)
        life = self.b.life
        self.cast(self.spell("Each opponent loses 1 life for each creature you control."))
        self.assertEqual(self.b.life, life - 2)

    def test_unknown_quantity_is_rejected(self):
        self.assertIsNone(parse_sentence("Creatures you control get +1/+1 until end of turn for each creature blocking it."))
        self.assertIsNone(parse_sentence("Target creature gains flying until end of turn for each card in your hand."))


class Registry(unittest.TestCase):
    def test_a_registered_verb_family_plugs_in(self):
        from mtgsim import cx_grammar as G

        @G.verb(r"zaps? (\d+) widgets?", heads=("zap", "zaps"), subjects=("permanent", "group"))
        def zap(m, clause):
            return [G.Part("pump", int(m[1]), 0)] if clause.duration == "eot" else None
        try:
            effs = parse_sentence("Target creature zaps 2 widgets and gains flying until end of turn.")
            self.assertEqual([(e.kind, e.amount) for e in effs], [("pump", 2), ("grant", 0)])
            self.assertIsNone(parse_sentence("Target creature zaps 2 widgets."))     # the parser rejected it
        finally:
            G.VERBS[:] = [v for v in G.VERBS if v.parse is not zap]
            G._HEADS.clear()

    def test_families_are_discovered(self):
        from mtgsim import cx_grammar as G
        G._load()
        self.assertTrue({"mtgsim.cx_grammar_stats", "mtgsim.cx_grammar_keywords", "mtgsim.cx_grammar_color",
                         "mtgsim.cx_grammar_players"} <= {v.module for v in G.VERBS})


class TargetPlayers(Base):
    def main_phase(self, text, types="Sorcery"):
        spell = card("Test Spell", "{U}", types, text)
        self.assertEqual(spell.unsupported, [], text)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        return spell

    def test_ai_casts_a_group_debuff_at_the_opponent(self):
        bear, mine = self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        spell = self.main_phase("Creatures target player controls get -1/-1 until end of turn.")
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((bear.power, mine.power), (BEAR.power - 1, BEAR.power))

    def test_ai_casts_a_group_pump_at_itself(self):
        bear, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.game.step = "main1"
        spell = card("Test Spell", "{U}", "Instant", "Creatures target player controls get +1/+1 until end of turn.")
        with self.game.targeting(spell):
            tgt = self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell)
        self.assertIs(tgt, self.a)
        self.cast(spell, [self.a])
        self.assertEqual((bear.power, theirs.power), (BEAR.power + 1, BEAR.power))

    def test_ai_casts_target_player_loses_life_at_the_opponent(self):
        life = (self.a.life, self.b.life)
        spell = self.main_phase("Target player mills two cards and loses 2 life.")
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((self.a.life, self.b.life), (life[0], life[1] - 2))
        self.assertEqual(len(self.b.graveyard), 2)

    def test_target_opponent_and_mixed_effects(self):
        effs = parse_sentence("Target opponent discards a card.")
        self.assertEqual((effs[0].target, effs[0].filter, effs[0].data["side"]), ("player", "opp", "theirs"))
        self.assertIsNone(parse_sentence("Target player draws a card and loses 1 life."))


class Interface(unittest.TestCase):
    def setUp(self):
        from mtgsim import cx_grammar as G
        self.G = G
        G._load()
        self.verbs, self.riders = list(G.VERBS), list(G.RIDERS)

    def tearDown(self):
        self.G.VERBS[:], self.G.RIDERS[:] = self.verbs, self.riders
        self.G._HEADS.clear()

    def test_imperative_with_an_object(self):
        G = self.G

        @G.verb(r"zorch (.+)", heads=("zorch",), subjects=("imperative",))
        def zorch(m, clause):
            obj = G.object_phrase(m[1])
            return [G.Part("destroy", obj=obj)] if obj is not None else None
        effs = parse_sentence("Zorch up to two target artifacts.")
        self.assertEqual([(e.kind, e.target, e.data.get("distinct")) for e in effs],
                         [("destroy", "permanent", True)] * 2)
        effs = parse_sentence("Zorch each creature you control.")
        self.assertEqual((effs[0].kind, effs[0].data["effects"][0].kind), ("cx_group", "destroy"))
        self.assertIsNone(parse_sentence("Zorch the moon."))

    def test_object_overrides_the_target_and_records_the_source(self):
        G = self.G

        @G.verb(r"blasts? (\d+) at (.+)", heads=("blast", "blasts"), subjects=("permanent",))
        def blast(m, clause):
            obj = G.object_phrase(m[2])
            return [G.Part("damage", int(m[1]), obj=obj)] if obj is not None else None
        effs = parse_sentence("~ blasts 3 at any target and gets +1/+0 until end of turn.")
        self.assertEqual([(e.kind, e.target) for e in effs], [("damage", "any"), ("pump", "self")])   # verbs of ~
        effs = parse_sentence("~ blasts 3 at any target.")
        self.assertEqual((effs[0].kind, effs[0].target, effs[0].data["source"]), ("damage", "any", "self"))
        effs = parse_sentence("~ blasts 2 at that creature's controller.")
        self.assertEqual((effs[0].target, effs[0].data["who"]), ("none", "controller"))
        effs = parse_sentence("~ blasts 2 at target opponent.")
        self.assertEqual((effs[0].target, effs[0].filter), ("player", "opp"))

    def test_rider_wraps_any_sentence(self):
        G = self.G

        @G.rider(r"(?P<body>.+) twice")
        def twice(m, inner):
            body = inner(m["body"])
            return body + body if body else None
        effs = parse_sentence("Target creature gains flying until end of turn twice.")
        self.assertEqual([e.kind for e in effs], ["grant", "grant"])


class ColorSide(Base):
    def target_for(self, text):
        spell = self.spell(text)
        with self.game.targeting(spell):
            return self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell)

    def test_colour_change_follows_the_effects_after_it(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(WOLF, self.b)
        self.assertIs(self.target_for("Target creature becomes red and gains haste until end of turn."), mine)
        self.assertIs(self.target_for("Target creature becomes blue until end of turn. Untap that creature."), mine)
        self.assertIs(self.target_for("Target creature becomes white until end of turn. Tap that creature."), theirs)
        self.assertIs(self.target_for("Target creature becomes black until end of turn."), theirs)


class LootSide(unittest.TestCase):
    def test_draw_then_discard_is_for_its_controller(self):
        effs = parse_sentence("Target player draws two cards, then discards a card.")
        self.assertEqual((effs[0].target, effs[0].data["side"]), ("player", "mine"))
        self.assertIsNone(parse_sentence("Target player discards a card, then draws a card."))   # helps and hurts


class TargetOpponent(Base):
    def test_ai_targets_the_opponent_even_when_the_verb_helps(self):
        spell = self.spell("Target opponent gains 3 life and draws a card.")
        with self.game.targeting(spell):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), self.b)
        eff = parse_sentence("Creatures target opponent controls get +1/+1 until end of turn.")[0]    # the grammar's reading
        self.assertEqual((eff.filter, eff.data["side"]), ("opp", "theirs"))
        with self.game.targeting(spell):
            self.assertEqual(self.game.legal_targets(self.a, eff), [self.b])
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, spell), self.b)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_armistice(self):
        from mtgsim.carddb import CardDB
        armistice = CardDB().get("Armistice")
        eff = next(e for e in armistice.activated[0].effects if e.target == "player")
        with self.game.targeting(armistice):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, armistice), self.b)


class MassDiminish(Base):
    def test_ai_casts_it_at_the_opponent(self):
        theirs, mine = self.perm(WOLF, self.b), self.perm(WOLF, self.a)
        spell = card("Test Diminish", "{U}", "Sorcery",
                     "Until your next turn, creatures target player controls have base power and toughness 1/1.")
        self.assertEqual(spell.unsupported, [])
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((theirs.power, mine.power), (1, 2))

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_card(self):
        from mtgsim.carddb import CardDB
        card_ = CardDB().get("Mass Diminish")
        eff = next(e for e in card_.spell_effects if e.target == "player")
        self.perm(BEAR, self.b)
        with self.game.targeting(card_):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, card_), self.b)


class PlayersCast(Base):
    def main_phase(self, text):
        spell = card("Test Spell", "{U}", "Sorcery", text)
        self.assertEqual(spell.unsupported, [], text)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        return spell

    def test_ai_casts_you_draw_and_lose_life(self):
        life = self.a.life
        spell = self.main_phase("You draw three cards and lose 3 life.")
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((self.a.life, len(self.a.hand)), (life - 3, 3))

    def test_ai_casts_each_opponent_discards(self):
        self.b.hand = [BEAR, BEAR]
        life = self.b.life
        spell = self.main_phase("Each opponent discards a card and loses 2 life.")
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual((len(self.b.hand), self.b.life), (1, life - 2))

    def test_ai_keeps_a_symmetric_wash(self):
        spell = self.main_phase("Each player loses 2 life.")
        self.assertIn(spell, self.a.hand)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_ambitions_cost(self):
        from mtgsim.carddb import CardDB
        ambition = CardDB().get("Ambition's Cost")
        from tests.test_templates import SWAMP
        for _ in range(4):
            self.perm(SWAMP, self.a)
        self.a.hand = [ambition]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(ambition, self.a.hand)


class PlayersAsRiders(Base):
    """A cx_players rider must not stop the spell it rides on from being cast."""
    def cast_on_board(self, text):
        from tests.test_templates import SWAMP
        spell = card("Test Spell", "{B}", "Sorcery", text)
        self.assertEqual(spell.unsupported, [], text)
        angel = self.perm(card("Test Angel", "{5}", "Creature — Angel", "Flying", 4, 4), self.b)
        self.perm(SWAMP, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        return spell not in self.a.hand, angel

    def test_destroy_then_each_player_gains_life(self):
        cast, angel = self.cast_on_board("Destroy target creature. Each player gains 3 life.")
        self.assertTrue(cast)
        self.assertNotIn(angel, self.b.battlefield)

    def test_destroy_then_its_owner_gains_life(self):
        cast, angel = self.cast_on_board("Destroy target creature. Its owner gains 4 life.")
        self.assertTrue(cast)
        self.assertEqual(self.b.life, 24)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_path_of_peace(self):
        from mtgsim.carddb import CardDB
        from tests.test_templates import PLAINS
        path = CardDB().get("Path of Peace")
        angel = self.perm(card("Test Angel", "{5}", "Creature — Angel", "Flying", 4, 4), self.b)
        for _ in range(4):
            self.perm(PLAINS, self.a)
        self.a.hand = [path]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(path, self.a.hand)
        self.assertNotIn(angel, self.b.battlefield)
