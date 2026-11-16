"""#793: in an Equipment's / Aura's "Whenever equipped / enchanted creature ..." trigger, "~" ("this Equipment") is the
attachment itself and "equipped / enchanted creature" / "it" is the host (parse.py splits them; Game.fire runs the
trigger with the attachment as source and the host as context)."""
import unittest

from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
WURM = card("Test Wurm", "{4}{G}{G}", "Creature — Wurm", "", 6, 4)
HOST_PUMP = card("Test Spurs", "{1}", "Artifact — Equipment", "Whenever equipped creature attacks, it gets +2/+0 until "
                 "end of turn.\nEquip {1}")


class Base793(Base):
    def equip(self, name_or_card, lands, host=None):
        from mtgsim.carddb import CardDB
        self.game.turn, self.game.step = 1, "main1"
        c = CardDB(offline=True).get(name_or_card) if isinstance(name_or_card, str) else name_or_card
        host = host or self.perm(BEAR, self.a)
        eq = self.perm(c, self.a)
        self.a.battlefield += [Permanent(x, self.a) for x in lands]
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.game.settle()
        host.sick = False
        return host, eq

    def attack(self, who):
        self.a.ai.choose_attackers = lambda g_, p, o: list(who)
        self.b.ai.choose_blocks = lambda *args: {}
        self.game.combat(self.a, self.b)
        self.game.settle()


class HostStillMeansTheCreature(Base793):
    def test_it_is_the_equipped_creature(self):
        self.assertFalse(HOST_PUMP.host_triggers[0].data.get("attachment_source"))
        bear, _ = self.equip(HOST_PUMP, [FOREST])
        self.attack([bear])
        self.assertEqual(self.b.life, 16)                 # 2 + 2


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base793):
    def test_worldslayer_keeps_itself(self):
        """"Whenever equipped creature deals combat damage to a player, destroy all permanents other than this
        Equipment": everything else goes, the equipped creature included."""
        bear, ws = self.equip("Worldslayer", [FOREST] * 5)
        theirs = self.perm(WURM, self.b)
        self.attack([bear])
        self.assertEqual([x.card.name for pl in self.game.players for x in pl.battlefield], ["Worldslayer"])
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertNotIn(bear, self.a.battlefield)

    def test_bloodforged_battle_axe_copies_itself(self):
        bear, axe = self.equip("Bloodforged Battle-Axe", [FOREST] * 2)
        self.attack([bear])
        copies = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(copies), 1)
        self.assertIn("Equipment", copies[0].card.subtypes)

    def test_sleep_magic_leaves_when_its_host_is_dealt_damage(self):
        """"When enchanted creature is dealt damage, sacrifice Sleep Magic": the Aura goes, the creature stays."""
        from mtgsim.carddb import CardDB
        self.game.turn, self.game.step = 1, "main1"
        wurm = self.perm(WURM, self.b)
        wurm.tapped = True
        self.a.battlefield.append(Permanent(ISLAND, self.a))
        magic = CardDB(offline=True).get("Sleep Magic")
        self.a.hand = [magic]
        self.assertTrue(self.game.cast(self.a, magic, [wurm]))
        self.game.settle()
        aura = next(x for x in self.a.battlefield if x.card.name == "Sleep Magic")
        shock = StackItem(self.a, list(SHOCK.spell_effects), [wurm], card=SHOCK, name="Shock")
        self.game.stack.append(shock)
        self.game.resolve_top()
        self.game.settle()
        self.assertNotIn(aura, self.a.battlefield)
        self.assertIn(wurm, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
