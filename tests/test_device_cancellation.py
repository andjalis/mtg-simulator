"""Early stopping must not leave browser futures invisible to as_completed."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from web import sim


class DeviceCancellationTests(unittest.TestCase):
    def test_reconnect_handoff_recovers_work_claimed_by_old_browser(self):
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server, stall=0.1)
            try:
                future = pool.submit(sim._play_chunk, {"Mountain": 60}, {"Mountain": 60}, 2, 1)
                self.assertEqual(len(pool.take(1)), 1)
                # A new page can keep polling without owning the old page's work.
                deadline = time.monotonic() + 0.25
                while time.monotonic() < deadline:
                    self.assertEqual(pool.take(0), [])
                    time.sleep(0.02)
                self.assertFalse(future.done())
                self.assertFalse(pool.on_server)
                pool.release()  # the reconnect handler must explicitly hand it off
                self.assertEqual(future.result(timeout=5)["games"], 2)
            finally:
                pool.close()

    def test_cancelled_browser_future_notifies_completion_waiters(self):
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server, stall=60)
            try:
                future = pool.submit(sim._play_chunk, {"Mountain": 60}, {"Mountain": 60}, 10, 1)
                self.assertTrue(future.cancel())
                self.assertTrue(future.cancel())  # repeated cancellation stays safe
                self.assertEqual(list(as_completed([future], timeout=0.2)), [future])
                self.assertEqual(pool.take(1), [])
            finally:
                pool.close()

    def test_browser_early_stop_finishes_without_playing_cancelled_batches(self):
        run = sim.make_run("cancel QA", "60 Mountain", ["bronze"], False, 100, seed=7, grade=False)
        run.chunk, run.record_history = 10, False
        errors = []
        def execute(pool):
            try:
                run.execute(pool)
            except Exception as error:
                errors.append(error)
        with ThreadPoolExecutor(1) as server:
            pool = sim.DevicePool(server, stall=60)
            worker = threading.Thread(target=execute, args=(pool,), daemon=True)
            try:
                worker.start()
                deadline = time.monotonic() + 5
                while worker.is_alive() and time.monotonic() < deadline:
                    for task in pool.take(1):
                        games = task["games"]
                        pool.finish(task["id"], {"games": games, "wins": games, "losses": 0,
                            "draws": 0, "on_play_wins": (games + 1) // 2,
                            "on_play_games": (games + 1) // 2, "turns": games * 4})
                    time.sleep(0.001)
                self.assertFalse(worker.is_alive(), "run hung waiting for cancelled browser batches")
                self.assertEqual(errors, [])
                self.assertEqual(run.done, run.total)
                self.assertEqual(run.done, 20 * len(run.tiers[0].decks()))
                self.assertEqual(run.tracker.to_dict()["status"], "done")
            finally:
                pool.close()
