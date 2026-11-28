"""Headless tests for the desktop operation boundary."""

import importlib
from pathlib import Path
from unittest.mock import Mock, patch
import threading
import time
import unittest


class WorkerTests(unittest.TestCase):
    def setUp(self):
        # Importing the module must work without a display or a configured toolkit.
        gui = importlib.import_module("open_fire_toolkit.gui")
        self.worker = gui.Worker()

    def wait_for_result(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            self.worker.drain()
            if not self.worker.busy:
                return
            time.sleep(0.001)
        self.fail("Background operation did not complete")

    def test_concurrent_submission_is_rejected_without_running_later(self):
        held = threading.Event()
        unexpected = threading.Event()
        finished = []
        self.assertTrue(self.worker.submit(lambda log: held.wait(2), finished.append, self.fail))
        try:
            self.assertFalse(
                self.worker.submit(lambda log: unexpected.set(), finished.append, self.fail)
            )
        finally:
            held.set()
        self.wait_for_result()
        self.assertEqual(finished, [True])
        self.assertFalse(unexpected.is_set())

    def test_logs_and_success_callbacks_only_run_on_caller_thread(self):
        caller = threading.get_ident()
        observed = []

        def action(log):
            log("read one")
            return threading.get_ident()

        self.assertTrue(self.worker.submit(
            action,
            lambda thread_id: observed.append(("result", thread_id, threading.get_ident())),
            self.fail,
            lambda line: observed.append(("log", line, threading.get_ident())),
        ))
        self.assertEqual(observed, [])
        self.wait_for_result()
        self.assertEqual(observed[0], ("log", "read one", caller))
        self.assertEqual(observed[1][0], "result")
        self.assertNotEqual(observed[1][1], caller)
        self.assertEqual(observed[1][2], caller)

    def test_failure_clears_busy_and_allows_retry(self):
        def action(log):
            raise ValueError("unplugged")

        errors, finished = [], []
        self.assertTrue(self.worker.submit(action, self.fail, errors.append))
        self.wait_for_result()
        self.assertEqual([str(error) for error in errors], ["unplugged"])
        self.assertTrue(self.worker.submit(lambda log: "retry", finished.append, self.fail))
        self.wait_for_result()
        self.assertEqual(finished, ["retry"])


class BundledSelectionTests(unittest.TestCase):
    def test_bundled_selection_clears_old_paths_before_loading_and_preserves_preview(self):
        from open_fire_toolkit.gui import App
        app = App.__new__(App)
        app.apk_paths = [Path("stale.apk")]
        app.using_bundle = False
        app.worker = Mock(busy=False)
        app.review = None
        app.apk_table = Mock()
        app.apk_table.get_children.return_value = []
        app._sync_controls = Mock()
        app._append_log = Mock()
        app._start = Mock()
        app._load_bundled_apks()
        self.assertEqual(app.apk_paths, [])
        _, load, complete = app._start.call_args.args
        paths = tuple(map(Path, ["one.apk", "two.apk", "three.apk", "four.apk"]))
        with patch("open_fire_toolkit.gui.bundled_apks", side_effect=ValueError("checksum")):
            with self.assertRaisesRegex(ValueError, "checksum"):
                load(None)
        self.assertFalse(app.using_bundle)
        self.assertFalse(app.apk_paths)
        with patch("open_fire_toolkit.gui.bundled_apks", return_value=paths):
            complete(load(None))
        self.assertTrue(app.using_bundle)
        self.assertEqual(tuple(app.apk_paths), paths)
        app._plan = Mock()
        toolkit = Mock()
        app._plan_play()
        app._plan.call_args.args[1](toolkit, "owner")
        toolkit.plan_bundled_google_play.assert_called_once_with("owner", paths)
        toolkit.execute.assert_not_called()
        app.files = Mock()
        app.files.askopenfilenames.return_value = ()
        app.root = Mock()
        app._choose_apks()
        self.assertTrue(app.using_bundle)
        app.files.askopenfilenames.return_value = ('adapter.apk',)
        app._choose_apks()
        self.assertEqual(app.apk_paths, [Path('adapter.apk')])
        self.assertFalse(app.using_bundle)


if __name__ == "__main__":
    unittest.main()
