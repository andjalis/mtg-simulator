"""Die rolls, batch 3: several dice at once, per-face amounts and new check wordings.

The foundation: a ``die_roll`` may roll several dice (``count``), the faces of the last
roll are kept per player, and ``die_amount`` / ``die_check`` effects read them back
through an aggregate (``chosen`` / ``other`` for "choose one result", the ``total``,
their ``difference``, or the count of ``even`` / ``odd`` faces). Plus the smaller die
sizes (d4/d8/d10/d12), the party die, and the "If the result is 4 or less, ..." /
"If the roll was 4 or higher, ..." / doubles / repeat-total check wordings.
"""
import random
import unittest

from mtgsim import dungeon_mechanics
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

ENDEAVOR = card("Wild Endeavor", "{3}{G}{G}", "Sorcery",
                "Roll two d4 and choose one result. Create a number of 3/3 green Beast "
                "creature tokens equal to that result. Then search your library for a "
                "number of basic land cards equal to the other result, put them onto the "
                "battlefield tapped, then shuffle.")
VALIANT = card("Valiant Endeavor", "{4}{W}{W}", "Sorcery",
               "Roll two d6 and choose one result. Destroy each creature with power "
               "greater than or equal to that result. Then create a number of 2/2 white "
               "Knight creature tokens with vigilance equal to the other result.")
PAIR = card("Pair o' Dice Lost", "{U}{U}", "Sorcery",
            "Roll two six-sided dice. Return any number of cards with total mana value X "
            "or less from your graveyard to your hand, where X is the total of those "
            "results. Exile Pair o' Dice Lost.")
CLOWN_CAR = card("Clown Car", "{X}{W}", "Artifact — Vehicle",
                 "When this Vehicle enters, roll X six-sided dice. For each odd result, "
                 "create a 1/1 white Clown Robot artifact creature token. For each even "
                 "result, put a +1/+1 counter on this Vehicle.", None, None)
MATHISE = card("Mathise, Surge Channeler", "{1}{U}", "Creature — Human Wizard",
               "Whenever you cast an instant or sorcery spell with mana value 3 or "
               "greater, roll a d20.\n1—9 | Each player draws a card.\n"
               "10—19 | You draw a card.\n20 | You draw two cards.", 1, 3)
CANNONBALL = card("Non-Human Cannonball", "{3}{R}", "Creature — Goblin Warrior",
                  "When this creature dies, roll a six-sided die. If the result is 4 or "
                  "less, this creature deals that much damage to you.", 4, 3)
MONOXA = card("Monoxa, Midway Manager", "{2}{B}", "Legendary Creature — Zombie",
              "Whenever you roll a 3 or higher, Monoxa gains first strike until end of "
              "turn. If the roll was 4 or higher, it gains menace until end of turn. "
              "If the roll was 5 or higher, it gains lifelink until end of turn.", 2, 2)
JAIL = card("GO TO JAIL", "{2}{W}", "Enchantment",
            "When this enchantment enters, exile target creature an opponent controls "
            "until this enchantment leaves the battlefield.\nAt the beginning of the "
            "upkeep of the exiled card's owner, that player rolls two six-sided dice. "
            "If they roll doubles, sacrifice this enchantment.")
CHICKEN = card("Free-Range Chicken", "{2}{G}", "Creature — Bird",
               "{1}{G}: Roll two six-sided dice. If both results are the same, this "
               "creature gets +X/+X until end of turn, where X is that result. If the "
               "total of those results is equal to any other total you have rolled this "
               "turn for this ability, sacrifice it.", 2, 2)
BOBBLEHEAD = card("Luck Bobblehead", "{3}", "Artifact — Bobblehead",
                 "{1}, {T}: Roll X six-sided dice, where X is the number of Bobbleheads "
                 "you control. Create a tapped Treasure token for each even result.")


def _kinds(effects):
    return [e.kind for e in effects]


