"""Regression checks for saved leaderboard report edge cases."""
import json
import tempfile
import unittest
from pathlib import Path

from mtgsim import history
from web import leaderboard


class SavedReportQATests(unittest.TestCase):
    def test_non_object_json_does_not_hide_valid_decks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'ladder').mkdir()
            (root / 'assess').mkdir()
            for folder in ('ladder', 'assess'):
                (root / folder / 'bad.json').write_text(json.dumps(['mmr', 'rank', 'criteria']))
            (root / 'ladder' / 'good.json').write_text(json.dumps(
                {'deck': 'Good', 'mmr': 1200, 'rank': 'Gold'}))
            self.assertEqual([r['deck'] for r in leaderboard.from_files(root)], ['Good'])

    def test_invalid_assessment_structure_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'assess').mkdir()
            for name, criteria in [('null', None), ('list', []), ('child', {'meta': None})]:
                (root / 'assess' / (name + '.json')).write_text(json.dumps({'criteria': criteria}))
            self.assertEqual(leaderboard.from_files(root), [])

    def test_rated_history_without_rank_renders_podium(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / 'history.sqlite3'
            for index in range(3):
                history.record(f'Deck {index}', {'Mountain': 60}, 'rank', {},
                               mmr=1200 + index, path=store)
            rows = leaderboard.collect(Path(tmp), history_path=store)
            self.assertEqual(len(rows), 3)
            self.assertIn('Unrated', leaderboard.render_page(rows))

    def test_assessment_score_is_html_escaped(self):
        payload = '<img src=x onerror=alert(1)>'
        page = leaderboard.render_assessment({'deck': 'Saved', 'criteria': {
            'meta': {'grade': 'A', 'score': payload, 'summary': 'ok'}}})
        self.assertNotIn(payload, page)
        self.assertIn('&lt;img', page)
