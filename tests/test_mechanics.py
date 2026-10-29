"""Sagas, planeswalkers, tokens, modal spells, alternative costs and other mechanics the
gauntlet decks use. Card text is written out here so the tests don't depend on a card cache."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player

DB = CardDB(offline=True)

CARDS = {c["name"].split(" // ")[0]: card_from_scryfall(c) for c in [
    {"name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "mana_cost": "{2}{R}", "cmc": 3,
     "type_line": "Enchantment — Saga // Enchantment Creature — Goblin Shaman", "card_faces": [
         {"name": "Fable of the Mirror-Breaker", "mana_cost": "{2}{R}", "type_line": "Enchantment — Saga",
          "oracle_text": "(As this Saga enters and after your draw step, add a lore counter.)\nI — Create a 2/2 red "
                         "Goblin Shaman creature token with \"Whenever this token attacks, create a Treasure "
                         "token.\"\nII — You may discard up two cards. If you do, draw that many cards.\nIII — "
                         "Exile this Saga, then return it to the battlefield transformed under your control."},
         {"name": "Reflection of Kiki-Jiki", "mana_cost": "", "type_line": "Enchantment Creature — Goblin Shaman",
          "power": "2", "toughness": "2", "oracle_text": ""}]},
    {"name": "The Wandering Emperor", "mana_cost": "{2}{W}{W}", "cmc": 4, "type_line": "Legendary Planeswalker",
     "loyalty": "3", "oracle_text": "Flash\nAs long as The Wandering Emperor entered this turn, you may activate "
     "her loyalty abilities any time you could cast an instant.\n[+1]: Put a +1/+1 counter on up to one target "
     "creature. It gains first strike until end of turn.\n[−1]: Create a 2/2 white Samurai creature token with "
     "vigilance.\n[−2]: Exile target tapped creature. You gain 2 life."},
    {"name": "Sheoldred, the Apocalypse", "mana_cost": "{2}{B}{B}", "cmc": 4,
     "type_line": "Legendary Creature — Phyrexian Praetor", "power": "4", "toughness": "5",
     "oracle_text": "Deathtouch\nWhenever you draw a card, you gain 2 life.\nWhenever an opponent draws a card, "
                    "they lose 2 life."},
    {"name": "Kolaghan's Command", "mana_cost": "{1}{B}{R}", "cmc": 3, "type_line": "Instant",
     "oracle_text": "Choose two —\n• Return target creature card from your graveyard to your hand.\n• Target "
                    "player discards a card.\n• Destroy target artifact.\n• Kolaghan's Command deals 2 damage "
                    "to any target."},
    {"name": "Bonecrusher Giant // Stomp", "mana_cost": "{2}{R}", "cmc": 3, "type_line": "Creature // Instant",
     "card_faces": [
         {"name": "Bonecrusher Giant", "mana_cost": "{2}{R}", "type_line": "Creature — Giant", "power": "4",
          "toughness": "3", "oracle_text": "Whenever Bonecrusher Giant becomes the target of a spell, Bonecrusher "
                                           "Giant deals 2 damage to that spell's controller."},
         {"name": "Stomp", "mana_cost": "{1}{R}", "type_line": "Instant — Adventure",
          "oracle_text": "Damage can't be prevented this turn. Stomp deals 2 damage to any target."}]},
    {"name": "Thoughtseize", "mana_cost": "{B}", "cmc": 1, "type_line": "Sorcery",
     "oracle_text": "Target player reveals their hand. You choose a nonland card from it. That player discards "
                    "that card. You lose 2 life."},
    {"name": "Fatal Push", "mana_cost": "{B}", "cmc": 1, "type_line": "Instant",
     "oracle_text": "Destroy target creature if it has mana value 2 or less.\nRevolt — Destroy that creature if "
                    "it has mana value 4 or less instead if a permanent you controlled left the battlefield this "
                    "turn."},
    {"name": "Wedding Announcement // Wedding Festivity", "mana_cost": "{2}{W}", "cmc": 3,
     "type_line": "Enchantment // Enchantment", "card_faces": [
         {"name": "Wedding Announcement", "mana_cost": "{2}{W}", "type_line": "Enchantment",
          "oracle_text": "At the beginning of your end step, put an invitation counter on Wedding Announcement. "
                         "If you attacked with two or more creatures this turn, draw a card. Otherwise, create a "
                         "1/1 white Human creature token. Then if Wedding Announcement has three or more "
                         "invitation counters on it, transform it."},
         {"name": "Wedding Festivity", "mana_cost": "", "type_line": "Enchantment",
          "oracle_text": "Creatures you control get +1/+1."}]},
    {"name": "Den of the Bugbear", "mana_cost": "", "cmc": 0, "type_line": "Land",
     "oracle_text": "If you control two or more other lands, Den of the Bugbear enters tapped.\n{T}: Add {R}.\n"
                    "{3}{R}: Until end of turn, Den of the Bugbear becomes a 3/2 red Goblin creature with "
                    "\"Whenever this creature attacks, create a 1/1 red Goblin creature token that's tapped and "
                    "attacking.\" It's still a land."},
    {"name": "Eidolon of the Great Revel", "mana_cost": "{R}{R}", "cmc": 2,
     "type_line": "Enchantment Creature — Spirit", "power": "2", "toughness": "2",
     "oracle_text": "Whenever a player casts a spell with mana value 3 or less, Eidolon of the Great Revel deals "
                    "2 damage to that player."},
    {"name": "Tenacious Underdog", "mana_cost": "{1}{B}", "cmc": 2, "type_line": "Creature — Human Warrior",
     "power": "3", "toughness": "2",
     "oracle_text": "Blitz—{2}{B}{B}, Pay 2 life. (If you cast this spell for its blitz cost, it gains haste and "
                    "\"When this creature dies, draw a card.\" Sacrifice it at the beginning of the next end "
                    "step.)\nYou may cast Tenacious Underdog from your graveyard using its blitz ability."},
    {"name": "Esika's Chariot", "mana_cost": "{3}{G}", "cmc": 4, "type_line": "Legendary Artifact — Vehicle",
     "power": "4", "toughness": "4",
     "oracle_text": "When Esika's Chariot enters, create two 2/2 green Cat creature tokens.\nWhenever Esika's "
                    "Chariot attacks, create a token that's a copy of target token you control.\nCrew 4"},
]}


def perm(card, owner, sick=False):
    p = Permanent(CARDS.get(card) or DB.get(card), owner)
    p.sick = sick
    p.tapped = False
    owner.battlefield.append(p)
    return p


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn = 1
        for p in (self.a, self.b):
            p.library = [DB.get("Island")] * 20

    def lands(self, p, name, n):
        return [perm(name, p) for _ in range(n)]

    def test_thirst_for_discovery_discards_one_basic_land_instead_of_two(self):
        thirst = card_from_scryfall({"name": "Thirst for Discovery", "mana_cost": "{2}{U}", "cmc": 3,
                                     "type_line": "Instant", "oracle_text": "Draw three cards. Then discard two "
                                     "cards unless you discard a basic land card."})
        self.assertEqual(thirst.unsupported, [])
        for hand, discarded in (([DB.get("Island"), DB.get("Lightning Bolt")], 1),
                                ([DB.get("Lightning Bolt"), DB.get("Counterspell")], 2)):
            with self.subTest(hand=hand):
                self.a.hand, self.a.graveyard = list(hand), []
                self.a.library = [DB.get("Lightning Bolt")] * 20
                self.lands(self.a, "Island", 3)
                self.a.hand.append(thirst)
                self.game.cast(self.a, thirst)
                self.game.settle()
                self.assertEqual(len(self.a.graveyard) - 1, discarded)   # minus Thirst itself
                if discarded == 1:
                    self.assertIn(DB.get("Island"), self.a.graveyard)

    def test_saga_chapters_and_transform(self):
        self.lands(self.a, "Mountain", 3)
        fable = CARDS["Fable of the Mirror-Breaker"]
        self.a.hand = [fable]
        self.game.cast(self.a, fable)
        self.assertEqual([c.card.name for c in self.a.creatures], ["Goblin Shaman token"])
        saga = next(x for x in self.a.battlefield if x.card.is_saga)
        self.game.add_lore(saga)
        self.game.settle()
        self.game.add_lore(saga)
        self.game.settle()
        self.assertEqual(saga.card.name, "Reflection of Kiki-Jiki")
        self.assertTrue(saga.is_creature)

    def test_token_attack_trigger_makes_treasure_that_pays(self):
        self.lands(self.a, "Mountain", 3)
        self.a.hand = [CARDS["Fable of the Mirror-Breaker"]]
        self.game.cast(self.a, CARDS["Fable of the Mirror-Breaker"])
        goblin = self.a.creatures[0]
        goblin.sick = False
        self.a.ai.choose_attackers = lambda g, me, opp: [goblin]
        self.game.combat(self.a, self.b)
        treasure = [x for x in self.a.battlefield if x.card.token_kind == "treasure"]
        self.assertEqual(len(treasure), 1)
        self.assertEqual(self.b.life, 18)
        self.a.hand = [DB.get("Shock")]
        self.game.cast(self.a, DB.get("Shock"), [self.b])
        self.assertNotIn(treasure[0], self.a.battlefield)

    def test_wandering_emperor_flash_exiles_attacker(self):
        self.lands(self.b, "Plains", 4)
        self.b.hand = [CARDS["The Wandering Emperor"]]
        maw = perm("Colossal Dreadmaw", self.a)
        self.a.ai.choose_attackers = lambda g, me, opp: [maw]
        self.game.combat(self.a, self.b)
        self.assertNotIn(maw, self.a.battlefield)
        emperor = self.b.planeswalkers[0]
        self.assertEqual(emperor.loyalty, 1)
        self.assertEqual(self.b.life, 22)

    def test_attacking_and_burning_planeswalkers(self):
        emperor = perm("The Wandering Emperor", self.b)
        emperor.counters["loyalty"] = 3
        bears = perm("Grizzly Bears", self.a)
        self.a.ai.choose_attackers = lambda g, me, opp: [bears]
        self.game.combat(self.a, self.b)
        self.assertEqual(emperor.loyalty, 1)
        self.assertEqual(self.b.life, 20)
        self.lands(self.a, "Mountain", 1)
        self.a.hand = [DB.get("Shock")]
        self.game.cast(self.a, DB.get("Shock"), [emperor])
        self.assertNotIn(emperor, self.b.battlefield)

    def test_sheoldred_draw_triggers(self):
        perm("Sheoldred, the Apocalypse", self.a)
        self.game.draw(self.b)
        self.game.draw(self.a)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (22, 18))

    def test_kolaghans_command_picks_two_modes(self):
        self.lands(self.a, "Swamp", 1)
        self.lands(self.a, "Mountain", 2)
        bears = perm("Grizzly Bears", self.b)
        self.b.hand = [DB.get("Island"), DB.get("Murder")]
        self.a.hand = [CARDS["Kolaghan's Command"]]
        self.game.cast(self.a, CARDS["Kolaghan's Command"])
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(len(self.b.hand), 1)

    def test_adventure_then_creature_from_exile(self):
        self.lands(self.a, "Mountain", 5)
        giant = CARDS["Bonecrusher Giant"]
        self.a.hand = [giant]
        stomp = next(c for c in self.game.spell_options(self.a) if c.name == "Stomp")
        self.game.cast(self.a, stomp, [self.b])
        self.assertEqual(self.b.life, 18)
        self.assertEqual(self.a.on_adventure, [giant])
        again = next(c for c in self.game.spell_options(self.a) if c.name.startswith("Bonecrusher"))
        self.assertTrue(self.game.can_cast_now(self.a, again))
        self.game.cast(self.a, again)
        self.assertEqual([c.card.name for c in self.a.creatures], ["Bonecrusher Giant"])

    def test_bonecrusher_punishes_targeting(self):
        giant = perm("Bonecrusher Giant", self.b)
        self.lands(self.a, "Swamp", 3)
        self.a.hand = [DB.get("Murder")]
        self.game.cast(self.a, DB.get("Murder"), [giant])
        self.assertEqual(self.a.life, 18)

    def test_flashback_and_foretell(self):
        self.lands(self.a, "Island", 7)
        deluge = DB.get("Memory Deluge")
        self.a.graveyard = [deluge]
        fb = next(c for c in self.game.spell_options(self.a) if "flashback" in c.name)
        self.a.library = [DB.get("Island")] * 10
        self.game.cast(self.a, fb)
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.library), 8)   # looked at seven
        self.assertIn(deluge, self.a.exile)
        for land in self.a.battlefield:
            land.tapped = False
        saw = DB.get("Saw It Coming")
        self.a.hand = [saw]
        self.assertTrue(self.game.foretell(self.a, saw))
        self.assertEqual(self.a.foretold, [saw])
        opt = next(c for c in self.game.spell_options(self.a) if "foretold" in c.name)
        self.assertEqual(self.game.cost_of(self.a, opt), {"generic": 1, "U": 1})

    def test_thoughtseize_and_fatal_push(self):
        self.lands(self.a, "Swamp", 2)
        self.b.hand = [DB.get("Island"), DB.get("Colossal Dreadmaw"), DB.get("Shock")]
        self.a.hand = [CARDS["Thoughtseize"]]
        self.game.cast(self.a, CARDS["Thoughtseize"], [self.b])
        self.assertNotIn(DB.get("Colossal Dreadmaw"), self.b.hand)
        self.assertEqual(self.a.life, 18)
        tusker = perm("Kalonian Tusker", self.b)
        maw = perm("Colossal Dreadmaw", self.b)
        push = CARDS["Fatal Push"]
        self.assertEqual(self.game.legal_targets(self.a, push.spell_effects[0]), [tusker, maw])
        self.a.hand = [push]
        self.game.cast(self.a, push, [maw])
        self.assertIn(maw, self.b.battlefield)    # legal target, but the mana-value condition prevents destruction

    def test_wedding_announcement_and_anthem(self):
        wa = perm("Wedding Announcement", self.a)
        for _ in range(3):
            self.game.fire(self.a, "end_step")
            self.game.settle()
        self.assertEqual(wa.card.name, "Wedding Festivity")
        humans = [c for c in self.a.creatures if c.card.name == "Human token"]
        self.assertEqual(len(humans), 3)
        self.assertEqual((humans[0].power, humans[0].toughness), (2, 2))

    def test_manland_attacks_and_makes_attacking_token(self):
        den = perm("Den of the Bugbear", self.a)
        self.lands(self.a, "Mountain", 4)
        self.assertTrue(self.game.activate(self.a, den, "animate"))
        self.assertTrue(den.is_creature)
        self.a.ai.choose_attackers = lambda g, me, opp: [den]
        self.a.ai.choose_blocks = lambda *a: {}
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 16)   # 3 from Den, 1 from the attacking Goblin

    def test_eidolon_and_blitz_from_graveyard(self):
        perm("Eidolon of the Great Revel", self.b)
        self.lands(self.a, "Swamp", 4)
        dog = CARDS["Tenacious Underdog"]
        self.a.graveyard = [dog]
        blitz = next(c for c in self.game.spell_options(self.a) if "blitz" in c.name)
        self.game.cast(self.a, blitz)
        self.assertEqual(self.a.life, 16)   # 2 life for blitz, 2 from Eidolon (mana value 2)
        underdog = self.a.creatures[0]
        self.assertTrue(underdog.has("haste"))
        self.game.dies(underdog)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)  # blitz: draw when it dies

    def test_vehicle_crew_and_cat_tokens(self):
        self.lands(self.a, "Forest", 4)
        chariot = CARDS["Esika's Chariot"]
        self.a.hand = [chariot]
        self.game.cast(self.a, chariot)
        self.assertEqual(len(self.a.creatures), 2)
        for x in self.a.battlefield:
            x.sick = False
        vehicle = next(x for x in self.a.battlefield if x.card.crew)
        self.assertTrue(self.game.activate(self.a, vehicle, "crew"))
        self.assertTrue(vehicle.is_creature)
        self.a.ai.choose_attackers = lambda g, me, opp: [vehicle]
        self.game.combat(self.a, self.b)
        self.assertEqual(len([c for c in self.a.battlefield if c.card.name == "Cat token"]), 3)

    def test_full_games_with_new_cards(self):
        names = ["Fable of the Mirror-Breaker", "Sheoldred, the Apocalypse", "Kolaghan's Command",
                 "Bonecrusher Giant", "Thoughtseize", "Fatal Push", "Tenacious Underdog", "Den of the Bugbear"]
        deck = [CARDS[n] for n in names for _ in range(4)] + [DB.get("Swamp")] * 12 + [DB.get("Mountain")] * 12
        wa = ["The Wandering Emperor", "Wedding Announcement", "Esika's Chariot", "Eidolon of the Great Revel"]
        deck2 = [CARDS[n] for n in wa for _ in range(6)] + [DB.get("Plains")] * 12 + \
            [DB.get("Forest")] * 12 + [DB.get("Mountain")] * 12
        for seed in range(6):
            Game(Player("x", deck, HeuristicAI()), Player("y", deck2, HeuristicAI()), random.Random(seed)).play()


if __name__ == "__main__":
    unittest.main()
