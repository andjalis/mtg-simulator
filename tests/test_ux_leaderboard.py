"""Leaderboard navigation descriptions must identify the saved deck."""
import unittest
from html.parser import HTMLParser
from web import leaderboard


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))


class LeaderboardUXTests(unittest.TestCase):
    def test_saved_result_links_identify_the_deck_and_escape_its_name(self):
        rows = [dict(deck="A's <deck>", mmr=1200, rank='Gold', rank_color='#aaa',
                     tested=0, games=2, link='/leaderboard/history/1', source='history',
                     grades=None, replay=True, place=1)]
        page = leaderboard.render_page(rows, now=0)
        links = Links(page).links
        self.assertIn({'class': 'play', 'href': '/leaderboard/history/1?replay=1',
                       'aria-label': "Replay the climb for A's <deck>",
                       'title': 'Replay the climb'}, links)
        self.assertTrue(any(a.get('aria-label') == "Results for A's <deck>" for a in links))
        self.assertIn('latest rated run', page)
        self.assertIn('not Arena rankings', page)
