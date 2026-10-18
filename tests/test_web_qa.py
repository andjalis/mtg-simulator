"""Regression coverage for browser sessions and recoverable device result failures."""
import shutil
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from web import sim


class DeviceResultQATests(unittest.TestCase):
    def test_invalid_result_preserves_task_for_server_fallback(self):
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server)
            try:
                future = pool.submit(sim._play_chunk, {"Mountain": 60}, {"Mountain": 60}, 2, 1)
                tid = pool.take(1)[0]["id"]
                with self.assertRaises(ValueError):
                    pool.finish(tid, {})
                self.assertFalse(future.done())
                self.assertIn(tid, pool.tasks)
                pool.release()
                self.assertEqual(future.result(timeout=10)["games"], 2)
            finally:
                pool.close()

    def test_inconsistent_result_preserves_task(self):
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server)
            try:
                future = pool.submit(sim._play_chunk, {"Mountain": 60}, {"Mountain": 60}, 2, 1)
                tid = pool.take(1)[0]["id"]
                result = {"games": 2, "wins": 3, "losses": 0, "draws": 0,
                          "on_play_wins": 1, "on_play_games": 1, "turns": 10}
                with self.assertRaises(ValueError):
                    pool.finish(tid, result)
                self.assertFalse(future.done())
                self.assertIn(tid, pool.tasks)
            finally:
                pool.close()


class BrowserSessionQATests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js needed to exercise browser JavaScript")
    def test_successive_device_trials_refresh_card_data(self):
        root = Path(__file__).resolve().parents[1]
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync('web/static/index.html', 'utf8');
const fn = html.slice(html.indexOf('async function runOnDevice(id)'), html.indexOf('\ntry { $("#deck")'));
const requests = [], messages = [];
const ctx = {
  device: {cards: [{name: 'Previous deck card'}], results: [], failed: null},
  alive: () => [{busy: 0, postMessage: m => messages.push(m)}],
  sleep: async () => {},
  api: async (path, body) => {
    requests.push(body);
    return {active: false, tasks: [], cards: [{name: path}]};
  }
};
vm.createContext(ctx); vm.runInContext(fn,ctx);
(async () => {
  await ctx.runOnDevice('first'); await ctx.runOnDevice('second');
  assert(requests.every(r => r.cards === true), 'each trial needs its own card data');
  assert(requests.every(r => r.want === 0), 'wait for card data before claiming tasks');
  assert.equal(messages.length, 2);
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run([shutil.which("node"), "-e", script], cwd=root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
