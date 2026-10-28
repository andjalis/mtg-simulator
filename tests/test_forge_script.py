import random
import unittest
from pathlib import Path

from mtgsim import forge_script as fs
from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect, Trigger
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, card

CARDS = Path(__file__).parent / "fixtures" / "forge_scripts" / "cards"


def script(name):
    return (CARDS / f"{name}.txt").read_text(encoding="utf-8")


def abilities(name):
    return [ab for face in fs.parse_script(script(name)) for ab in face.abilities]


def inline(*lines):
    """The abilities of a minimal hand-written script (not a Forge copy) for one translation rule."""
    return [ab for face in fs.parse_script("Name:Test\n" + "\n".join(lines)) for ab in face.abilities]


class ParseTest(unittest.TestCase):
    def test_parse_params(self):
        self.assertEqual(fs.parse_params("SP$ DealDamage | ValidTgts$ Any | NumDmg$ 3"),
                         {"SP": "DealDamage", "ValidTgts": "Any", "NumDmg": "3"})

    def test_chain_follows_subabilities(self):
        ab = abilities("acrobatic_leap")[0]
        self.assertEqual(ab.kind, "spell")
        self.assertEqual([s.api for s in ab.steps], ["Pump", "Untap"])

    def test_faces_triggers_and_keywords(self):
        faces = fs.parse_script(script("brazen_borrower_petty_theft"))
        self.assertEqual([f.name for f in faces], ["Brazen Borrower", "Petty Theft"])
        self.assertEqual([a.kind for a in faces[0].abilities], ["keyword", "keyword", "static"])
        sheoldred = abilities("sheoldred_the_apocalypse")
        self.assertEqual([a.kind for a in sheoldred], ["keyword", "trigger", "trigger"])
        self.assertEqual(sheoldred[1].steps[0].api, "GainLife")

    def test_charm_modes_and_saga_chapters(self):
        charm = abilities("three_steps_ahead")[1]
        self.assertEqual([[s.api for s in m] for m in charm.modes], [["Counter"], ["CopyPermanent"], ["Draw", "Discard"]])
        chapters = [a for a in abilities("fable_of_the_mirror_breaker_reflection_of_kiki_jiki") if a.kind == "chapter"]
        self.assertEqual(len(chapters), 3)

    def test_script_index(self):
        idx = fs.script_index(CARDS)
        self.assertIn("lightning bolt", idx)
        self.assertIn("sheoldred, the apocalypse", idx)


class TranslateTest(unittest.TestCase):
    def test_lightning_bolt(self):
        self.assertEqual(fs.translate(abilities("lightning_bolt")[0]), ("spell", [Effect("damage", 3, target="any")]))

    def test_destroy_filter_and_dig(self):
        self.assertEqual(fs.translate(abilities("go_for_the_throat")[0]),
                         ("spell", [Effect("destroy", target="creature", filter="nonartifact")]))
        self.assertEqual(fs.translate(abilities("stock_up")[0]), ("spell", [Effect("dig", 5, 2)]))
        self.assertEqual(fs.translate(abilities("pyroclasm")[0]),
                         ("spell", [Effect("damage", 2, target="each_creature")]))

    def test_triggers(self):
        kind, trig = fs.translate(abilities("sheoldred_the_apocalypse")[1])
        self.assertEqual((kind, trig), ("trigger", Trigger("you_draw", [Effect("gain_life", 2)])))
        kind, trig = fs.translate(abilities("sheoldred_the_apocalypse")[2])
        self.assertEqual(trig.event, "opp_draw")
        self.assertEqual(trig.effects, [Effect("lose_life", 2, target="that_player")])

    def test_lands(self):
        kinds = [fs.translate(a)[0] for a in abilities("blossoming_sands")]
        self.assertEqual(kinds, ["enters_tapped", "trigger", "mana"])

    def test_keywords(self):
        self.assertEqual(fs.translate(abilities("sheoldred_the_apocalypse")[0]), ("keyword", "deathtouch"))

    def test_untranslatable_reasons(self):
        with self.assertRaisesRegex(fs.Untranslatable, "API Untap"):
            fs.translate(abilities("acrobatic_leap")[0])
        with self.assertRaisesRegex(fs.Untranslatable, "ChangeZoneAll: parameter RememberChanged"):
            fs.translate(abilities("sunfall")[0])     # "exiled this way" needs remembered cards
        with self.assertRaisesRegex(fs.Untranslatable, "static CantBlockBy"):
            fs.translate(abilities("brazen_borrower_petty_theft")[2])
        with self.assertRaisesRegex(fs.Untranslatable, "ModeCost"):     # spree mode costs
            fs.translate(abilities("three_steps_ahead")[1])

    def test_loyalty_ability(self):
        kaito = [a for a in abilities("kaito_bane_of_nightmares") if a.kind == "loyalty"]
        self.assertEqual(len(kaito), 3)
        self.assertEqual(fs.translate(kaito[2]),
                         ("loyalty", (-2, [Effect("tap", 1, target="creature"), Effect("stun", 2, target="prev")])))
        with self.assertRaisesRegex(fs.Untranslatable, "variable amount"):
            fs.translate(kaito[1])      # draw a card for each opponent who lost life