class ParseDiceBatch3(unittest.TestCase):
    def test_two_dice_and_choose_one(self):
        self.assertEqual([(e.kind, e.data.get("sides"), e.data.get("count"))
                          for e in ENDEAVOR.spell_effects][:1],
                         [("die_roll", 4, 2)])

    def test_that_and_other_result_effects(self):
        kinds = [e.kind for e in ENDEAVOR.spell_effects]
        self.assertEqual(kinds, ["die_roll", "die_amount", "die_amount"])
        self.assertEqual([e.data.get("agg") for e in ENDEAVOR.spell_effects[1:3]],
                         ["chosen", "other"])
        self.assertEqual(ENDEAVOR.spell_effects[2].data["then"][0].kind, "fetch_basic_n")

    def test_smaller_dice_and_party_die(self):
        for text, sides in (("Roll a d4.", 4), ("Roll a d8.", 8), ("Roll a d10.", 10),
                            ("Roll a d12.", 12), ("Roll a four-sided die.", 4)):
            effs, bad = _parse_effects(text)
            self.assertFalse(bad, text)
            self.assertEqual((effs[0].kind, effs[0].data.get("sides")), ("die_roll", sides), text)
        effs, bad = _parse_effects("Roll the party die.")
        self.assertFalse(bad)
        self.assertTrue(effs[0].data.get("party"))

    def test_x_dice_count(self):
        effs, bad = _parse_effects("Roll X six-sided dice.")
        self.assertFalse(bad)
        self.assertEqual(effs[0].data.get("count"), "x")
        effs, bad = _parse_effects("Roll X six-sided dice, where X is the number of "
                                   "Bobbleheads you control.")
        self.assertFalse(bad)
        self.assertEqual(effs[0].data.get("xq"), ("count", "Bobblehead"))   # shared xq rule

    def test_new_result_carriers(self):
        for text, kind in (("Target player mills X cards, where X is the result.", "mill"),
                           ("Target opponent loses life equal to the result.", "lose_life"),
                           ("Monstrosity X, where X is the result.", "monstrosity")):
            effs, bad = _parse_effects(f"Roll a d6. {text}")
            self.assertFalse(bad, text)
            self.assertEqual(effs[-1].data["then"][0].kind, kind, text)

    def test_die_check_wordings(self):
        effs, bad = _parse_effects("Roll a six-sided die. If the result is 4 or less, ~ deals "
                                   "that much damage to you.")
        self.assertFalse(bad)
        check = effs[-1]
        self.assertEqual((check.kind, check.data["lo"], check.data["hi"]),
                         ("die_check", 1, 4))
        self.assertEqual(check.data["then"][0].kind, "lose_life")
        effs, bad = _parse_effects("Roll a d6. If the roll was 4 or higher, it gains menace "
                                   "until end of turn.")
        self.assertFalse(bad)
        self.assertEqual(effs[-1].data["then"][0].data["keyword"], "menace")

    def test_doubles_and_repeat_checks(self):
        effs, bad = _parse_effects("Roll two six-sided dice. If you roll doubles, sacrifice ~.")
        self.assertFalse(bad)
        self.assertTrue(effs[-1].data["doubles"])
        effs, bad = _parse_effects("If both results are the same, ~ gets +X/+X until end of "
                                   "turn, where X is that result.")
        self.assertFalse(bad)
        self.assertTrue(effs[-1].data["doubles"])

    def test_as_enters_roll_trigger(self):
        triggers = [(t.event, _kinds(t.effects)) for t in CLOWN_CAR.triggers]
        self.assertIn(("etb", ["die_roll", "die_amount", "die_amount"]), triggers)
        roll = next(t for t in CLOWN_CAR.triggers if t.event == "etb").effects[0]
        self.assertEqual((roll.data["sides"], roll.data["count"]), (6, "x"))

    def test_cast_cmc_trigger_and_outcomes(self):
        events = [t.event for t in MATHISE.triggers]
        self.assertIn("cast_cmc", events)
        self.assertIn("die:1-9", events)
        self.assertIn("die:10-19", events)
        self.assertIn("die:20-20", events)

    def test_jail_exile_and_upkeep_roll(self):
        events = [t.event for t in JAIL.triggers]
        self.assertIn("opp_upkeep", events)
        upkeep = next(t for t in JAIL.triggers if t.event == "opp_upkeep")
        self.assertEqual(_kinds(upkeep.effects), ["die_roll", "die_check"])

    def test_destroy_power_ge_parse(self):
        effs, bad = _parse_effects("Destroy each creature with power greater than or equal to "
                                   "that result.")
        self.assertFalse(bad)
        self.assertEqual(effs[-1].data["then"][0].kind, "destroy_power_ge")


