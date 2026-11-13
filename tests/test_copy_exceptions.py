"""Copy effects with explicit exceptions and entry modifiers (#340): "enter as a copy of any artifact on the
battlefield, except it's an enchantment in addition to its other types", "except it enters with X additional
+1/+1 counters on it", "except it isn't legendary", "except it's a 4/4 black Zombie". Checks exact copiable
values (types, subtypes, colours, P/T, keywords, legendary), counters as non-copiable entry state, copies of
copies, the legend rule, refusals of unknown exception text, and that the AI casts the newly full cards."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.copies import make_copy, parse_except
from mtgsim.engine import Game, Player, StackItem

from tests.test_templates import BEAR, DRAGON3, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
LEGEND = card("Test Legend", "{2}{G}", "Legendary Creature — Elf Druid", "", 3, 3)
TRINKET = card("Test Trinket", "{3}", "Artifact", "{T}: You gain 1 life.", cmc=3)


class ParseExcept(unittest.TestCase):
    def test_positive_clauses(self):
        cases = {
            "it's a 4/4 black Zombie": {"pt": (4, 4), "set_colors": frozenset("B"),
                                         "set_subtypes": frozenset({"Zombie"})},
            "it's 7/7": {"pt": (7, 7)},
            "it's an enchantment in addition to its other types": {"types": frozenset({"Enchantment"})},
            "it isn't legendary, is an artifact in addition to its other types, and has haste":
                {"legendary": False, "types": frozenset({"Artifact"}), "keywords": frozenset({"haste"})},
            "they're 2/2 and they aren't legendary": {"pt": (2, 2), "legendary": False},
            "they're 3/3 Dragon creatures in addition to their other types, and they have flying":
                {"pt": (3, 3), "types": frozenset({"Creature"}), "subtypes": frozenset({"Dragon"}),
                 "keywords": frozenset({"flying"})},
            "it enters with X additional +1/+1 counters on it": {"counters": {"+1/+1": "x"}},
            "it enters with an additional +1/+1 counter on it": {"counters": {"+1/+1": 1}},
            "it has changeling": {"changeling": True},
            "the token has flying and it isn't legendary": {"keywords": frozenset({"flying"}), "legendary": False},
            "it's a 4/4 Dragon creature with flying in addition to its other types":
                {"pt": (4, 4), "types": frozenset({"Creature"}), "subtypes": frozenset({"Dragon"}),
                 "keywords": frozenset({"flying"})},
            "it's a 1/1 green Squirrel creature token in addition to its other colors and types":
                {"pt": (1, 1), "colors": frozenset("G"), "types": frozenset({"Creature"}),
                 "subtypes": frozenset({"Squirrel"})},
            "its name is ~ and it's legendary in addition to its other types": {"keep_name": True, "legendary": True},
            "he's a Klingon Spy in addition to his other types and has menace":
                {"subtypes": frozenset({"Klingon", "Spy"}), "keywords": frozenset({"menace"})},
            "the copy is an artifact in addition to its other types": {"types": frozenset({"Artifact"})},
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_except(text), want)

    def test_unknown_exception_text_rejects_the_whole_clause(self):
        for text in ("it has this ability", "it isn't legendary, is an artifact in addition to its other types, "
                     "and has myriad", "it isn't a Zombie", "it has \"{T}: Add {U}.\"",
                     "it's legendary and snow in addition to its other types",
                     "it enters with an additional +1/+1 counter on it if it's a creature",
                     "it has haste and exalted", "it's a Vehicle artifact with crew 3 and it loses all other card types",
                     "it's an artifact. Activate only as a sorcery"):
            with self.subTest(text=text):
                self.assertIsNone(parse_except(text))

    def test_replacing_and_adding_characteristics(self):
        zombie = make_copy(DRAGON3, parse_except("it's a 4/4 black Zombie"))
        self.assertEqual((zombie.power, zombie.toughness, zombie.colors, zombie.subtypes, zombie.types),
                         (4, 4, frozenset("B"), frozenset({"Zombie"}), frozenset({"Creature"})))
        squirrel = make_copy(TRINKET, parse_except(
            "it's a 1/1 green Squirrel creature token in addition to its other colors and types"))
        self.assertEqual((squirrel.types, squirrel.subtypes, squirrel.colors, squirrel.power),
                         (frozenset({"Artifact", "Creature"}), frozenset({"Squirrel"}), frozenset("G"), 1))
        self.assertEqual(make_copy(LEGEND, parse_except("it isn't legendary")).legendary, False)
        self.assertEqual(make_copy(BEAR, parse_except("it's legendary in addition to its other types")).legendary,
                         True)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner=None):
        x = self.game.enter_battlefield(owner or self.a, c)
        x.sick = False
        return x

    def resolve(self, c, x=0, effects=None):
        if effects is None:
            effs = list(c.spell_effects)
            item = StackItem(self.a, effs, [None] * len(effs), card=c, name=c.name)
        else:                   # a triggered or activated ability of c
            effs = list(effects)
            item = StackItem(self.a, effs, [None] * len(effs), name=c.name, kind="trigger")
        item.x = x
        self.game.stack.append(item)
        self.game.resolve_top()


class InlineClones(Base):
    """Clone sentences written out, so these run without the card database."""

    def test_enchantment_copy_of_an_artifact_keeps_its_abilities(self):
        copy_art = card("Copy Artifact", "{1}{U}", "Enchantment", (
            "You may have Copy Artifact enter as a copy of any artifact on the battlefield, except it's an "
            "enchantment in addition to its other types."))
        self.assertEqual(copy_art.unsupported, [])
        self.perm(BEAR, self.b)
        self.perm(TRINKET, self.b)
        x = self.perm(copy_art)
        self.assertEqual(x.card.name, "Test Trinket")
        self.assertEqual(x.card.types, frozenset({"Artifact", "Enchantment"}))
        self.assertEqual(len(x.card.activated), len(TRINKET.activated))
        self.game.destroy(x)
        self.assertEqual([c.name for c in self.a.graveyard], ["Copy Artifact"])

    def test_x_additional_counters_are_entry_state_not_copiable(self):
        ego = card("Altered Ego", "{X}{2}{G}{U}", "Creature — Shapeshifter", (
            "You may have Altered Ego enter as a copy of any creature on the battlefield, except it enters with X "
            "additional +1/+1 counters on it."), 0, 0)
        self.assertEqual(ego.unsupported, [])
        self.perm(DRAGON3, self.b)
        x = self.game.enter_battlefield(self.a, ego, x=3)
        self.assertEqual((x.card.name, x.counters.get("+1/+1"), x.power, x.toughness), ("Big Dragon", 3, 6, 6))
        self.assertEqual(x.copiable_card.power, 3)      # the counters aren't part of the copiable values
        # A clone without the exception copying the Ego copies a plain Big Dragon.
        clone = card("Plain Clone", "{3}{U}", "Creature — Shapeshifter", (
            "You may have Plain Clone enter as a copy of a creature you control."), 0, 0)
        y = self.game.enter_battlefield(self.a, clone)
        self.assertEqual((y.card.name, y.counters.get("+1/+1", 0), y.power), ("Big Dragon", 0, 3))

    def test_copy_of_a_copy_keeps_the_first_exception(self):
        gargantuan = card("Quicksilver Gargantuan", "{5}{U}{U}", "Creature — Shapeshifter", (
            "You may have Quicksilver Gargantuan enter as a copy of any creature on the battlefield, except it's "
            "7/7."), 7, 7)
        metamorph = card("Phyrexian Metamorph", "{3}{U/P}", "Artifact Creature — Phyrexian Shapeshifter", (
            "You may have Phyrexian Metamorph enter as a copy of any artifact or creature on the battlefield, "
            "except it's an artifact in addition to its other types."), 0, 0)
        self.assertEqual(gargantuan.unsupported + metamorph.unsupported, [])
        self.perm(BEAR, self.b)
        g = self.game.enter_battlefield(self.a, gargantuan)
        self.assertEqual((g.card.name, g.power, g.toughness), (BEAR.name, 7, 7))
        m = self.game.enter_battlefield(self.a, metamorph)
        self.assertEqual((m.card.name, m.power, m.toughness), (BEAR.name, 7, 7))      # 707.9b: copied 7/7
        self.assertEqual(m.card.types, frozenset({"Creature", "Artifact"}))
        self.assertEqual(m.card.subtypes, BEAR.subtypes)

    def test_opponent_scope_and_added_subtypes(self):
        impostor = card("Malleable Impostor", "{2}{U}", "Creature — Faerie Shapeshifter", (
            "Flash\nYou may have Malleable Impostor enter as a copy of a creature an opponent controls, except "
            "it's a Faerie Shapeshifter in addition to its other types and it has flying."), 0, 0)
        self.assertEqual(impostor.unsupported, [])
        self.perm(DRAGON3, self.a)          # mine, bigger: not eligible
        self.perm(BEAR, self.b)
        x = self.game.enter_battlefield(self.a, impostor)
        self.assertEqual(x.card.name, BEAR.name)
        self.assertTrue({"Faerie", "Shapeshifter"} <= x.card.subtypes)
        self.assertTrue(x.has("flying"))

    def test_clone_avoids_a_legend_it_would_lose_to_the_legend_rule(self):
        clone = card("Plain Clone", "{3}{U}", "Creature — Shapeshifter", (
            "You may have Plain Clone enter as a copy of any creature on the battlefield."), 0, 0)
        self.perm(LEGEND, self.a)
        self.perm(BEAR, self.b)
        x = self.game.enter_battlefield(self.a, clone)
        self.assertEqual(x.card.name, BEAR.name)


class TokenCopies(Base):
    def test_token_copy_of_a_legend_isnt_legendary_and_survives_the_legend_rule(self):
        dup = card("Irenicus's Vile Duplication", "{3}{U}", "Sorcery", (
            "Create a token that's a copy of target creature you control, except the token has flying and it "
            "isn't legendary."))
        self.assertEqual(dup.unsupported, [])
        self.perm(LEGEND, self.a)
        self.resolve(dup)
        self.game.state_based_actions()
        legends = [x for x in self.a.battlefield if x.card.name == LEGEND.name]
        self.assertEqual(len(legends), 2)
        token = next(x for x in legends if x.card.is_token)
        self.assertEqual((token.card.legendary, token.has("flying")), (False, True))

    def test_without_the_exception_the_legend_rule_applies(self):
        dup = card("Plain Duplication", "{3}{U}", "Sorcery", (
            "Create a token that's a copy of target creature you control."))
        self.perm(LEGEND, self.a)
        self.resolve(dup)
        self.game.state_based_actions()
        self.assertEqual(sum(x.card.name == LEGEND.name for x in self.a.battlefield), 1)

    def test_token_copy_enters_with_an_additional_counter(self):
        lake = card("Littjara Mirrorlake", "", "Land", (
            "{T}: Add {G} or {U}.\n{2}{G}{G}{U}, {T}, Sacrifice Littjara Mirrorlake: Create a token that's a "
            "copy of target creature you control, except it enters with an additional +1/+1 counter on it. "
            "Activate only as a sorcery."))
        self.assertEqual(lake.unsupported, [])
        self.perm(BEAR)
        effects = lake.activated[-1].effects
        self.resolve(lake, effects=effects)
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual((token.card.name, token.counters.get("+1/+1"), token.power), (BEAR.name, 1, BEAR.power + 1))
        self.assertEqual(token.copiable_card.power, BEAR.power)

    def test_plural_type_and_keyword_exception(self):
        astral = card("Astral Dragon", "{6}{U}{U}", "Creature — Dragon", (
            "Flying\nWhen Astral Dragon enters, create two tokens that are copies of target noncreature permanent, "
            "except they're 3/3 Dragon creatures in addition to their other types, and they have flying."), 4, 4)
        self.assertEqual(astral.unsupported, [])
        self.perm(TRINKET, self.b)
        trig = astral.triggers[0]
        self.resolve(astral, effects=trig.effects)
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 2)
        for t in tokens:
            self.assertEqual((t.card.name, t.power, t.toughness, t.card.types, t.has("flying")),
                             ("Test Trinket", 3, 3, frozenset({"Artifact", "Creature"}), True))
            self.assertIn("Dragon", t.card.subtypes)


@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class DatabaseCards(Base):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB()

    def test_newly_full_cards_parse(self):
        for name in ("Copy Artifact", "Copy Land", "Altered Ego", "Phyrexian Metamorph", "Surgical Metamorph",
                     "Quicksilver Gargantuan", "Omni-Changeling", "Dack's Duplicate", "Malleable Impostor",
                     "Voq, Torchbearer", "Astral Dragon", "Irenicus's Vile Duplication", "Will of the Temur",
                     "Uugguu, the Omniplasm", "Littjara Mirrorlake", "Welcome to Mini-apolis", "Nightmare Shepherd"):
            with self.subTest(card=name):
                c = self.db.get(name)
                self.assertEqual((c.unsupported, c.approximations), ([], []))

    def test_still_partial(self):
        for name in ("Volrath, the Shapestealer", "Auton Soldier", "Spark Double", "Machine God's Effigy", "Moritte of the Frost"):
            with self.subTest(card=name):
                self.assertNotEqual(self.db.get(name).unsupported, [])

    def test_omni_changeling_copy_has_changeling(self):
        self.perm(BEAR, self.b)
        x = self.game.enter_battlefield(self.a, self.db.get("Omni-Changeling"))
        self.assertEqual(x.card.name, BEAR.name)
        self.assertTrue(x.card.changeling)

    def test_copy_land_copies_a_land_as_an_enchantment_land(self):
        forest = self.db.get("Forest")
        self.perm(forest, self.b)
        x = self.game.enter_battlefield(self.a, self.db.get("Copy Land"))
        self.assertEqual((x.card.name, x.card.types), ("Forest", frozenset({"Land", "Enchantment"})))
        self.assertEqual(x.card.produces, forest.produces)

    def test_ai_casts_altered_ego_and_metamorph(self):
        for name in ("Altered Ego", "Phyrexian Metamorph"):
            with self.subTest(card=name):
                self.setUp()
                self.perm(DRAGON3, self.b)
                island, forest = self.db.get("Island"), self.db.get("Forest")
                for land in [island] * 4 + [forest] * 3:
                    self.perm(land)
                c = self.db.get(name)
                self.a.hand = [c]
                self.a.ai.main_phase(self.game, self.a)
                self.game.run_priority()
                copies = [x for x in self.a.battlefield if x.card.name == DRAGON3.name]
                self.assertEqual(len(copies), 1, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class BecomeCopy(Base):
    """"~ becomes a copy of ..., except it has this ability": durations, retained abilities, "that creature"."""

    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB()

    def trigger(self, perm, index=0, context=None):
        trig = perm.card.triggers[index]
        item = StackItem(perm.controller, list(trig.effects), [None] * len(trig.effects), source=perm,
                         name="trigger", kind="trigger", context=context)
        self.game.stack.append(item)
        self.game.resolve_top()

    def cleanup(self):
        from mtgsim import copies
        for pl in self.game.players:
            for x in pl.battlefield:
                copies.revert(x)

    def test_cryptoplasm_lasting_copy_keeps_its_upkeep_ability(self):
        cp = self.perm(self.db.get("Cryptoplasm"))
        self.perm(DRAGON3, self.b)
        self.trigger(cp)
        self.assertEqual((cp.card.name, cp.power), (DRAGON3.name, 3))
        self.assertEqual([t.event for t in cp.card.triggers if t.event == "upkeep"], ["upkeep"])
        self.cleanup()                                          # no duration: the copy doesn't end at cleanup
        self.assertEqual(cp.card.name, DRAGON3.name)
        big = card("Huge Thing", "{6}{G}", "Creature — Beast", "", 7, 7)
        self.perm(big, self.b)
        self.trigger(cp, index=[t.event for t in cp.card.triggers].index("upkeep"))     # the retained ability
        self.assertEqual((cp.card.name, cp.power), ("Huge Thing", 7))
        self.game.destroy(cp)
        self.assertEqual([c.name for c in self.a.graveyard], ["Cryptoplasm"])

    def test_thespians_stage_keeps_its_activated_ability(self):
        stage = self.perm(self.db.get("Thespian's Stage"))
        vesuva_target = self.perm(self.db.get("Dryad Arbor"), self.b)
        effects = stage.card.activated[0].effects
        item = StackItem(self.a, list(effects), [None], source=stage, name="ability", kind="ability")
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual(stage.card.name, vesuva_target.card.name)
        self.assertEqual(len(stage.card.activated), len(vesuva_target.card.activated) + 1)
        self.assertIs(stage.card.activated[-1].effects[0], effects[0])

    def test_hulkling_until_end_of_turn_keeps_name_and_reverts(self):
        h = self.perm(self.db.get("Hulkling, Young Avenger"))
        self.perm(card("Huge Thing", "{6}{G}", "Creature — Beast", "Trample", 7, 7), self.b)
        self.trigger(h)
        self.assertEqual((h.card.name, h.power, h.toughness, h.has("flying"), h.has("trample")),
                         ("Hulkling, Young Avenger", 4, 4, True, True))
        self.assertEqual(h.card.subtypes, frozenset({"Beast"}))
        self.cleanup()
        self.assertEqual((h.card.subtypes, h.has("trample")), (frozenset({"Skrull", "Kree", "Hero"}), False))

    def test_crystalline_resonance_lasts_until_your_next_turn(self):
        from mtgsim.advanced_templates import begin_turn
        cr = self.perm(self.db.get("Crystalline Resonance"))
        self.perm(DRAGON3, self.b)
        self.trigger(cr)
        self.assertEqual(cr.card.name, DRAGON3.name)
        self.cleanup()
        begin_turn(self.game, self.b)
        self.assertEqual(cr.card.name, DRAGON3.name)            # not over at cleanup or on the opponent's turn
        begin_turn(self.game, self.a)
        self.assertEqual(cr.card.name, "Crystalline Resonance")

    def test_unstable_shapeshifter_must_copy_the_entering_creature(self):
        us = self.perm(self.db.get("Unstable Shapeshifter"))
        self.perm(DRAGON3, self.b)
        bear = self.perm(BEAR, self.b)
        self.trigger(us, context=bear)
        self.assertEqual(us.card.name, BEAR.name)               # no "may": even a worse creature is copied
        self.assertTrue(any(t.event == "filtered_enters" for t in us.card.triggers))

    def test_renegade_doppelganger_may_decline_a_worse_creature(self):
        rd = self.perm(self.db.get("Renegade Doppelganger"))
        token = self.perm(card("Tiny Thing", "", "Creature — Insect", "", 1, 1))
        self.trigger(rd, context=token)
        self.assertEqual(rd.card.name, "Renegade Doppelganger")
        self.trigger(rd, context=self.perm(DRAGON3))
        self.assertEqual(rd.card.name, DRAGON3.name)

    def test_cemetery_puca_copies_the_dead_creature_by_last_known_information(self):
        puca = self.perm(self.db.get("Cemetery Puca"))
        for _ in range(2):
            self.perm(self.db.get("Island"))
        dragon = self.perm(DRAGON3, self.b)
        self.game.destroy(dragon)
        self.game.run_priority()
        self.assertEqual(puca.card.name, DRAGON3.name)
        self.assertEqual(sum(t.event == "creature_dies" for t in puca.card.triggers), 1)

    def test_ai_activates_a_lasting_become_copy(self):
        m = self.perm(self.db.get("Mizzium Transreliquat"))
        self.perm(self.db.get("Wurmcoil Engine"), self.b)
        for land in ["Island"] * 3 + ["Mountain"] * 3:
            self.perm(self.db.get(land))
        self.a.hand = []
        self.game.step = "main2"
        self.a.ai.use_abilities(self.game, self.a)
        self.game.run_priority()
        self.assertEqual(m.card.name, "Wurmcoil Engine")

@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class SpellCopies(Base):
    """"copy it, except the copy isn't legendary / is an artifact in addition to its other types"."""

    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB()

    def lands(self, name, n):
        for _ in range(n):
            self.perm(self.db.get(name))

    def test_sixth_doctor_copy_of_a_legend_isnt_legendary(self):
        self.perm(self.db.get("The Sixth Doctor"))
        self.lands("Plains", 3)
        legend = card("Test Legend", "{2}{W}", "Legendary Creature — Human Knight", "", 3, 3)
        self.a.hand = [legend]
        self.game.cast(self.a, legend)
        self.game.run_priority()
        self.game.state_based_actions()
        mine = [x for x in self.a.battlefield if x.card.name == "Test Legend"]
        self.assertEqual(sorted((x.card.is_token, x.card.legendary) for x in mine), [(False, True), (True, False)])

    def test_tawnos_copy_is_an_artifact_token(self):
        self.perm(self.db.get("Tawnos, the Toymaker"))
        self.lands("Forest", 3)
        beast = card("Test Beast", "{2}{G}", "Creature — Beast", "", 3, 3)
        self.a.hand = [beast]
        self.game.cast(self.a, beast)
        self.game.run_priority()
        beasts = sorted(((x.card.is_token, x.card.types) for x in self.a.battlefield if x.card.name == "Test Beast"),
                        key=lambda t: t[0])
        self.assertEqual(beasts, [(False, frozenset({"Creature"})), (True, frozenset({"Creature", "Artifact"}))])

    def test_tawnos_ignores_other_creatures(self):
        self.perm(self.db.get("Tawnos, the Toymaker"))
        self.lands("Forest", 2)
        self.a.hand = [BEAR]
        self.game.cast(self.a, BEAR)
        self.game.run_priority()
        self.assertEqual(sum(x.card.name == BEAR.name for x in self.a.battlefield), 1)

    def test_unknown_spell_copy_exception_stays_a_gap(self):
        c = card("Odd Copier", "{1}{U}", "Creature — Wizard", (
            "Whenever you cast an instant spell, copy it, except the copy has \"Draw a card.\""), 1, 1)
        self.assertNotEqual(c.unsupported, [])

@unittest.skipUnless(DB_FILE.exists(), "needs the card database")
class TokenCopyReferents(Base):
    """Token copies of "that card", "equipped / enchanted creature", "each creature target opponent controls",
    and "its controller creates a token that's a copy of it"."""

    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB()

    def fire_trigger(self, perm, event, context=None):
        trig = next(t for t in perm.card.triggers if t.event == event)
        targets = self.game.auto_targets(perm.controller, list(trig.effects))
        item = StackItem(perm.controller, list(trig.effects), targets, source=perm,
                         name="trigger", kind="trigger", context=context)
        self.game.stack.append(item)
        self.game.run_priority()

    def tokens(self, p=None):
        return [x for x in (p or self.a).battlefield if x.card.is_token]

    def test_seance_copies_the_exiled_card_as_a_spirit_until_end_step(self):
        s = self.perm(self.db.get("Séance"))
        self.a.graveyard.append(DRAGON3)
        self.fire_trigger(s, "each_upkeep")
        tok = self.tokens()
        self.assertEqual([(t.card.name, "Spirit" in t.card.subtypes, "Dragon" in t.card.subtypes) for t in tok],
                         [(DRAGON3.name, True, True)])
        self.assertEqual([c.name for c in self.a.exile], [DRAGON3.name])
        self.assertIn((tok[0], "exile"), self.game.end_cleanup)       # "Exile it at the beginning of the next end step"

    def test_blastoneuron_token_has_haste_and_is_sacrificed(self):
        self.a.graveyard.append(BEAR)
        b = self.game.enter_battlefield(self.a, self.db.get("Blastoneuron"))
        self.game.run_priority()
        tok = self.tokens()
        self.assertEqual([t.card.name for t in tok], [BEAR.name])
        self.assertTrue(tok[0].has("haste"))
        self.assertFalse("haste" in tok[0].copiable_card.keywords)       # granted, not a copiable value
        self.assertTrue(any(x[0] is tok[0] for x in self.game.end_cleanup))
        self.assertIsNotNone(b)

    def test_helm_of_the_host_copies_the_equipped_legend_nonlegendary_with_haste(self):
        helm = self.perm(self.db.get("Helm of the Host"))
        legend = self.perm(LEGEND)
        helm.attached_to = legend
        self.fire_trigger(helm, "begin_combat")
        self.game.state_based_actions()
        tok = self.tokens()
        self.assertEqual([(t.card.name, t.card.legendary, t.has("haste")) for t in tok], [(LEGEND.name, False, True)])
        self.assertIn(legend, self.a.battlefield)

    def test_followed_footsteps_copies_the_enchanted_creature(self):
        ff = self.perm(self.db.get("Followed Footsteps"))
        dragon = self.perm(DRAGON3, self.b)
        ff.aura_host = dragon
        self.fire_trigger(ff, "upkeep")
        self.assertEqual([t.card.name for t in self.tokens()], [DRAGON3.name])

    def test_penumbra_umbra_copies_its_last_creature_in_black(self):
        # The trigger itself doesn't fire on a noncreature yet (#369); its effect is resolved here after the
        # Aura has left, reading "enchanted creature" by last known information.
        pu = self.perm(self.db.get("Penumbra Umbra"))
        bear = self.perm(BEAR)
        pu.aura_host = bear
        bear.auras.append(pu)
        self.game.destroy(pu)
        self.assertIsNone(pu.aura_host)
        self.fire_trigger(pu, "dies")
        tok = self.tokens()
        self.assertEqual([(t.card.name, t.card.colors) for t in tok], [(BEAR.name, frozenset("B"))])

    def test_clone_legion_copies_each_creature_of_the_opponent_even_with_hexproof(self):
        warded = card("Shy Thing", "{1}{G}", "Creature — Elf", "Hexproof", 1, 1)
        self.perm(BEAR, self.b)
        self.perm(warded, self.b)
        self.perm(DRAGON3)
        self.resolve(self.db.get("Clone Legion"))
        self.assertEqual(sorted(t.card.name for t in self.tokens()), sorted([BEAR.name, "Shy Thing"]))

    def test_mirror_universe_intrusion_kicked_copies_each_creature(self):
        mui = self.db.get("Mirror Universe Intrusion")
        kicked = next(a for a in mui.alt_costs if a.kind == "kicker")
        self.perm(BEAR, self.b)
        self.perm(DRAGON3, self.b)
        self.resolve(mui, effects=kicked.effects)
        self.assertEqual(sorted((t.card.name, t.has("menace")) for t in self.tokens()),
                         sorted([(BEAR.name, True), (DRAGON3.name, True)]))

    def test_dedicated_dollmaker_gives_the_copy_to_the_exiled_permanents_controller(self):
        legend = self.perm(LEGEND, self.b)
        self.game.enter_battlefield(self.a, self.db.get("Dedicated Dollmaker"))
        self.game.run_priority()
        self.assertNotIn(legend, self.b.battlefield)
        tok = self.tokens(self.b)
        self.assertEqual([(t.card.name, t.card.legendary, t.card.types) for t in tok],
                         [(LEGEND.name, False, frozenset({"Creature", "Artifact"}))])
        self.assertEqual(self.tokens(self.a), [])

    def test_bramble_sovereign_copy_goes_to_that_creatures_controller(self):
        self.perm(self.db.get("Bramble Sovereign"))
        for land in ["Forest"] * 2:
            self.perm(self.db.get(land))
        self.game.enter_battlefield(self.a, DRAGON3)
        self.game.run_priority()
        self.assertEqual([t.card.name for t in self.tokens()], [DRAGON3.name])
        self.assertEqual(self.tokens(self.b), [])
        # the copy of an opponent's creature would be theirs: same rule, other player
        effects = next(t for t in self.a.battlefield if t.card.name == "Bramble Sovereign").card.triggers[0].effects
        theirs = self.perm(BEAR, self.b)
        import dataclasses
        paid = dataclasses.replace(effects[-1], cond="")         # as if {1}{G} was paid
        item = StackItem(self.a, [paid], [None], name="trigger", kind="trigger", context=theirs)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual([t.card.name for t in self.tokens(self.b)], [BEAR.name])

    def test_hashaton_copies_the_discarded_creature_card_as_a_zombie(self):
        self.perm(self.db.get("Hashaton, Scarab's Fist"))
        for land in ["Island"] * 3:
            self.perm(self.db.get(land))
        self.a.hand = [DRAGON3]
        self.game.discard_card(self.a, DRAGON3)
        self.game.run_priority()
        tok = self.tokens()
        self.assertEqual([(t.card.name, t.power, t.card.subtypes, t.card.colors, t.tapped) for t in tok],
                         [(DRAGON3.name, 4, frozenset({"Zombie"}), frozenset("B"), True)])


if __name__ == "__main__":
    unittest.main()
