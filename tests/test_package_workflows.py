"""Owner package workflow tests at the Android command boundary."""
import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import re
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
        self.modes = {}
        self.default_disabled = set()
        self.denied = self.ignore = self.change_after = ''
        self.home = STOCK + '/.Home'
        self.keyboard = 'com.android.inputmethod.latin/.Ime'
        self.updates = {A}
        self.package_dumps = {}
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
            if package in self.package_dumps:
                return self.package_dumps[package]
            mode = self.modes.get(package, '3' if package in self.disabled else '0')
            return f'    User 0: installed=true enabled={mode} stopped=' + ('true' if package in self.stopped else 'false')
        self.writes.append(args)
        if package == self.denied:
            return 'Failure [Permission Denial]'
        if package == self.change_after:
            self.device = replace(self.device, model='Other')
        modes = {'default-state': '0', 'enable': '1', 'disable': '2', 'disable-user': '3', 'disable-until-used': '4'}
        if args[0] == 'pm' and args[1] in modes:
            if package != self.ignore:
                self.modes[package] = mode = modes[args[1]]
                if mode in {'2', '3', '4'} or mode == '0' and package in self.default_disabled:
                    self.disabled.add(package)
                else:
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

    def run_cli(self, args):
        from open_fire_toolkit.cli import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = main(args)
        return result, output.getvalue()

    def test_cli_confirms_the_reviewed_files_signers_and_selection(self):
        paths = [self.root / 'a.apk', self.root / 'b.apk']
        packages = ['org.example.first', 'org.example.second']
        certificates = dict(zip(packages, ('a' * 64, 'b' * 64)))
        for path, package in zip(paths, packages):
            path.write_text(package)

        def inspect(path):
            path = Path(path)
            name = path.read_text()
            return ApkInfo(path, name, 1, '1', 23, (), hashlib.sha256(path.read_bytes()).hexdigest(),
                           (certificates[name],))

        with patch('open_fire_toolkit.cli.Toolkit', return_value=self.tool), patch.object(self.tool, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = inspect
            args = ['tool', 'sideload', '--serial', SERIAL, '--param', 'paths=' + json.dumps(list(map(str, paths)))]
            result, preview = self.run_cli(args)
            self.assertEqual(result, 0, preview)
            match = re.search(r'--confirm-token ([0-9a-f]{64})', preview)
            self.assertIsNotNone(match, preview)
            confirm = ['--yes', '--confirm-token', match[1]]
            self.assertEqual(self.run_cli(args + ['--yes'])[0], 1)
            certificates[packages[1]] = 'c' * 64
            self.assertEqual(self.run_cli(args + confirm)[0], 1)
            self.assertEqual(self.adb.installs, [])
            certificates[packages[1]] = 'b' * 64
            self.assertEqual(self.run_cli(args + confirm)[0], 0)
            self.assertEqual(self.adb.installs, packages)

            custom = self.root / 'apps.txt'
            custom.write_text(A)
            args = ['tool', 'debloat', '--serial', SERIAL, '--param', 'profile=custom', '--param', 'list_file=' + str(custom)]
            result, preview = self.run_cli(args)
            self.assertEqual(result, 0, preview)
            token = re.search(r'--confirm-token ([0-9a-f]{64})', preview)[1]
            custom.write_text(B)
            self.assertEqual(self.run_cli(args + ['--yes', '--confirm-token', token])[0], 1)
            self.assertEqual(self.adb.disabled, set())

    def test_accepted_last_package_write_survives_disconnect_or_identity_change(self):
        self.adb.change_after = A
        with self.assertRaisesRegex(ToolkitError, 'Completed:.*accepted.*' + A):
            self.execute(self.plan('disable', (A,)))
        self.assertEqual(self.adb.disabled, {A})
        self.adb.device = replace(self.adb.device, model='Fire')
        self.adb.change_after = ''
        self.execute(self.plan('undo'))
        shell = self.adb.shell
        def inventory(serial, args):
            if B in self.adb.disabled and tuple(args[:3]) == ('pm', 'list', 'packages'):
                raise OSError('tablet disconnected')
            return shell(serial, args)
        with patch.object(self.adb, 'shell', side_effect=inventory):
            with self.assertRaisesRegex(ToolkitError, 'Completed:.*' + A + '.*accepted.*' + B):
                self.execute(self.plan('disable', (A, B)))
        self.assertEqual(self.adb.disabled, {A, B})
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, set())

    def test_last_component_and_factory_rollback_verify_reviewed_identity(self):
        for op, packages, params, target in (
            ('launcher-set', (), {'component': HOME + '/.Home'}, HOME + '/.Home'),
            ('rollback-system', (A,), {}, A),
        ):
            with self.subTest(operation=op):
                self.adb.device = replace(self.adb.device, model='Fire')
                self.adb.change_after = target
                with self.assertRaisesRegex(ToolkitError, 'Completed:.*accepted.*' + target):
                    self.execute(self.plan(op, packages, **params))

    def test_inventory_distinguishes_disabled_and_removed(self):
        self.adb.disabled.add(B)
        for mode, expected in [('third-party', {HOME, IME}), ('uninstalled', {'org.example.removed'}),
                               ('disabled', {B}), ('system', self.adb.system), ('all', self.adb.present)]:
            rows = self.tool.package_inventory(SERIAL, mode)
            self.assertEqual({row['package'] for row in rows}, expected)
            self.assertTrue(all(row['label'] and row['state'] for row in rows))

    def test_package_info_reports_active_split_app_and_effective_owner_state(self):
        self.adb.disabled.add(A)
        self.adb.package_dumps[A] = """Activity Resolver Table:
  Package [com.amazon.kindle] (ffff):
    versionName=resolver noise
Packages:
  Package [com.amazon.kindle.store] (11ab):
    versionName=other app
  Package [com.amazon.kindle] (d181ae2):
    codePath=/data/app/com.amazon.kindle
    versionCode=4200000001 minSdk=23 targetSdk=33
    versionName=5.4.1 Fire Edition
    splits=[base, config.en, config.arm64_v8a]
    User 0: installed=true hidden=false enabled=3
    User 10: installed=true hidden=false enabled=1
      versionName=other profile decoration
Hidden system packages:
  Package [com.amazon.kindle] (1c12):
    versionCode=12 minSdk=15 targetSdk=19
    versionName=factory build
"""
        report = self.tool.package_info(SERIAL, A)
        for field in (A, 'Kindle', 'Owner user 0: installed, disabled', 'Type: system',
                      'Version name: 5.4.1 Fire Edition', 'Version code: 4200000001',
                      'Minimum SDK: 23', 'Target SDK: 33'):
            self.assertIn(field, report)
        for irrelevant in ('resolver noise', 'other app', 'other profile', 'factory build'):
            self.assertNotIn(irrelevant, report)
        self.assertEqual(self.adb.writes, [])
        self.assertEqual(self.adb.installs, [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_package_info_reports_missing_oem_fields_without_using_external_stanzas(self):
        self.adb.package_dumps[HOME] = """Packages:
  Package [org.example.home] (1a):
    targetSdk=30
    versionName=null
  Package [org.example.home.helper] (2a):
    versionName=helper
    versionCode=4 minSdk=20 targetSdk=34
Disabled system packages:
  Package [org.example.home] (3a):
    versionName=factory
    versionCode=1 minSdk=15 targetSdk=20
"""
        report = self.tool.package_info(SERIAL, HOME)
        for field in ('Label: not reported', 'Owner user 0: installed, enabled', 'Type: third-party',
                      'Version name: not reported', 'Version code: not reported',
                      'Minimum SDK: not reported', 'Target SDK: 30'):
            self.assertIn(field, report)

    def test_package_info_does_not_report_version_from_hidden_or_duplicate_packages(self):
        stanza = '  Package [org.example.home] (7d3):\n    versionName=wrong version\n'
        for dump in ('Hidden system packages:\n' + stanza, 'Packages:\n' + stanza * 2,
                     'Packages:\n  Package [org.example.home.helper] (afa):\n    versionName=wrong version',
                     'Package Changes:\n  Packages:\n' + stanza):
            with self.subTest(dump=dump):
                self.adb.package_dumps[HOME] = dump
                report = self.tool.package_info(SERIAL, HOME)
                self.assertIn('Version name: not reported', report)
                self.assertNotIn('wrong version', report)

    def test_package_info_rejects_control_characters_and_overlong_values(self):
        for name in ('3\x1b[2J', '3\u202ebogus', '3\rspoof', '3\u2028    minSdk=777', 'x' * 1024):
            with self.subTest(name=name[:30]):
                self.adb.package_dumps[HOME] = 'Packages:\n  Package [org.example.home] (a):\n    versionName=' + name
                report = self.tool.package_info(SERIAL, HOME)
                self.assertIn('Version name: not reported', report)
                self.assertIn('Minimum SDK: not reported', report)
                self.assertNotIn(name, report)

    def test_package_info_identifies_absent_or_removed_owner_app_without_reading_global_version(self):
        for package, expected in [('org.example.removed', 'uninstalled'), ('org.example.absent', 'not found')]:
            with self.subTest(package=package), patch.object(self.adb, 'shell', wraps=self.adb.shell) as shell:
                report = self.tool.package_info(SERIAL, package)
                self.assertIn(package, report)
                self.assertIn(expected, report)
                for (serial, args), _ in shell.call_args_list:
                    self.assertEqual(serial, SERIAL)
                    self.assertEqual(tuple(args[:5]), ('pm', 'list', 'packages', '--user', '0'))
                self.assertEqual(list(self.root.iterdir()), [])

    def test_package_info_validates_identifier_before_queries(self):
        with patch.object(self.adb, 'shell') as shell, self.assertRaisesRegex(ToolkitError, 'identifier'):
            self.tool.package_info(SERIAL, HOME + ' extra')
        shell.assert_not_called()

    def test_package_info_fails_clearly_if_owner_inventory_changes_or_dump_exceeds_limit(self):
        self.adb.known.remove(HOME)
        with self.assertRaisesRegex(ToolkitError, 'lists changed'):
            self.tool.package_info(SERIAL, HOME)
        self.adb.known.add(HOME)
        self.adb.package_dumps[HOME] = 'X' * (1024 * 1024 + 1)
        with self.assertRaisesRegex(ToolkitError, 'limit'):
            self.tool.package_info(SERIAL, HOME)
        self.assertFalse(self.adb.writes)

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

    def test_toolbox_list_footer_and_restore_keep_direction_and_undo(self):
        custom = self.root / 'selected.debloat'
        custom.write_text('^Group description\n+Section\n++End\n' + A + ' \n' + B +
                          '\ncom.android.settings\n#Ignored package\nListType=debloat\n', encoding='utf-16')
        plan = self.plan('debloat', profile='custom', list_file=str(custom))
        self.assertEqual(plan.packages, (A, B))
        self.assertIn('Skipped com.android.settings: protected', ' '.join(plan.details))
        self.execute(plan)
        self.assertEqual(self.adb.disabled, {A, B})
        custom.write_text('ListType=restore\n^Test list\n' + A + '\n' + B + ' # annotated line\n')
        with self.assertRaises(ToolkitError):
            self.plan('debloat', profile='custom', list_file=str(custom), mode='disable')
        restore = self.plan('debloat', profile='custom', list_file=str(custom))
        self.assertEqual(restore.packages, (A,))
        self.assertIn('disabled → enabled', ' '.join(restore.details))
        self.execute(restore)
        self.assertEqual(self.adb.disabled, {B})
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, {A, B})

    def test_incomplete_debloat_retry_preserves_original_states(self):
        custom = self.root / 'apps.debloat'
        custom.write_text(A + '\n' + B + '\nListType=debloat')
        for options in ({'profile': 'standard'}, {'profile': 'custom', 'list_file': str(custom)}):
            with self.subTest(options=options):
                self.adb.denied = B
                with self.assertRaisesRegex(ToolkitError, 'Permission Denial'):
                    self.execute(self.plan('debloat', **options))
                self.assertEqual(self.adb.disabled, {A})
                self.adb.denied = ''
                self.execute(self.plan('debloat', **options))
                self.assertEqual(self.adb.disabled, {A, B})
                self.execute(self.plan('undo'))
                self.assertFalse(self.adb.disabled)

    def test_different_custom_list_starts_its_own_undo_batch(self):
        custom = self.root / 'apps.debloat'
        custom.write_text(A + '\n' + B)
        options = {'profile': 'custom', 'list_file': str(custom)}
        self.adb.denied = B
        with self.assertRaisesRegex(ToolkitError, 'Permission Denial'):
            self.execute(self.plan('debloat', **options))
        custom.write_text(B)
        self.adb.denied = ''
        self.execute(self.plan('debloat', **options))
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, {A})

    def test_list_direction_change_after_preview_is_rejected(self):
        custom = self.root / 'apps.debloat'
        custom.write_text(A + '\nListType=debloat')
        plan = self.plan('debloat', profile='custom', list_file=str(custom))
        custom.write_text(A + '\nListType=restore')
        with self.assertRaises(ToolkitError):
            self.execute(plan)
        self.assertFalse(self.adb.writes)
        for header in ['ListType=other', 'ListType=debloat\nListType=restore']:
            custom.write_text(A + '\n' + header)
            with self.assertRaises(ToolkitError):
                self.plan('debloat', profile='custom', list_file=str(custom))

    def test_standard_complete_and_legacy_membership(self):
        from open_fire_toolkit.package_catalog import DEBLOAT_PROFILES
        excluded = {'com.android.contacts', 'com.android.calendar', 'com.android.email', 'com.amazon.dee.app'}
        self.assertFalse(excluded.intersection(DEBLOAT_PROFILES['standard']))
        self.assertTrue(excluded.issubset(DEBLOAT_PROFILES['complete']))
        self.assertTrue(excluded.issubset(DEBLOAT_PROFILES['standard-v0.2']))
        self.assertIn('org.mopria.printplugin', DEBLOAT_PROFILES['standard'])
        setup = 'com.amazon.kindle.otter.oobe'
        self.adb.known.add(setup)
        self.adb.present.add(setup)
        self.adb.disabled.add(A)
        self.assertEqual(self.plan('debloat', profile='standard', mode='enable').packages, (A,))
        complete = self.plan('debloat', profile='complete')
        self.assertNotIn(setup, complete.packages)
        self.assertIn('Device Setup (' + setup + '): protected', ' '.join(complete.details))

    def test_current_presets_keep_v46_order_through_preview_and_comparison(self):
        from open_fire_toolkit import package_catalog
        # The ordinary v46 Complete preset, with + marking its additions to Standard.
        entries = """
            +com.amazon.dee.app +com.amazon.venezia com.amazon.ags.app com.amazon.geo.client.maps
            com.amazon.mp3 com.amazon.kindle com.amazon.avod com.amazon.alexa.youtube.app
            com.audible.application.kindle +com.android.calculator2 +com.android.calendar
            +com.android.camera2 +com.android.deskclock +com.android.contacts +com.amazon.zico
            com.amazon.smartgenie +com.amazon.kindle.otter.oobe +com.android.email +com.amazon.tahoe
            com.goodreads.kindle com.amazon.csapp +com.amazon.imdb.tv.mobile.app com.amazon.webapp
            com.amazon.ods.kindleconnect org.mopria.printplugin com.android.music
            com.amazon.kindle.personal_video com.amazon.iris com.amazon.photos.importer com.amazon.photos
            com.amazon.windowshop +com.amazon.cloud9 com.kingsoft.office.amz com.washingtonpost.rainbow
            com.amazon.weather
        """.split()
        complete = tuple(p.lstrip('+') for p in entries)
        standard = tuple(p for p in entries if not p.startswith('+'))
        extras = tuple(p[1:] for p in entries if p.startswith('+'))
        self.adb.present.update(complete)
        self.adb.known.update(complete)
        self.assertEqual(self.plan('debloat').packages, standard)
        self.assertEqual(self.plan('debloat', profile='recommended'), self.plan('debloat', profile='standard'))
        plan = self.plan('debloat', profile='complete')
        self.assertEqual(plan.packages, tuple(p for p in complete if p != 'com.amazon.kindle.otter.oobe'))
        comparison = package_catalog.debloat_preset_comparison()
        self.assertEqual(tuple(re.findall(r'\(([\w]+(?:\.[\w]+)+)\)', comparison)), standard + extras)
        for name in ('Standard Debloat (Recommended)', 'Complete Debloat', '22', '35', '13', 'up to 34 eligible',
                     'Mayday Sharing', 'Device Setup', 'protected', 'Restore Everything', 'Undo'):
            self.assertIn(name, comparison)

    def test_complete_preview_explains_app_names_skips_counts_and_restore(self):
        self.adb.disabled.add(A)
        plan = self.plan('debloat', profile='complete')
        self.assertEqual(plan.title, 'Complete Debloat')
        self.assertEqual(plan.packages, (B,))
        details = '\n'.join(plan.details)
        for text in ('35 listed', '1 to disable', '34 skipped', 'owner user 0',
                     'Prime Photos', 'enabled → disabled', 'Amazon Newsstand',
                     'already disabled', 'Mayday Sharing', 'absent', 'Device Setup', 'protected'):
            self.assertIn(text, details)
        self.assertIn('Amazon Appstore', ' '.join(plan.warnings))
        self.assertFalse(self.adb.writes)

        restore = self.plan('debloat', profile='complete', mode='enable')
        self.assertEqual(restore.title, 'Restore Everything')
        self.assertEqual(restore.packages, (A,))
        self.assertIn('Undo', ' '.join(restore.details))

    def test_cli_restore_everything_enables_reviewed_disabled_apps_and_supports_undo(self):
        appstore, setup = 'com.amazon.venezia', 'com.amazon.kindle.otter.oobe'
        self.adb.known.update((appstore, setup))
        self.adb.present.update((appstore, setup))
        self.adb.disabled.update((appstore, setup, A, HOME))
        with patch('open_fire_toolkit.cli.Toolkit', return_value=self.tool):
            args = ['tool', 'debloat-restore', '--serial', SERIAL]
            code, preview = self.run_cli(args)
            self.assertEqual(code, 0, preview)
            self.assertIn('Restore Everything', preview)
            self.assertIn('Device Setup', preview)
            token = re.search(r'--confirm-token ([0-9a-f]{64})', preview)[1]
            self.assertEqual(self.run_cli(args + ['--yes'])[0], 1)
            self.assertFalse(self.adb.writes)
            code, applied = self.run_cli(args + ['--yes', '--confirm-token', token])
            self.assertEqual(code, 0, applied)
        self.assertEqual(self.adb.writes, [('pm', 'enable', '--user', '0', p) for p in (appstore, A)])
        self.assertEqual(self.adb.disabled, {setup, HOME})
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, {appstore, setup, A, HOME})

    def test_upgraded_preset_retry_preserves_undo_from_sorted_order(self):
        # Saved list-source values from the alphabetical v0.3.1 presets.
        for profile, source, pending in (
            ('recommended', '7bed63d1d483b752f73e9dfcdfc02fbec08466d3f25249a882dcfa0447bf2dee', True),
            ('complete', 'cb46bf84bf43b459e31f881c542137dc99a09af579375ea5d944a597be463dea', False),
        ):
            with self.subTest(profile=profile):
                self.adb.disabled.add(A)
                record = {'model': 'Fire', 'states': {A: 'enabled'}, 'restore_source': source}
                if pending:
                    record = {'model': 'Fire', 'states': {}, 'pending': {A: 'enabled'}, 'pending_source': source}
                data = {'schema': 1, 'devices': {self.adb.device.state_key: record}}
                (self.root / 'packages-state.json').write_text(json.dumps(data))
                retry = self.plan('debloat', profile=profile)
                self.assertEqual(retry.packages, (B,))
                self.execute(retry)
                self.execute(self.plan('undo'))
                self.assertEqual(self.adb.disabled, set())

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

    def test_special_offers_package_plans_wait_for_paired_restore(self):
        self.execute(self.plan('ads-disable'))
        stale_restore = self.plan('ads-restore')
        stale_undo = self.plan('undo')
        self.start_paired_ads_with_disabled_package()
        before = list(self.adb.writes)
        for op in ('ads-restore', 'ads-disable', 'undo'):
            with self.subTest(op=op), self.assertRaisesRegex(ToolkitError, '[Pp]aired'):
                self.plan(op)
        for plan in (stale_restore, stale_undo):
            with self.assertRaisesRegex(ToolkitError, '[Pp]aired'):
                self.execute(plan)
        self.assertEqual(self.adb.writes, before)
        self.execute(self.tool.plan_ads(SERIAL, restore=True, paired=True))
        self.execute(self.plan('undo'))
        self.assertNotIn(ADS, self.adb.disabled)

    def test_paired_ads_allows_unrelated_package_plan_and_undo(self):
        self.adb.disabled.add(ADS)
        self.start_paired_ads_with_disabled_package()
        self.execute(self.plan('disable', (A,)))
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, {ADS})
        self.execute(self.tool.plan_ads(SERIAL, restore=True, paired=True))

    def start_paired_ads_with_disabled_package(self):
        shell = self.adb.shell
        value = '1'
        def handle_ads(serial, args, timeout=30):
            nonlocal value
            if tuple(args) == ('dumpsys', 'package', ADS):
                mode = '3' if ADS in self.adb.disabled else '1'
                return f' User 0: installed=true enabled={mode}'
            if 'LOCKSCREEN_AD_ENABLED' in args:
                if 'get' in args:
                    return value
                self.assertIn('put', args)
                value = args[-1]
                return ''
            return shell(serial, args, timeout)
        self.adb.shell = handle_ads
        self.execute(self.tool.plan_ads(SERIAL, paired=True))

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
                            dict(package='com.google.android.syncadapters.contacts'),
                            dict(package='com.google.android.syncadapters.calendar'),
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

    def test_updater_status_returns_only_the_two_known_ids_and_reads_owner_state(self):
        override = OTA + '.override'
        def read():
            return {row['package']: (row['state'], row['type']) for row in self.tool.updater_status(SERIAL)}
        self.assertEqual(read(), {OTA: ('enabled', 'system'), override: ('absent', '-')})
        self.adb.known.add(override)
        self.assertEqual(read()[override], ('uninstalled', '-'))
        self.adb.present.add(override)
        self.adb.disabled.add(OTA)
        self.assertEqual(read(), {OTA: ('disabled', 'system'), override: ('enabled', 'non-system')})
        self.assertFalse(self.adb.writes)

    def test_ota_declines_a_non_system_package_at_preview_apply_and_undo(self):
        self.adb.system.remove(OTA)
        with self.assertRaisesRegex(ToolkitError, 'system package'):
            self.plan('ota-disable', (OTA,))
        self.adb.system.add(OTA)
        plan = self.plan('ota-disable', (OTA,))
        self.adb.system.remove(OTA)
        with self.assertRaisesRegex(ToolkitError, 'system package'):
            self.execute(plan)
        self.assertFalse(self.adb.writes)
        self.adb.system.add(OTA)
        self.execute(plan)
        self.adb.system.remove(OTA)
        with self.assertRaisesRegex(ToolkitError, 'system package'):
            self.plan('undo')
        self.assertEqual(len(self.adb.writes), 1)

    def test_undo_after_owner_removed_updater_never_reinstalls_it(self):
        self.execute(self.plan('ota-disable', (OTA,)))
        self.adb.present.remove(OTA)
        self.adb.disabled.remove(OTA)
        with self.assertRaisesRegex(ToolkitError, 'undo record'):
            self.plan('undo')
        self.assertEqual(len(self.adb.writes), 1)

    def test_ota_classification_change_during_batch_cannot_enable_a_replacement(self):
        override = OTA + '.override'
        self.adb.system.add(override)
        self.adb.present.add(override)
        self.adb.known.add(override)
        self.adb.disabled.update((OTA, override))
        plan = self.plan('ota-enable', (OTA, override))
        move = self.tool._pkg_move

        def swap_second_at_dispatch(plan, package, before, target, completed, prepare_write):
            if package == override:
                self.adb.system.remove(override)
            return move(plan, package, before, target, completed, prepare_write)

        with patch.object(self.tool, '_pkg_move', swap_second_at_dispatch):
            with self.assertRaisesRegex(ToolkitError, 'no longer an installed system package'):
                self.execute(plan)
        self.assertEqual(self.adb.disabled, {override})
        self.assertEqual([cmd[-1] for cmd in self.adb.writes], [OTA])
        undo = self.plan('undo', scope='updaters')
        self.assertEqual(undo.packages, (OTA,))
        self.assertFalse(any(override in line for line in undo.details))
        self.execute(undo)
        self.assertEqual(self.adb.disabled, {OTA, override})
        self.assertEqual([cmd[-1] for cmd in self.adb.writes], [OTA, OTA])
        self.adb.system.add(override)
        with self.assertRaisesRegex(ToolkitError, 'No package undo'):
            self.plan('undo', scope='updaters')

    def test_ota_partial_failure_and_retry_keep_both_original_states_for_undo(self):
        override = OTA + '.override'
        self.adb.system.add(override)
        self.adb.present.add(override)
        self.adb.known.add(override)
        self.adb.denied = override
        with self.assertRaises(ToolkitError):
            self.execute(self.plan('ota-disable', (OTA, override)))
        self.assertEqual(self.adb.disabled, {OTA})
        self.assertEqual(self.plan('undo', scope='updaters').packages, (OTA,))
        self.adb.denied = ''
        self.execute(self.plan('ota-disable', (override,)))
        self.assertEqual(self.adb.disabled, {OTA, override})
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.disabled, set())
        self.assertEqual(self.adb.modes, {OTA: '0', override: '0'})

    def test_updater_undo_restores_each_exact_mode_even_for_a_disabled_default(self):
        for mode, disabled in [('0', False), ('0', True), ('1', False), ('2', True), ('3', True), ('4', True)]:
            with self.subTest(mode=mode, disabled=disabled):
                self.adb.modes[OTA] = mode
                self.adb.disabled = {OTA} if disabled else set()
                self.adb.default_disabled = {OTA} if mode == '0' and disabled else set()
                self.execute(self.plan('ota-enable' if disabled else 'ota-disable', (OTA,)))
                self.execute(self.plan('undo', scope='updaters'))
                self.assertEqual(self.adb.modes[OTA], mode)
                self.assertEqual(OTA in self.adb.disabled, disabled)

    def test_updater_same_effective_mode_change_voids_preview_and_undo_checks_readback(self):
        preview = self.plan('ota-disable', (OTA,))
        self.adb.modes[OTA] = '1'
        with self.assertRaisesRegex(ToolkitError, 'changed'):
            self.execute(preview)
        self.assertFalse(self.adb.writes)
        self.adb.modes[OTA] = '0'
        self.execute(self.plan('ota-disable', (OTA,)))
        self.adb.modes[OTA] = '1'
        self.adb.disabled.clear()
        self.adb.ignore = OTA
        with self.assertRaisesRegex(ToolkitError, 'confirm'):
            self.execute(self.plan('undo'))
        self.adb.ignore = ''
        self.execute(self.plan('undo'))
        self.assertEqual(self.adb.modes[OTA], '0')

    def test_updater_missing_or_ambiguous_mode_denies_change(self):
        for dump in ('User 0: installed=true', 'User 0: installed=false enabled=2',
                     'User 0: installed=true enabled=5', 'User 0: installed=true enabled=0 enabled=1'):
            self.adb.package_dumps[OTA] = dump
            with self.subTest(dump=dump), self.assertRaises(ToolkitError):
                self.plan('ota-disable', (OTA,))
        self.assertFalse(self.adb.writes)

    def test_uncertain_first_updater_preserves_prior_batch_until_mode_is_readable(self):
        self.execute(self.plan('disable', (A,)))
        shell = self.adb.shell
        def stop_before_write(serial, args):
            if tuple(args) == ('pm', 'disable-user', '--user', '0', OTA):
                self.adb.system.remove(OTA)
                raise OSError('disconnected')
            return shell(serial, args)
        with patch.object(self.adb, 'shell', stop_before_write), self.assertRaisesRegex(ToolkitError, 'unverified'):
            self.execute(self.plan('ota-disable', (OTA,)))
        journal = json.loads((self.root / 'packages-state.json').read_text())['devices'][self.adb.device.state_key]
        self.assertEqual(journal['states'], {A: 'enabled'})
        self.assertEqual(journal['pending'], {OTA: 'enabled:0'})
        self.adb.system.add(OTA)
        self.assertEqual(self.plan('undo').packages, (A,))

    def test_legacy_updater_undo_restores_only_saved_effective_state(self):
        self.tool._pkg_save_undo(self.adb.device, {'schema': 1, 'devices': {}}, {OTA: 'enabled'})
        self.adb.modes[OTA] = '3'
        self.adb.disabled.add(OTA)
        plan = self.plan('undo')
        self.assertIn('older', ' '.join(plan.details).lower())
        self.execute(plan)
        self.assertEqual(self.adb.modes[OTA], '1')

    def test_interrupted_second_updater_is_recovered_only_if_its_mode_changed(self):
        override = OTA + '.override'
        self.adb.system.add(override)
        self.adb.present.add(override)
        self.adb.known.add(override)
        shell = self.adb.shell
        for written in (False, True):
            def stop(serial, args):
                if tuple(args) == ('pm', 'disable-user', '--user', '0', override):
                    if written:
                        shell(serial, args)
                    raise KeyboardInterrupt
                return shell(serial, args)
            with self.subTest(written=written), patch.object(self.adb, 'shell', stop), self.assertRaises(KeyboardInterrupt):
                self.execute(self.plan('ota-disable', (OTA, override)))
            undo = self.plan('undo')
            self.assertEqual(set(undo.packages), {OTA, override} if written else {OTA})
            self.execute(undo)
            self.assertFalse(self.adb.disabled)

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