class SemanticLossTest(unittest.TestCase):
    """The translation refuses a step rather than playing it as something else."""

    def test_single_exile_is_refused_not_destroy(self):
        for tgt in ("Creature", "Creature.OppCtrl", "Creature,Planeswalker", "Artifact"):
            ab = inline(f"A:SP$ ChangeZone | Origin$ Battlefield | Destination$ Exile | ValidTgts$ {tgt}")[0]
            with self.assertRaisesRegex(fs.Untranslatable, "Battlefield to Exile"):
                fs.translate(ab)

    def test_mass_exile_is_exile_not_wrath(self):
        ab = inline("A:SP$ ChangeZoneAll | ChangeType$ Creature | Origin$ Battlefield | Destination$ Exile")[0]
        self.assertEqual(fs.translate(ab), ("spell", [Effect("exile_all_creatures")]))
        ab = inline("A:SP$ DestroyAll | ValidCards$ Creature")[0]
        self.assertEqual(fs.translate(ab), ("spell", [Effect("wrath", target="each_creature")]))

    def test_exile_and_destroy_differ_in_play(self):
        # Indestructible and dies triggers: wrath leaves the god and fires the trigger, exile does neither.
        god = card("Test God", "{2}{W}", "Creature — God", "Indestructible", 4, 4)
        mourner = card("Test Mourner", "{1}{B}", "Creature — Human", "When this creature dies, you draw a card.", 1, 1)
        for effect, god_stays, drew in ((Effect("wrath", target="each_creature"), True, 1),
                                        (Effect("exile_all_creatures"), False, 0)):
            a, b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
            game = Game(a, b, random.Random(0))
            game.turn, game.step = 1, "main1"
            a.library = [BEAR] * 5
            g, m = game.enter_battlefield(a, god), game.enter_battlefield(a, mourner)
            game.settle()
            hand = len(a.hand)
            game.resolve(a, effect, None)
            game.settle()
            self.assertEqual(g in a.battlefield, god_stays, effect.kind)
            self.assertNotIn(m, a.battlefield)
            self.assertEqual([c.name for c in a.graveyard].count("Test Mourner"), drew, effect.kind)
            self.assertEqual(len(a.hand) - hand, drew, effect.kind)

    def test_up_to_targets_are_refused(self):
        with self.assertRaisesRegex(fs.Untranslatable, "TargetMin=0"):
            fs.translate(inline("A:SP$ Destroy | ValidTgts$ Creature | TargetMin$ 0")[0])
        self.assertEqual(fs.translate(inline("A:SP$ Destroy | ValidTgts$ Creature | TargetMin$ 1")[0]),
                         ("spell", [Effect("destroy", target="creature")]))

    def test_timing_and_permission_restrictions_are_refused(self):
        for extra in ("SorcerySpeed$ True", "ActivationPhases$ Upkeep", "AnyPlayer$ True"):
            with self.assertRaisesRegex(fs.Untranslatable, "mana ability"):
                fs.translate(inline(f"A:AB$ Mana | Cost$ T | Produced$ G | {extra}")[0])
        self.assertEqual(fs.translate(inline("A:AB$ Mana | Cost$ T | Produced$ G")[0]), ("mana", "G"))

    def test_spell_additional_costs_are_refused(self):
        with self.assertRaisesRegex(fs.Untranslatable, "additional cost Sac<1/Creature>"):
            fs.translate(inline("A:SP$ Draw | Cost$ 1 B Sac<1/Creature> | NumCards$ 2")[0])
        self.assertEqual(fs.translate(inline("A:SP$ Draw | Cost$ 2 U/P | NumCards$ 2")[0]),
                         ("spell", [Effect("draw", 2)]))

    def test_controller_restrictions_are_kept(self):
        def spell(line):
            return fs.translate(inline(line)[0])[1]
        self.assertEqual(spell("A:SP$ Destroy | ValidTgts$ Creature.OppCtrl"),
                         [Effect("destroy", target="creature", filter="opp")])
        self.assertEqual(spell("A:SP$ DealDamage | ValidTgts$ Creature,Planeswalker | NumDmg$ 3"),
                         [Effect("damage", 3, target="creature_pw")])
        self.assertEqual(spell("A:SP$ DealDamage | ValidTgts$ Opponent | NumDmg$ 2"),
                         [Effect("damage", 2, target="player", filter="opp")])
        self.assertEqual(spell("A:SP$ ChangeZone | Origin$ Battlefield | Destination$ Hand | ValidTgts$ Creature"),
                         [Effect("bounce", target="creature")])
        self.assertEqual(spell("A:SP$ Tap | ValidTgts$ Permanent.nonLand+OppCtrl"),
                         [Effect("tap", 1, target="nonland_perm", filter="opp")])
        self.assertEqual(spell("A:SP$ Pump | ValidTgts$ Creature.YouCtrl | NumAtt$ +2 | KW$ Trample"),
                         [Effect("pump", 2, 0, target="creature_mine"), Effect("grant", target="prev",
                                                                               data={"keyword": "trample"})])
        with self.assertRaisesRegex(fs.Untranslatable, "target Player,Planeswalker"):
            spell("A:SP$ DealDamage | ValidTgts$ Player,Planeswalker | NumDmg$ 2")
        with self.assertRaisesRegex(fs.Untranslatable, "PutCounter: P1P1 on Creature"):
            spell("A:SP$ PutCounter | ValidTgts$ Creature | CounterType$ P1P1 | CounterNum$ 1")

    def test_controller_filter_limits_targets_in_play(self):
        a, b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0))
        mine, theirs = Permanent(BEAR, a), Permanent(BEAR, b)
        a.battlefield.append(mine)
        b.battlefield.append(theirs)
        eff = fs.translate(inline("A:SP$ Destroy | ValidTgts$ Creature.OppCtrl")[0])[1][0]
        self.assertEqual(game.legal_targets(a, eff), [theirs])


