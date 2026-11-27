"""Owner package workflow tests at the Android command boundary."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from open_fire_toolkit.adb import DeviceInfo
from open_fire_toolkit.apk import ApkInfo
from open_fire_toolkit.service import Toolkit, ToolkitError, ToolConfig

A = 'com.amazon.kindle'
B = 'com.amazon.photos'
STOCK = 'com.amazon.firelauncher'
HOME = 'org.example.home'
IME = 'org.example.ime'
ADS = 'com.amazon.kindle.kso'
OTA = 'com.amazon.device.software.ota'
SERIAL = 'TEST1'


class Tablet:
    """Model observable Android shell state, including a package removed for user 0."""
    def __init__(self):
        self.device = DeviceInfo(SERIAL, 'Fire', 'Amazon', '8', '11', 30, ('arm64-v8a',), 0)
        self.system = {A, B, ADS, OTA, STOCK}
        self.known = self.system | {HOME, IME, 'org.example.removed'}
        self.present = self.known - {'org.example.removed'}
        self.disabled = set()
        self.denied = self.ignore = self.change_after = ''
        self.home = STOCK + '/.Home'
        self.keyboard = 'com.android.inputmethod.latin/.Ime'
        self.updates = {A}
        self.writes = []
        self.installs = []
        self.apk_files = {}
        self.stopped = set()

    def info(self, serial):
        return self.device

    def install(self, serial, path):
        package = Path(path).read_text()
        self.installs.append(package)
        self.apk_files[package] = Path(path).read_bytes()
        self.present.add(package)
        self.known.add(package)
        if package in self.system:
            self.updates.add(package)
        return 'Success'

    def _run_device(self, serial, args, timeout=30):
        command, source, destination = args
        assert command == 'pull'
        Path(destination).write_bytes(self.apk_files[Path(source).parent.name])

    def shell(self, serial, args, timeout=30):
        args = tuple(args)
        package = args[-1]
        if args[:3] == ('pm', 'list', 'packages'):
            assert '--user' in args and args[args.index('--user') + 1] == '0', args
            subset = self.present
            for flag, values in [('-d', self.disabled), ('-s', self.system), ('-u', self.known),
                                 ('-3', self.present - self.system)]:
                if flag in args:
                    subset = values
            return '\n'.join('package:' + p for p in sorted(subset))
        if args[:3] == ('cmd', 'package', 'resolve-activity'):
            if '-p' in args:
                return package + ('/.Home' if 'android.intent.category.HOME' in args else '/.Main')
            return self.home
        if args[:3] == ('ime', 'list', '-s'):
            return IME + '/.Ime\n' + self.keyboard
        if args[:1] == ('settings',) and 'default_input_method' in args:
            return self.keyboard
        if args == ('pm', 'help'):
            return '  uninstall-system-updates [<PACKAGE>]\n'
        if args[:3] == ('stat', '-c', '%s'):
            return str(len(self.apk_files[Path(package).parent.name]))
        if args[:2] == ('pm', 'path'):
            return 'package:' + ('/data/app/' if package in self.updates else '/system/app/') + package + '/base.apk'
        if args[:2] == ('dumpsys', 'package'):
            return '    User 0: installed=true stopped=' + ('true' if package in self.stopped else 'false')
        self.writes.append(args)
        if package == self.denied:
            return 'Failure [Permission Denial]'
        if package == self.change_after:
            self.device = replace(self.device, model='Other')
        if args[:2] == ('pm', 'disable-user'):
            if package != self.ignore:
                self.disabled.add(package)
        elif args[:2] == ('pm', 'enable'):
            self.disabled.discard(package)
        elif args[:4] == ('pm', 'uninstall', '-k', '--user'):
            self.present.remove(package)
            self.disabled.discard(package)
        elif args[:3] == ('cmd', 'package', 'install-existing'):
            self.present.add(package)
        elif args[:2] == ('pm', 'set-home-activity'):
            if package != self.ignore:
                self.home = package
        elif args[:2] == ('ime', 'set'):
            self.keyboard = package
        elif args[:2] == ('pm', 'uninstall-system-updates'):
            self.updates.remove(package)
        elif args[:2] == ('am', 'force-stop'):
            self.stopped.add(package)
        elif args[:2] == ('am', 'start'):
            return 'Status: ok\nActivity: ' + package
        elif args[:2] not in {('ime', 'enable'), ('pm', 'clear')}:
            raise AssertionError(args)
        return 'Success'


class PackageWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.adb = Tablet()
        with patch('open_fire_toolkit.service.AdbClient', return_value=self.adb):
            self.tool = Toolkit(ToolConfig('adb'), self.root)
        self.assertTrue(hasattr(self.tool, 'plan_package_action'), 'package workflow service missing')

    def plan(self, op, packages=(), **options):
        return self.tool.plan_package_action(SERIAL, op, packages, **options)

    def execute(self, plan):
        return self.tool.execute(plan, confirmed=True, log=lambda message: None)

    def test_inventory_distinguishes_disabled_and_removed(self):
        self.adb.disabled.add(B)
        for mode, expected in [('third-party', {HOME, IME}), ('uninstalled', {'org.example.removed'}),
                               ('disabled', {B}), ('system', self.adb.system), ('all', self.adb.present)]:
            rows = self.tool.package_inventory(SERIAL, mode)
            self.assertEqual({row['package'] for row in rows}, expected)
            self.assertTrue(all(row['label'] and row['state'] for row in rows))

    def test_invalid_and_protected_selections(self):
        for name in ('x.y;reboot', 'com.android.settings', 'com.android.systemui', 'com.android.shell',
                     'com.android.providers.media', STOCK, 'com.google.android.permissioncontroller'):
            self.adb.known.add(name)
            self.adb.present.add(name)
            with self.subTest(name=name), self.assertRaises(ToolkitError):
                self.plan('disable', (name,))
        for op in ('keyboard-set', 'launcher-set'):
            with self.assertRaises(ToolkitError):
                self.plan(op, component='org.example/.Thing;reboot')
        self.assertFalse(self.adb.writes)

    def test_undo_after_partial_failure_restores_exact_owner_states(self):
        self.adb.disabled.add(A)
        self.adb.denied = B
        with self.assertRaisesRegex(ToolkitError, 'Completed:.*' + A):
            self.execute(self.plan('uninstall', (A, B)))
        self.assertNotIn(A, self.adb.present)
        self.adb.denied = ''
        self.execute(self.plan('undo'))
        self.assertIn(A, self.adb.present)
        self.assertEqual(self.adb.disabled, {A})
        self.assertNotIn(('pm', 'enable', '--user', '0', B), self.adb.writes)

    def test_stale_before_batch_or_after_undo_preview(self):
        plan = self.plan('disable', (A, B))
        self.adb.disabled.add(B)
        with self.assertRaises(ToolkitError):
            self.execute(plan)
        self.assertFalse(self.adb.writes)
        self.execute(self.plan('disable', (A,)))
        undo = self.plan('undo')
        self.execute(self.plan('enable', (B,)))
        with self.assertRaises(ToolkitError):
            self.execute(undo)
        self.assertIn(A, self.adb.disabled)

    def test_unchanged_readback_and_identity_swap_stop_batch(self):
        self.adb.ignore = A
        with self.assertRaises(ToolkitError):
            self.execute(self.plan('disable', (A, B)))
        self.assertNotIn(B, self.adb.disabled)
        self.adb.ignore = ''
        self.adb.change_after = A
        with self.assertRaises(ToolkitError):
            self.execute(self.plan('disable', (A, B)))
        self.assertNotIn(B, self.adb.disabled)

    def test_debloat_custom_only_changes_previewed_apps(self):
        file = self.root / 'custom.txt'
        file.write_text('# selected\n' + B + '\norg.example.missing\n' + A + ' # keep data\n')
        plan = self.plan('debloat', profile='custom', list_file=str(file))
        self.assertEqual(set(plan.packages), {A, B})
        self.assertIn('org.example.missing', ' '.join(plan.details))
        self.execute(plan)
        self.assertEqual(self.adb.disabled, {A, B})
        for contents in ['com.android.settings', 'a.b; reboot', '\n'.join(f'test.p{i}' for i in range(257))]:
            file.write_text(contents)
            with self.assertRaises(ToolkitError):
                self.plan('debloat', profile='custom', list_file=str(file))

    def test_presets_exclude_updater_and_specialized_targets(self):
        for profile in ('standard', 'complete'):
            plan = self.plan('debloat', profile=profile)
            self.assertIn(A, plan.packages)
            self.assertFalse(set(plan.packages) & {OTA, STOCK, ADS})
        for prefix, pkg in [('ads', ADS), ('ota', OTA)]:
            kwargs = {'packages': (pkg,)} if prefix == 'ota' else {}
            self.execute(self.plan(prefix + '-disable', **kwargs))
            self.assertIn(pkg, self.adb.disabled)
            self.execute(self.plan(prefix + ('-restore' if prefix == 'ads' else '-enable'), **kwargs))
            self.assertNotIn(pkg, self.adb.disabled)

    def test_launcher_verifies_replacement_before_disabling_stock_and_restores(self):
        alternate = HOME + '/.Home'
        self.adb.ignore = alternate
        with self.assertRaises(ToolkitError):
            self.execute(self.plan('launcher-set', component=alternate, disable_stock='true'))
        self.assertNotIn(STOCK, self.adb.disabled)
        self.adb.ignore = ''
        self.execute(self.plan('launcher-set', component=alternate, disable_stock='true'))
        self.assertEqual(self.adb.home, alternate)
        self.assertIn(STOCK, self.adb.disabled)
        self.execute(self.plan('launcher-restore'))
        self.assertEqual(self.adb.home, STOCK + '/.Home')
        self.assertNotIn(STOCK, self.adb.disabled)

    def test_keyboard_requires_listed_service(self):
        with self.assertRaises(ToolkitError):
            self.plan('keyboard-set', component=IME + '/.NotAnIme')
        self.execute(self.plan('keyboard-set', component=IME + '/.Ime'))
        self.assertEqual(self.adb.keyboard, IME + '/.Ime')

    def test_clear_stop_launch_and_system_rollback(self):
        plan = self.plan('clear-data', (A,))
        self.assertIn('data', ' '.join(plan.warnings).lower())
        self.execute(plan)
        self.execute(self.plan('force-stop', (A,)))
        self.assertIn(A, self.adb.stopped)
        self.execute(self.plan('launch', (A,)))
        self.execute(self.plan('rollback-system', (A,)))
        self.assertFalse(self.adb.updates)
        with self.assertRaises(ToolkitError):
            self.plan('rollback-system', (HOME,))

    def test_signed_apks_are_all_staged_before_any_install(self):
        paths = [self.root / 'a.apk', self.root / 'b.apk']
        for index, path in enumerate(paths):
            path.write_text(f'org.example.app{index}')
        def inspect(path):
            path = Path(path)
            return ApkInfo(path, path.read_text(), 1, '1', 23, (), hashlib.sha256(path.read_bytes()).hexdigest(), ('a' * 64,))
        with patch.object(self.tool, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = inspect
            options = {'paths': json.dumps([str(p) for p in paths])}
            with self.assertRaises(ToolkitError):
                self.plan('sideload', **options, signer='b' * 64)
            plan = self.plan('sideload', **options)
            self.assertIn('a' * 64, ' '.join(plan.details))
            paths[-1].write_text('org.example.changed')
            with self.assertRaises(ToolkitError):
                self.execute(plan)
            self.assertFalse(self.adb.installs)
            paths[-1].write_text('org.example.app1')
            self.execute(plan)
            self.assertEqual(self.adb.installs, ['org.example.app0', 'org.example.app1'])
            paths[0].write_text(A)
            update = self.plan('system-update', (A,), paths=json.dumps([str(paths[0])]))
            self.execute(update)
            with self.assertRaises(ToolkitError):
                self.plan('system-update', (B,), paths=json.dumps([str(paths[0])]))

    def test_missing_third_party_image_keeps_undo_for_later_and_restores_other_apps(self):
        self.execute(self.plan('uninstall', (A, HOME)))
        self.adb.known.remove(HOME)  # Android discarded its only APK.
        undo = self.plan('undo')
        self.assertEqual(undo.packages, (A,))
        self.assertIn(HOME, ' '.join(undo.details))
        self.execute(undo)
        self.assertIn(A, self.adb.present)
        with self.assertRaisesRegex(ToolkitError, 'APK'):
            self.plan('undo')
        # Reintroduce the image; it still isn't installed for this user.
        self.adb.known.add(HOME)
        retry = self.plan('undo')
        self.assertEqual(retry.packages, (HOME,))
        self.execute(retry)
        self.assertIn(HOME, self.adb.present)
        with self.assertRaises(ToolkitError):
            self.plan('undo')

    def test_core_provider_modules_and_primary_user_infrastructure_are_protected(self):
        for p in ('com.google.android.providers.media.module', 'com.android.networkstack.tethering',
                  'com.android.location.fused', 'com.android.storagemanager'):
            self.adb.present.add(p)
            self.adb.known.add(p)
            with self.subTest(p=p), self.assertRaises(ToolkitError):
                self.plan('disable', (p,))
        self.assertFalse(self.adb.writes)

    def test_restore_removed_app_then_undo_returns_it_to_removed(self):
        p = 'org.example.removed'
        self.execute(self.plan('restore', (p,)))
        self.assertIn(('cmd', 'package', 'install-existing', '--user', '0', p), self.adb.writes)
        self.assertIn(p, self.adb.present)
        self.execute(self.plan('undo'))
        self.assertIn(('pm', 'uninstall', '-k', '--user', '0', p), self.adb.writes)
        self.assertNotIn(p, self.adb.present)

    def test_per_package_rollback_capability_required(self):
        shell = self.adb.shell
        with patch.object(self.adb, 'shell', side_effect=lambda serial, args:
                          '  uninstall-system-updates' if tuple(args) == ('pm', 'help') else shell(serial, args)):
            with self.assertRaisesRegex(ToolkitError, 'rollback'):
                self.plan('rollback-system', (A,))
        self.assertFalse(self.adb.writes)

    def test_active_input_and_last_home_are_guarded(self):
        self.adb.disabled.add(STOCK)
        self.adb.home = HOME + '/.Home'
        self.adb.keyboard = IME + '/.Ime'
        for p in (HOME, IME):
            for op in ('disable', 'clear-data', 'uninstall', 'force-stop'):
                with self.subTest(p=p, op=op), self.assertRaises(ToolkitError):
                    self.plan(op, (p,))
        self.assertFalse(self.adb.writes)

    def test_generic_apk_policy_rechecks_google_pin_sdk_abi_and_core_names(self):
        path = self.root / 'test.apk'
        path.write_bytes(b'apk')
        base = ApkInfo(path, A, 5, '5.0', 23, (), hashlib.sha256(b'apk').hexdigest(), ('a' * 64,))
        with patch.object(self.tool, '_verifier') as verifier:
            for changes in [dict(package='com.android.settings'), dict(package='com.google.android.gms'),
                            dict(min_sdk=31), dict(abis=('x86',)), dict(split=True)]:
                verifier.return_value.inspect.return_value = replace(base, **changes)
                with self.subTest(changes=changes), self.assertRaises(ToolkitError):
                    self.plan('sideload', paths=json.dumps([str(path)]))
        self.assertFalse(self.adb.installs)

    def test_staged_apk_late_signature_failure_prevents_entire_batch(self):
        paths = [self.root / 'first.apk', self.root / 'second.apk']
        for i, path in enumerate(paths):
            path.write_text('org.example.app' + str(i))
        def inspect(path):
            pkg = path.read_text()
            signer = 'b' if path.parent != self.root and pkg.endswith('1') else 'a'
            return ApkInfo(path, pkg, 1, '1', 23, (), hashlib.sha256(path.read_bytes()).hexdigest(), (signer * 64,))
        with patch.object(self.tool, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = inspect
            plan = self.plan('sideload', paths=json.dumps([str(p) for p in paths]))
            with self.assertRaisesRegex(ToolkitError, 'signer'):
                self.execute(plan)
        self.assertFalse(self.adb.installs)

    def test_selected_installed_keyboard_can_be_enabled_for_the_first_time(self):
        shell = self.adb.shell
        def enabled_only(serial, args):
            if tuple(args[:2]) == ('ime', 'list') and '-a' not in args:
                return self.adb.keyboard
            return shell(serial, args)
        with patch.object(self.adb, 'shell', side_effect=enabled_only):
            self.execute(self.plan('keyboard-set', component=IME + '/.Ime'))
        self.assertEqual(self.adb.keyboard, IME + '/.Ime')

    def test_denied_first_write_preserves_previous_batch_undo(self):
        self.execute(self.plan('disable', (A,)))
        self.adb.denied = B
        with self.assertRaisesRegex(ToolkitError, 'Permission Denial'):
            self.execute(self.plan('disable', (B,)))
        self.adb.denied = ''
        self.adb.disabled.add(B)  # Later independent change to previously denied app.
        undo = self.plan('undo')
        self.assertEqual(undo.packages, (A,))
        self.execute(undo)
        self.assertEqual(self.adb.disabled, {B})

    def test_process_exit_after_unconfirmed_first_write_recovers_correct_batch(self):
        self.execute(self.plan('disable', (A,)))
        shell = self.adb.shell
        def disconnect(serial, args):
            if tuple(args[:2]) == ('pm', 'disable-user'):
                shell(serial, args)
                raise KeyboardInterrupt
            return shell(serial, args)
        with patch.object(self.adb, 'shell', side_effect=disconnect), self.assertRaises(KeyboardInterrupt):
            self.execute(self.plan('disable', (B,)))
        self.assertEqual(self.plan('undo').packages, (B,))
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, {A})

    def test_partial_two_step_undo_reports_verified_reinstall_and_allows_retry(self):
        self.adb.disabled.add(A)
        self.execute(self.plan('uninstall', (A,)))
        shell = self.adb.shell
        def deny_disable(serial, args):
            if tuple(args[:2]) == ('pm', 'disable-user'):
                return 'Failure [Permission Denial]'
            return shell(serial, args)
        with patch.object(self.adb, 'shell', side_effect=deny_disable):
            with self.assertRaisesRegex(ToolkitError, 'Completed:.*[Rr]einstalled.*' + A):
                self.execute(self.plan('undo'))
        self.assertIn(A, self.adb.present)
        self.assertNotIn(A, self.adb.disabled)
        self.execute(self.plan('undo'))
        self.assertIn(A, self.adb.disabled)

    def test_restore_stock_with_no_resolvable_current_home(self):
        self.adb.disabled.add(STOCK)
        self.adb.home = 'No activity found'
        plan = self.plan('launcher-restore')
        self.assertIn('No activity found', ' '.join(plan.details))
        self.execute(plan)
        self.assertEqual(self.adb.home, STOCK + '/.Home')
        self.assertNotIn(STOCK, self.adb.disabled)
        self.adb.home = 'Permission Denial'
        with self.assertRaises(ToolkitError):
            self.plan('launcher-restore')

    def test_same_version_replacement_must_read_back_exact_reviewed_apk(self):
        path = self.root / 'replacement.apk'
        path.write_bytes(b'new-bytes')
        apk = ApkInfo(path, A, 42, '4.2', 23, (), hashlib.sha256(path.read_bytes()).hexdigest(), ('a' * 64,))
        self.adb.apk_files[A] = b'old-bytes'
        with patch.object(self.tool, '_verifier') as verifier, patch.object(self.adb, 'install', return_value='Success'):
            verifier.return_value.inspect.side_effect = lambda p: replace(apk, path=Path(p))
            plan = self.plan('system-update', (A,), paths=json.dumps([str(path)]))
            with self.assertRaisesRegex(ToolkitError, 'Completed:.*accepted.*' + A):
                self.execute(plan)
        self.assertEqual(self.adb.apk_files[A], b'old-bytes')

    def test_ota_requires_nonempty_known_selection(self):
        for op in ('ota-disable', 'ota-enable'):
            with self.subTest(op=op), self.assertRaisesRegex(ToolkitError, 'select|Select'):
                self.plan(op)
            with self.assertRaises(ToolkitError):
                self.plan(op, (A,))
        self.assertFalse(self.adb.writes)

    def test_process_exit_before_first_write_preserves_previous_batch(self):
        self.execute(self.plan('disable', (A,)))
        shell = self.adb.shell
        def interrupt_before_mutation(serial, args):
            if tuple(args[:2]) == ('pm', 'disable-user'):
                raise KeyboardInterrupt
            return shell(serial, args)
        with patch.object(self.adb, 'shell', side_effect=interrupt_before_mutation), self.assertRaises(KeyboardInterrupt):
            self.execute(self.plan('disable', (B,)))
        self.assertEqual(self.plan('undo').packages, (A,))
        self.execute(self.plan('undo'))
        self.assertFalse(self.adb.disabled)

    def test_owner_install_readback_requires_owner_registration(self):
        path = self.root / 'local.apk'
        package = 'org.example.new'
        path.write_text(package)
        apk = ApkInfo(path, package, 1, '1', 23, (), hashlib.sha256(path.read_bytes()).hexdigest(), ('a' * 64,))
        self.adb.apk_files[package] = path.read_bytes()
        with patch.object(self.tool, '_verifier') as verifier, patch.object(self.adb, 'install', return_value='Success'):
            verifier.return_value.inspect.side_effect = lambda p: replace(apk, path=Path(p))
            plan = self.plan('sideload', paths=json.dumps([str(path)]))
            with self.assertRaisesRegex(ToolkitError, 'Completed:.*accepted.*' + package):
                self.execute(plan)

    def test_package_journal_first_save_refuses_symlinked_state_directory(self):
        linked, outside = self.root / 'linked', self.root / 'outside'
        outside.mkdir()
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('host cannot create directory symlinks')
        self.tool.state_dir = linked
        with self.assertRaises((ToolkitError, OSError)):
            self.execute(self.plan('disable', (A,)))
        self.assertFalse(self.adb.writes)
        self.assertEqual(list(outside.iterdir()), [])

    def test_package_journal_read_refuses_final_file_symlink(self):
        outside = self.root / 'elsewhere.json'
        outside.write_text('{"schema":1,"devices":{}}')
        try:
            (self.root / 'packages-state.json').symlink_to(outside)
        except OSError:
            self.skipTest('host cannot create file symlinks')
        with self.assertRaises((ToolkitError, OSError)):
            self.plan('disable', (A,))
        self.assertFalse(self.adb.writes)
        self.assertEqual(outside.read_text(), '{"schema":1,"devices":{}}')

    @unittest.skipUnless(os.name == 'posix', 'directory rename fixture requires POSIX')
    def test_package_journal_publish_stays_in_original_directory(self):
        folder, moved, outside = (self.root / name for name in ('active', 'moved', 'outside'))
        folder.mkdir()
        outside.mkdir()
        self.tool.state_dir = folder
        real_replace = os.replace
        def redirect_before_publish(source, destination):
            folder.rename(moved)
            folder.symlink_to(outside, target_is_directory=True)
            real_replace(source, destination)
        with patch('open_fire_toolkit.package_workflows.os.replace', side_effect=redirect_before_publish):
            self.tool._pkg_save_undo(self.adb.device, {'schema': 1, 'devices': {}}, {A: 'enabled'})
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual([p.name for p in moved.iterdir()], ['packages-state.json'])
        self.assertIn(A, (moved / 'packages-state.json').read_text())
