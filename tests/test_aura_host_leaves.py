"""#782: an Aura's / Equipment's "When enchanted / equipped creature dies / leaves the battlefield" event trigger looks
back in time (CR 603.10a): it triggers although the Aura is put into the graveyard right after its host left."""
import unittest

from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
VALOR = card("Test Valor", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.\nWhen "
             "enchanted creature leaves the battlefield, create a 1/1 white Spirit creature token with flying.")


class Enchanting:
    def enchant(self, aura, host, lands):
        self.game.turn, self.game.step = 1, "main1"
        self.a.battlefield += [Permanent(c, self.a) for c in lands]
        self.a.hand = [aura]
        self.assertTrue(self.game.cast(self.a, aura, [host]))
        self.game.settle()

    def tokens(self):
        return [x.card.name for x in self.a.battlefield if x.card.is_token]


class LooksBack(Enchanting, Base):
    def test_dies(self):
        bear = self.perm(BEAR, self.a)
        self.enchant(VALOR, bear, [PLAINS])
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.tokens()), 1)

    def test_bounced_host_counts_as_leaving(self):
        bear = self.perm(BEAR, self.a)
        self.enchant(VALOR, bear, [PLAINS])
        self.game.leave_battlefield(bear, "hand")
        self.game.settle()
        self.assertEqual(len(self.tokens()), 1)

    def test_only_its_own_host(self):
        """Another creature leaving doesn't trigger it, nor does its former host leaving later on."""
        bear, other = self.perm(BEAR, self.a), self.perm(BEAR, self.a)
        self.enchant(VALOR, bear, [PLAINS])
        self.game.destroy(other)
        self.game.settle()
        self.assertEqual(self.tokens(), [])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Enchanting, Base):
    def get(self, name):
        from mtgsim.carddb import CardDB
        return CardDB(offline=True).get(name)

    def test_kayas_ghostform_dies_and_exile(self):
        for how in ("dies", "exile"):
            self.setUp()
            bear = self.perm(BEAR, self.a)
            self.enchant(self.get("Kaya's Ghostform"), bear, [SWAMP])
            if how == "dies":
                self.game.destroy(bear)
            else:
                self.game.leave_battlefield(bear, "exile")
            self.game.settle()
            back = [x for x in self.a.battlefield if x.card.name == "Grizzly Bears"]
            self.assertEqual(len(back), 1, how)

    def test_funeral_march(self):
        """"When enchanted creature leaves the battlefield, its controller sacrifices a creature." """
        theirs, other = self.perm(BEAR, self.b), self.perm(card("Test Elk", "{3}", "Creature — Elk", "", 3, 3), self.b)
        march = self.perm(self.get("Funeral March"), self.a)    # attached directly: the host choice isn't tested here
        march.aura_host = theirs
        theirs.auras.append(march)
        self.game.destroy(theirs)
        self.game.settle()
        self.assertNotIn(other, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
