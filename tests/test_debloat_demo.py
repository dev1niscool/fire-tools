import unittest
from unittest.mock import patch

from open_fire_toolkit.demo import DemoToolkit
from open_fire_toolkit.feature_catalog import BY_KEY, run_feature
from open_fire_toolkit.service import ToolkitError


KINDLE = 'com.amazon.kindle'
SILK = 'com.amazon.cloud9'
CALENDAR = 'com.android.calendar'
SETUP = 'com.amazon.kindle.otter.oobe'


class DebloatDemoTests(unittest.TestCase):
    def setUp(self):
        self.demo = DemoToolkit()
        self.serial = self.demo.identity.serial

    def plan(self, **params):
        return run_feature(self.demo, self.serial, BY_KEY['debloat'], params)

    def apply(self, plan):
        return self.demo.execute(plan, confirmed=True, log=lambda _: None)

    def states(self, mode='all'):
        return {row['package']: row['state'] for row in self.demo.package_inventory(self.serial, mode)}

    def test_inventory_filters_follow_system_and_installed_user_apps(self):
        system, third_party = self.states('system'), self.states('third-party')
        self.assertIn(SILK, system)
        self.assertIn('com.android.vending', third_party)
        self.assertFalse(system.keys() & third_party.keys())
        self.assertEqual(system.keys() | third_party.keys(), self.states().keys())
        self.apply(self.demo.plan_package_action(self.serial, 'uninstall', (SILK,)))
        self.assertNotIn(SILK, self.states('system'))
        self.assertEqual(self.states('uninstalled')[SILK], 'uninstalled')
        self.apply(self.demo.plan_google_play(self.serial, ()))
        self.assertIn('com.google.android.gsf', self.states('third-party'))

    def test_review_and_apply_recommended_then_undo_only_its_changes(self):
        original = self.states()
        recommended = self.plan(profile='recommended')
        self.assertEqual(recommended.packages, self.plan(profile='standard').packages)
        self.assertIn(KINDLE, recommended.packages)
        self.assertNotIn(SILK, recommended.packages)
        self.assertTrue(any(KINDLE in row and 'Kindle' in row and 'enabled → disabled' in row
                            for row in recommended.details))
        with self.assertRaises(ToolkitError):
            self.demo.execute(recommended)
        self.assertEqual(self.states(), original)
        readback = self.apply(recommended)
        self.assertTrue(any(KINDLE in row and 'disabled' in row for row in readback))
        self.assertEqual(self.states()[KINDLE], 'disabled')
        self.assertEqual(self.states()[SILK], 'enabled')
        undo = self.demo.plan_package_action(self.serial, 'undo')
        self.assertEqual(set(undo.packages), set(recommended.packages))
        self.apply(undo)
        self.assertEqual(self.states(), original)
        with self.assertRaisesRegex(ToolkitError, 'undo'):
            self.demo.plan_package_action(self.serial, 'undo')

    def test_complete_and_restore_everything_include_different_apps_and_protect_setup(self):
        complete = self.plan(profile='complete')
        self.assertIn(SILK, complete.packages)
        self.assertNotIn(CALENDAR, complete.packages)  # Disabled before using the toolkit.
        self.assertNotIn(SETUP, complete.packages)
        self.assertTrue(any(SETUP in row and 'protected' in row.lower() for row in complete.details))
        self.apply(complete)
        disabled = self.states('disabled')
        restore = run_feature(self.demo, self.serial, BY_KEY['debloat-restore'], {})
        self.assertIn(KINDLE, restore.packages)
        self.assertIn(CALENDAR, restore.packages)
        self.assertNotIn(SETUP, restore.packages)
        self.assertTrue(any(CALENDAR in row and 'disabled → enabled' in row for row in restore.details))
        readback = self.apply(restore)
        self.assertTrue(any(CALENDAR in row and 'enabled' in row for row in readback))
        self.assertEqual(self.states()[CALENDAR], 'enabled')
        self.assertEqual(self.states()[SETUP], 'enabled')
        self.apply(self.demo.plan_package_action(self.serial, 'undo'))
        self.assertEqual(self.states('disabled'), disabled)

    def test_restore_everything_skips_owner_removals_and_undo_recovers_removed_apps(self):
        before = self.states()
        apps = self.demo.packages(self.serial)
        self.apply(self.plan(profile='complete', mode='uninstall'))
        self.assertIn(KINDLE, self.states('uninstalled'))
        self.assertNotIn(KINDLE, self.states())
        self.assertNotIn(KINDLE, self.demo.packages(self.serial))
        self.assertEqual(self.demo.packages(self.serial, disabled_only=True), [])
        with self.assertRaisesRegex(ToolkitError, 'No matching'):
            self.plan(profile='complete', mode='enable')
        self.apply(self.demo.plan_package_action(self.serial, 'undo'))
        self.assertEqual(self.states(), before)
        self.assertEqual(self.demo.packages(self.serial), apps)
        self.assertIn(CALENDAR, self.demo.packages(self.serial, disabled_only=True))

    def test_restore_everything_without_saved_batch_and_reject_stale_preview(self):
        restore = run_feature(self.demo, self.serial, BY_KEY['debloat-restore'], {})
        self.assertEqual(restore.packages, (CALENDAR,))
        self.apply(self.demo.plan_package_action(self.serial, 'disable', (KINDLE,)))
        with self.assertRaisesRegex(ToolkitError, '(?i)preview'):
            self.apply(restore)
        self.assertEqual(self.states()[CALENDAR], 'disabled')
        self.apply(self.demo.plan_package_action(self.serial, 'undo'))
        self.assertEqual(self.states()[KINDLE], 'enabled')
        self.assertEqual(self.states()[CALENDAR], 'disabled')
        self.apply(run_feature(self.demo, self.serial, BY_KEY['debloat-restore'], {}))
        self.assertEqual(self.states()[CALENDAR], 'enabled')

    def test_custom_lists_do_not_read_host_files_or_claim_to_have_applied(self):
        before = self.states()
        with patch('pathlib.Path.open', side_effect=AssertionError('file access')), \
             patch('builtins.open', side_effect=AssertionError('file access')), \
             patch('subprocess.Popen', side_effect=AssertionError('subprocess')):
            with self.assertRaisesRegex(ToolkitError, '(?i)demo.*custom|custom.*demo'):
                self.plan(profile='custom', list_file='example.debloat')
        self.assertEqual(self.states(), before)

    def test_update_undo_rejects_an_unrelated_package_batch(self):
        self.apply(self.demo.plan_package_action(self.serial, 'disable', (KINDLE,)))
        with self.assertRaisesRegex(ToolkitError, 'other apps'):
            run_feature(self.demo, self.serial, BY_KEY['ota-undo'], {})
        self.assertEqual(self.states()[KINDLE], 'disabled')

    def test_enabling_an_explicit_removed_app_keeps_it_removed(self):
        self.apply(self.demo.plan_package_action(self.serial, 'uninstall', (SILK,)))
        self.apply(self.demo.plan_package_action(self.serial, 'enable', (SILK,)))
        self.assertIn(SILK, self.states('uninstalled'))

    def test_manual_selection_and_undo_refuse_protected_packages_before_changing_any(self):
        before = self.states()
        with patch('pathlib.Path.open', side_effect=AssertionError('file access')), \
             patch('subprocess.Popen', side_effect=AssertionError('hardware')):
            for operation in ('disable', 'uninstall'):
                with self.subTest(operation=operation), self.assertRaisesRegex(ToolkitError, '(?i)protected'):
                    self.apply(self.demo.plan_package_action(self.serial, operation, (KINDLE, SETUP)))
                self.assertEqual(self.states(), before)
            self.demo.package_undo = {'com.amazon.kindle.kso': 'disabled'}
            with self.assertRaisesRegex(ToolkitError, '(?i)protected'):
                self.demo.plan_package_action(self.serial, 'undo')
            self.assertEqual(self.states(), before)


if __name__ == '__main__':
    unittest.main()
