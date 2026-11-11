"""A resolving group bonus affects its resolution-time set, until the source untaps."""
import random
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, card

WEAPONRY = card('Test Weaponry', '{4}', 'Artifact',
                'You may choose not to untap this artifact during your untap step.\n'
                '{2}, {T}: All creatures get +2/+2 for as long as this artifact remains tapped.')
DB_FILE = Path(__file__).resolve().parents[1] / 'mtgsim/data/cards.sqlite3'


class GroupDurations(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(2))
        self.g.turn, self.g.step = 2, 'main1'
        self.source = self.g.enter_battlefield(self.a, WEAPONRY)
        self.mine = self.g.enter_battlefield(self.a, BEAR)
        self.theirs = self.g.enter_battlefield(self.b, BEAR)

    def fire(self):
        effects = list(WEAPONRY.activated[0].effects)
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects), source=self.source, kind='ability'))
        self.g.resolve_top()

    def test_group_is_fixed_at_resolution_not_activation(self):
        self.assertEqual(WEAPONRY.unsupported, [])
        self.source.tapped = True
        late = self.g.enter_battlefield(self.a, BEAR)
        self.fire()
        newest = self.g.enter_battlefield(self.b, BEAR)
        self.assertEqual((self.mine.power, self.theirs.power, late.power, newest.power), (4, 4, 4, 2))
        self.g.turn += 2
        self.g.expire_continuous_effects()
        self.assertEqual(self.mine.power, 4)

    def test_untap_then_retap_without_query_never_restores_bonus(self):
        self.source.tapped = True
        self.fire()
        self.source.tapped = False
        self.source.tapped = True
        self.assertEqual((self.mine.power, self.theirs.power), (2, 2))
        self.fire()  # a new activation can create a new effect
        self.assertEqual(self.mine.power, 4)

    def test_ends_if_source_already_untapped_before_resolution(self):
        self.source.tapped = False
        self.fire()
        self.source.tapped = True
        self.assertEqual(self.mine.power, 2)

    def test_ends_if_source_left_before_resolution(self):
        self.source.tapped = True
        self.g.leave_battlefield(self.source, 'exile')
        self.fire()
        self.assertEqual(self.mine.power, 2)

    def test_source_departure_ends_bonus(self):
        self.source.tapped = True
        self.fire()
        self.g.destroy(self.source)
        self.assertEqual((self.mine.power, self.theirs.power), (2, 2))

    @unittest.skipUnless(DB_FILE.exists(), 'offline card database not built')
    def test_real_oracle(self):
        self.assertEqual(CardDB(offline=True).get('Thran Weaponry').unsupported, [])