class MeasureTest(unittest.TestCase):
    def test_match_line(self):
        abs_ = abilities("acrobatic_leap")
        self.assertIs(fs.match_line("Untap it.", abs_, "Acrobatic Leap"), abs_[0])   # a sentence of the ability
        sunfall = abilities("sunfall")
        self.assertIs(fs.match_line("Exile all creatures.", sunfall, "Sunfall"), sunfall[0])
        self.assertIsNone(fs.match_line("X costs are paid as X=0", sunfall, "Sunfall"))

    def test_measure(self):
        scripts = fs.script_index(CARDS)
        partial = {"Sunfall": ["Exile all creatures.", "Incubate X, where X is the number of creatures exiled this way."],
                   "Stock Up": ["Look at the top five cards of your library.",
                                "Put two of them into your hand and the rest on the bottom of your library in any order."]}
        rep = fs.measure(partial, [], scripts)
        self.assertEqual((rep.cards, rep.lines), (2, 4))
        self.assertEqual(rep.cards_fixed, 1)             # Stock Up translates, Sunfall needs Incubate
        self.assertEqual(rep.missing_api["Incubate"], 1)
        self.assertIn("Stock Up", [e[0] for e in rep.examples])
        self.assertIn("Cards that would become fully supported: 1", fs.format_report(rep, 2))


if __name__ == "__main__":
    unittest.main()