class DiceEngineBatch3(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def faces(self, *values, who=None):
        """Pin the last roll's faces (and its total) for the die_amount/die_check reads."""
        who = who or self.a
        self.g.__dict__.setdefault("_die_faces", {})[who] = list(values)
        self.g.__dict__.setdefault("_die_rolls", {})[who] = sum(values)

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target
        self.g.settle()
        return item

    def rolled(self, p=None):
        return dungeon_mechanics._last_die(self.g, p or self.a)

    def treasures(self, p=None):
        return [x for x in (p or self.a).battlefield if x.card.token_kind == "treasure"]

    def test_two_dice_roll_stores_faces(self):
        self.apply("Roll two six-sided dice.")
        faces = self.g.__dict__["_die_faces"][self.a]
        self.assertEqual(len(faces), 2)
        self.assertEqual(self.rolled(), sum(faces))

    def test_chosen_and_other_result(self):
        self.apply("Roll two six-sided dice. Create a number of Treasure tokens equal to "
                   "that result. Create a number of Treasure tokens equal to the other result.")
        faces = self.g.__dict__["_die_faces"][self.a]
        self.assertEqual(len(self.treasures()), sum(faces))

    def test_even_face_tokens(self):
        state = self.g.rng.getstate()
        self.apply("Roll two six-sided dice. Create a tapped Treasure token for each even result.")
        faces = self.g.__dict__["_die_faces"][self.a]
        self.g.rng.setstate(state)
        self.assertEqual(len(self.treasures()), sum(1 for f in faces if f % 2 == 0))
        self.assertTrue(all(x.tapped for x in self.treasures()))

    def test_odd_face_tokens(self):
        self.apply("Roll two six-sided dice. For each odd result, create a 1/1 white Clown "
                   "Robot artifact creature token.")
        faces = self.g.__dict__["_die_faces"][self.a]
        robots = [x for x in self.a.battlefield if "Robot" in x.card.subtypes]
        self.assertEqual(len(robots), sum(1 for f in faces if f % 2 == 1))

    def test_regrow_cmc_budget(self):
        bear2 = card("Big Bear", "{3}{G}", "Creature — Bear", "", 4, 4)
        self.a.graveyard = [bear2, ISLAND, ISLAND]
        self.faces(4, 4)
        self.apply("Return any number of cards with total mana value X or less from your "
                   "graveyard to your hand, where X is the total of those results.")
        names = sorted(c.name for c in self.a.hand)
        self.assertEqual(names, ["Big Bear", "Island", "Island"])

    def test_regrow_cmc_budget_binding(self):
        bear2 = card("Big Bear", "{3}{G}", "Creature — Bear", "", 4, 4)
        self.a.graveyard = [bear2, bear2]
        self.faces(2, 2)
        self.apply("Return any number of cards with total mana value X or less from your "
                   "graveyard to your hand, where X is the total of those results.")
        self.assertEqual([c.name for c in self.a.hand], ["Big Bear"])   # one 4 fits, not two

    def test_destroy_power_ge(self):
        bear = self.g.enter_battlefield(self.b, BEAR)          # 2/2
        self.faces(1, 2)          # "that result" is the higher face
        self.apply("Destroy each creature with power greater than or equal to that result.")
        self.assertNotIn(bear, self.b.battlefield)

    def test_destroy_power_ge_spares_smaller(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        self.faces(3, 4)
        self.apply("Destroy each creature with power greater than or equal to that result.")
        self.assertIn(bear, self.b.battlefield)

    def test_fetch_basic_n(self):
        self.a.library = [ISLAND] * 20
        self.faces(1, 4)
        before = sum(x.card.is_land for x in self.a.battlefield)
        self.apply("Search your library for a number of basic land cards equal to the other "
                   "result, put them onto the battlefield tapped, then shuffle.")
        lands = [x for x in self.a.battlefield if x.card.is_land]
        self.assertEqual(len(lands) - before, 1)
        self.assertTrue(lands[-1].tapped)

    def test_doubles_check(self):
        chicken = self.g.enter_battlefield(self.a, CHICKEN)
        chicken.sick = False
        effects = CHICKEN.activated[0].effects          # the {1}{G} ability's die_check
        self.assertEqual(_kinds(effects), ["die_roll", "die_check", "die_check"])
        effects = [e for e in effects if e.kind == "die_check"]
        self.faces(3, 3)
        self.g.resolve(self.a, effects[0], chicken, StackItem(self.a, [], [], source=chicken))
        self.assertEqual((chicken.power, chicken.toughness), (5, 5))
        self.faces(2, 3)
        self.g.resolve(self.a, effects[0], chicken, StackItem(self.a, [], [], source=chicken))
        self.assertEqual((chicken.power, chicken.toughness), (5, 5))   # no second pump

    def test_doubles_sacrifice(self):
        jail = self.g.enter_battlefield(self.a, JAIL)
        effects = [e for e in next(t for t in JAIL.triggers
                                   if t.event == "opp_upkeep").effects if e.kind == "die_check"]
        self.faces(4, 4)
        self.g.resolve(self.a, effects[-1], jail, StackItem(self.a, [], [], source=jail))
        self.g.settle()
        self.assertNotIn(jail, self.a.battlefield)
        jail2 = self.g.enter_battlefield(self.a, JAIL)
        self.faces(4, 5)
        self.g.resolve(self.a, effects[-1], jail2, StackItem(self.a, [], [], source=jail2))
        self.g.settle()
        self.assertIn(jail2, self.a.battlefield)

    def test_result_or_less_damage_to_you(self):
        check = [e for e in CANNONBALL.triggers[0].effects if e.kind == "die_check"][0]
        self.faces(4)
        life = self.a.life
        self.g.resolve(self.a, check, None, StackItem(self.a, [], []))
        self.assertEqual(self.a.life, life - 4)
        self.faces(5)
        life = self.a.life
        self.g.resolve(self.a, check, None, StackItem(self.a, [], []))
        self.assertEqual(self.a.life, life)

    def test_roll_was_higher_grants_keyword(self):
        monoxa = self.g.enter_battlefield(self.a, MONOXA)
        effects = MONOXA.triggers[0].effects       # the you_roll>=3 listener's body
        self.assertEqual(_kinds(effects), ["grant", "die_check", "die_check"])
        effects = [e for e in effects if e.kind == "die_check"]
        self.faces(4)
        self.g.resolve(self.a, effects[0], monoxa, StackItem(self.a, [], [], source=monoxa))
        self.assertTrue(monoxa.has("menace"))

    def test_dynamic_bound_by_creature_type(self):
        robot = card("Robot Pal", "{1}", "Artifact Creature — Robot", "", 1, 1)
        effects, ignored = _parse_effects("If the result is equal to or less than the number of "
                                          "Robots you control, create a 1/1 white Clown Robot "
                                          "artifact creature token.")
        self.assertFalse(ignored)
        self.faces(2)                    # two Robots needed for a 2; there are none
        self.g.resolve(self.a, effects[0], None, StackItem(self.a, [], []))
        self.g.settle()
        self.assertEqual([x for x in self.a.battlefield if "Robot" in x.card.subtypes], [])
        self.g.enter_battlefield(self.a, robot)
        self.faces(1)
        self.g.resolve(self.a, effects[0], None, StackItem(self.a, [], []))
        self.g.settle()
        self.assertEqual(len([x for x in self.a.battlefield if "Robot" in x.card.subtypes]), 2)

    def test_repeat_total_sacrifices(self):
        chicken = self.g.enter_battlefield(self.a, CHICKEN)
        effects = [e for e in CHICKEN.activated[0].effects if e.kind == "die_check"]
        effects = effects[1:]          # the repeat-total check, not the doubles one
        history = self.g.__dict__.setdefault("_die_totals", {})
        history[(self.g.turn, self.a)] = [7, 9, 9]      # 9 rolled before, 9 again just now
        self.faces(3, 6)
        self.g.resolve(self.a, effects[0], chicken, StackItem(self.a, [], [], source=chicken))
        self.g.settle()
        self.assertNotIn(chicken, self.a.battlefield)       # 9 was rolled before

        chicken2 = self.g.enter_battlefield(self.a, CHICKEN)
        history[(self.g.turn, self.a)] = [7, 8]         # 8 is new
        self.faces(3, 5)
        self.g.resolve(self.a, effects[0], chicken2, StackItem(self.a, [], [], source=chicken2))
        self.g.settle()
        self.assertIn(chicken2, self.a.battlefield)         # 8 is new

    def test_party_die_scales_with_party(self):
        cleric = card("Cleric Pal", "{1}{W}", "Creature — Human Cleric", "", 1, 1)
        rogue = card("Rogue Pal", "{1}{B}", "Creature — Human Rogue", "", 1, 1)
        self.g.enter_battlefield(self.a, cleric)
        self.g.enter_battlefield(self.a, rogue)
        self.apply("Roll the party die.")
        self.assertTrue(1 <= self.rolled() <= 8)            # a party of two rolls a d8

    def test_two_target_result_counters(self):
        bear = self.g.enter_battlefield(self.a, BEAR)
        bear2 = self.g.enter_battlefield(self.a, BEAR)
        self.faces(3)
        effects, ignored = _parse_effects("When you do, put X +1/+1 counters on each of up to "
                                         "two target creatures, where X is the result.")
        self.assertFalse(ignored)
        self.assertEqual(_kinds(effects), ["die_amount", "die_amount"])
        item = StackItem(self.a, effects, [bear, bear2])
        for eff, tgt in zip(effects, item.targets):
            self.g.resolve(self.a, eff, tgt, item)
        self.assertEqual((bear.power, bear.toughness), (5, 5))
        self.assertEqual((bear2.power, bear2.toughness), (5, 5))

    def test_clown_car_etb(self):
        perm = self.g.enter_battlefield(self.a, CLOWN_CAR, x=4)
        self.g.settle()
        faces = self.g.__dict__["_die_faces"][self.a]
        self.assertEqual(len(faces), 4)
        robots = [x for x in self.a.battlefield if "Robot" in x.card.subtypes]
        self.assertEqual(len(robots), sum(1 for f in faces if f % 2 == 1))
        self.assertEqual(perm.counters.get("+1/+1", 0), sum(1 for f in faces if f % 2 == 0))
