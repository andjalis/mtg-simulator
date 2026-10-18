"""Saved replay prefixes must remain valid match records."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js needed to exercise browser JavaScript")
class ArenaReplayTests(unittest.TestCase):
    def test_replay_prefix_counts_and_scores_are_valid(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = {document: {}, matchMedia: () => ({matches: true})};
vm.createContext(context);
vm.runInContext(fs.readFileSync('web/static/arena.js', 'utf8'), context);
for (let games = 1; games <= 12; games++) {
  for (let wins = 0; wins <= games; wins++) {
    for (let draws = 0; draws <= games - wins; draws++) {
      const opponent = {name:'mixed', pool:'bronze', games, wins, draws,
        win_rate:(wins + .5 * draws) / games};
      const data = {history:[[0,1000],[games,1010]],
        ranks:[{name:'Bronze', floor:0, color:'red'}],
        pools:[{key:'bronze', done:true}], opponents:[opponent], status:'done'};
      for (const per of [2, 5]) {
        let previous = {games:0, wins:0, draws:0};
        for (const step of context.replaySteps(data, per)) {
          const o = step.opponents[0];
          assert(o.games > 0);
          assert(o.wins >= previous.wins && o.draws >= previous.draws);
          assert(o.wins + o.draws <= o.games);
          assert(Number.isFinite(o.win_rate) && o.win_rate >= 0 && o.win_rate <= 1);
          assert(o.games - o.wins - o.draws >= previous.games - previous.wins - previous.draws);
          previous = o;
        }
        assert.deepStrictEqual(previous, opponent);
      }
    }
  }
}
'''
        result = subprocess.run([shutil.which("node"), "-e", script],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
