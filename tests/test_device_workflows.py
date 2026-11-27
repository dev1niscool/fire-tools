"""Device workflows exercised with an in-memory tablet and real temporary host files."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from open_fire_toolkit.adb import DeviceInfo
from open_fire_toolkit.service import ToolkitError

from open_fire_toolkit.device_workflows import DeviceWorkflows
from open_fire_toolkit.package_workflows import PackageWorkflows


class Tablet:
    def __init__(self):
        self.info = DeviceInfo('serial-example', 'Fire', 'Amazon', '8', '11', 30, ('arm64-v8a',), 0)
        self.settings = {'system': {'screen_off_timeout': '30000'}, 'secure': {}, 'global': {}}
        self.writes = []
        self.deny = False
        self.change_after_write = False
        self.files = {'/storage/emulated/0/Download/item.txt': b'file bytes',
                      '/data/app/shop/base.apk': b'base', '/data/app/shop/split.apk': b'split'}
        self.dirs = {'/storage/emulated/0', '/storage/emulated/0/Download'}
        self.package_state = {'org.example.shop': True, 'com.amazon.kindle': True}
        self.profile_rows = {'0': 'Owner', '12': 'Reader'}
        self.wm = {'density': '240', 'size': '1200x800'}
        self.overrides = {}
        self.fail_pull = False
        self.permission_flags = {}
        self.extra_apps = {}
        self.services = {}
        self.users = '0'

    def packages(self, serial, disabled_only=False):
        return [key for key, enabled in self.package_state.items() if not disabled_only or not enabled]

    def _run_device(self, serial, args, timeout=30):
        op = args[0]
        if op == 'pull':
            Path(args[2]).write_bytes(self.files[args[1]])
            if self.fail_pull:
                raise ToolkitError('copy interrupted')
        elif op == 'push':
            self.files[args[2]] = Path(args[1]).read_bytes()
        elif op == 'reboot':
            self.writes.append(args)
        else:
            raise AssertionError(args)
        return SimpleNamespace(stdout='', stderr='', returncode=0)


    def shell(self, serial, args, timeout=30):
        assert serial == self.info.serial
        args = list(args)
        op = args[0]
        if args[:3] == ['pm', 'list', 'packages']:
            return '\n'.join('package:' + p for p in self.packages(serial, '-d' in args))
        if op == 'stat':
            if args[3] in self.files:
                return str(len(self.files[args[3]])) if args[2] == '%s' else 'regular file'
            if args[3] in self.dirs and args[2] == '%F':
                return 'directory'
            raise ToolkitError('missing remote file')
        if op == 'realpath':
            return args[1]
        if op == 'test':
            if args[2] == '-e' and (args[3] in self.files or args[3] in self.dirs):
                raise ToolkitError('exists')
            return ''
        if op == 'mkdir':
            self.dirs.add(args[1])
            return ''
        if op == 'rmdir':
            self.dirs.remove(args[1])
            return ''
        if op == 'rm':
            self.files.pop(args[-1], None)
            return ''
        if op == 'screencap':
            self.files[args[2]] = b'\x89PNG\r\n\x1a\nfake pixels'
            return ''
        if op == 'screenrecord':
            self.files[args[-1]] = b'\0\0\0\30ftypmp42fake'
            return ''
        if op == 'mv' and args[1] == '-nT':
            if args[3] not in self.files:
                self.files[args[3]] = self.files.pop(args[2])
            return ''
        if op == 'find':
            root = args[1]
            names = sorted(n for n in {*self.files, *self.dirs} if n == root or n.startswith(root+'/'))
            return '\0'.join(names) + '\0'
        if args[:4] == ['pm', 'path', '--user', '0']:
            paths = self.extra_apps.get(args[4], ['/data/app/shop/base.apk', '/data/app/shop/split.apk'])
            return '\n'.join('package:'+name for name in paths)
        if op == 'wm':
            key = args[1]
            if len(args) == 2:
                rows = [f'Physical {key}: {self.wm[key]}']
                if key in self.overrides:
                    rows.append(f'Override {key}: {self.overrides[key]}')
                return '\n'.join(rows)
            if args[2] == 'reset':
                self.overrides.pop(key, None)
            else:
                self.overrides[key] = args[2]
            return ''
        if args[:3] == ['cmd','appops','get']:
            return 'CAMERA: ' + self.appops
        if args[:3] == ['cmd','appops','set']:
            self.appops = args[-1]
            return ''
        if op == 'input' or args[:2] == ['am', 'start']:
            self.writes.append(args)
            return ''
        if args[:3] == ['pm', 'list', 'users']:
            return '\n'.join('UserInfo{'+k+':'+v+':0}' for k, v in self.profile_rows.items())
        if args[:2] == ['pm', 'create-user']:
            self.profile_rows['13'] = args[2]
            return 'Success: created user id 13'
        if args[:2] == ['pm', 'remove-user']:
            del self.profile_rows[args[2]]
            return 'Success: removed user'
        if args[:2] == ['am', 'switch-user']:
            self.users = args[2]
            return ''
        if args == ['am', 'get-current-user']:
            return self.users
        if args[:3] == ['cmd', 'package', 'query-services']:
            return self.services.get(args[-1], '')
        if args[:3] == ['cmd', 'package', 'resolve-activity']:
            return 'com.example.home/.Home'
        if args[:2] in (['pm','enable'], ['pm','disable-user']):
            self.package_state[args[-1]] = args[1] == 'enable'
            return ''
        if args[:2] in (['pm','grant'], ['pm','revoke']):
            self.permission_flags[args[-1]] = 'true' if args[1] == 'grant' else 'false'
            return ''
        if args[:2] == ['dumpsys', 'package']:
            return '  User 0: installed=true\n    runtime permissions:\n' + '\n'.join(
                '      ' + name + ': granted=' + val for name,val in self.permission_flags.items())
        if args[:3] == ['settings', '--user', '0']:
            action, namespace = args[3:5]
            values = self.settings[namespace]
            if action == 'list':
                return '\n'.join(k + '=' + v for k, v in values.items())
            if action == 'get':
                return values.get(args[5], 'null')
            self.writes.append(args)
            if self.deny:
                return 'SecurityException: Permission denial'
            if action == 'delete':
                values.pop(args[5], None)
            elif action == 'put':
                values[args[5]] = args[6]
            else:
                raise AssertionError(args)
            if self.change_after_write:
                self.info = replace(self.info, user_id=10)
            return ''
        if args == ['logcat', '-d', '-t', '500']:
            return 'recent event'
        if args == ['echo', '$(touch fake); ok']:
            self.writes.append(args)
            return args[1]
        raise AssertionError(args)


class Harness(DeviceWorkflows, PackageWorkflows):
    def _owner_device(self, serial):
        return self._writable_device(serial)

    def _writable_device(self, serial):
        if self.adb.info.user_id:
            raise ToolkitError('owner profile changed')
        return self.adb.info

    def _state_key(self, serial):
        return hashlib.sha256(serial.encode()).hexdigest()


class DeviceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host = Path(self.tmp.name)
        self.tool = Harness()
        self.tool.adb = Tablet()
        self.tool.state_dir = self.host / 'state'
        self.serial = self.tool.adb.info.serial
        self.done = []

    def plan(self, operation, **params):
        return self.tool.plan_device_action(self.serial, operation, **params)

    def run_plan(self, plan):
        self.tool._execute_device_workflow(plan, self.done, lambda _: None)

    def test_undo_distinguishes_literal_null_from_absent(self):
        self.tool.adb.settings['global']['example'] = 'null'
        self.run_plan(self.plan('setting', namespace='global', key='example', value='__DELETE__'))
        self.assertNotIn('example', self.tool.adb.settings['global'])
        self.run_plan(self.plan('setting-undo', namespace='global', key='example'))
        self.assertEqual('null', self.tool.adb.settings['global']['example'])

    def test_stale_setting_prevents_writes(self):
        plan = self.plan('timeout', value='15000')
        self.tool.adb.settings['system']['screen_off_timeout'] = '120000'
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.assertEqual([], self.tool.adb.writes)

    def test_reject_unsafe_or_unbounded_arguments(self):
        cases = [
            ('setting', dict(namespace='shell', key='foo', value='bar')),
            ('setting', dict(namespace='secure', key='adb_enabled', value='0')),
            ('setting', dict(namespace='secure', key='install_non_market_apps', value='1')),
            ('setting', dict(namespace='system', key='x\ny', value='1')),
            ('navigation', dict(value='immersive.*')),
            ('timeout', dict(value='1800001')),
            ('display', dict(density='0')),
            ('screenrecord', dict(local=str(self.host/'new.mp4'), seconds='181')),
            ('pull', dict(remote='/sdcard/../data/db', local=str(self.host/'new'))),
            ('user-remove', dict(user_id='0')),
            ('shell', dict(argv='["echo",2]')),
        ]
        for operation, params in cases:
            with self.subTest(operation=operation, params=params), self.assertRaises(ToolkitError):
                self.plan(operation, **params)
        self.assertEqual([], self.tool.adb.writes)

    def test_setter_denial_is_failure(self):
        plan = self.plan('timeout', value='15000')
        self.tool.adb.deny = True
        with self.assertRaisesRegex(ToolkitError, 'denial|denied|SecurityException'):
            self.run_plan(plan)
        self.assertEqual([], self.done)

    def test_profile_change_stops_batch(self):
        plan = self.plan('privacy', preset='limit-tracking')
        self.tool.adb.change_after_write = True
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.assertEqual(1, len(self.tool.adb.writes))

    def test_read_log_and_shell_token_boundaries(self):
        self.assertEqual('recent event', self.tool.read_device_tool(self.serial, 'logcat'))
        self.run_plan(self.plan('shell', argv=json.dumps(['echo', '$(touch fake); ok'])))
        self.assertEqual([['echo', '$(touch fake); ok']], self.tool.adb.writes)

    def test_settings_export_bound_to_device_and_hash(self):
        local = self.host / 'snapshot.json'
        self.run_plan(self.plan('settings-export', local=str(local)))
        raw = local.read_text()
        self.assertNotIn(self.serial, raw)
        first = self.plan('settings-import', local=str(local))
        local.write_text(raw+'\n')
        with self.assertRaises(ToolkitError):
            self.run_plan(first)
        local.write_text(raw.replace(self.tool._state_key(self.serial), '0'*64))
        with self.assertRaises(ToolkitError):
            self.plan('settings-import', local=str(local))

    def test_no_overwrite_or_symlink_destination_parent(self):
        existing = self.host/'saved.json'
        plan = self.plan('settings-export', local=str(existing))
        existing.write_text('keep')
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.assertEqual('keep', existing.read_text())
        link = self.host / 'redirect'
        try:
            link.symlink_to(self.host, target_is_directory=True)
        except OSError:
            self.skipTest('symlink unavailable')
        with self.assertRaises(ToolkitError):
            self.plan('settings-export', local=str(link/'out.json'))

    def test_snapshot_import_rejects_impossible_timeout(self):
        file = self.host / 'settings.json'
        self.run_plan(self.plan('settings-export', local=str(file)))
        data = json.loads(file.read_bytes())
        next(row for row in data['settings'] if row[1] == 'screen_off_timeout')[2] = '-1'
        file.write_text(json.dumps(data))
        with self.assertRaises(ToolkitError):
            self.plan('settings-import', local=str(file))

    def test_push_rechecks_source_digest_and_refuses_remote_overwrite(self):
        src = self.host / 'my file'
        src.write_bytes(b'one')
        remote = '/sdcard/Download/has spaces;ok'
        stale = self.plan('push', local=str(src), remote=remote)
        src.write_bytes(b'two')
        with self.assertRaises(ToolkitError):
            self.run_plan(stale)
        self.run_plan(self.plan('push', local=str(src), remote=remote))
        self.assertEqual(b'two', self.tool.adb.files['/storage/emulated/0/Download/has spaces;ok'])
        with self.assertRaises(ToolkitError):
            self.plan('push', local=str(src), remote=remote)

    def test_interrupted_pull_never_publishes_partial_output(self):
        dest = self.host / 'save.txt'
        plan = self.plan('pull', remote='/sdcard/Download/item.txt', local=str(dest))
        self.tool.adb.fail_pull = True
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.assertFalse(dest.exists())
        self.tool.adb.fail_pull = False
        self.run_plan(plan)
        self.assertEqual(b'file bytes', dest.read_bytes())

    def test_shared_storage_backup_and_extracted_splits(self):
        folder = self.host / 'backup'
        self.run_plan(self.plan('storage-backup', remote='/sdcard/Download', local=str(folder)))
        self.assertEqual(b'file bytes', (folder/'item.txt').read_bytes())
        apks = self.host / 'apks'
        self.run_plan(self.plan('extract-apk', package='org.example.shop', local=str(apks)))
        self.assertEqual([b'base', b'split'], [p.read_bytes() for p in sorted(apks.iterdir())])

    def test_capture_outputs_verified_and_temporary_entries_removed(self):
        tablet = self.tool.adb
        original = dict(tablet.files)
        for op, filename, args in [('screenshot','screen.png',{}), ('screenrecord','screen.mp4',{'seconds':'1'})]:
            dest = self.host / filename
            self.run_plan(self.plan(op, local=str(dest), **args))
            self.assertGreater(dest.stat().st_size, 12)
            self.assertEqual(original, tablet.files)

    def test_snapshot_restore_keeps_original_states_across_partial_retry(self):
        tablet = self.tool.adb
        tablet.package_state['com.amazon.weather'] = True
        for combined in (False, True):
            with self.subTest(combined=combined):
                tablet.package_state.update({'com.amazon.weather': True, 'com.amazon.kindle': True})
                local = str(self.host / ('all' if combined else 'packages.json'))
                self.run_plan(self.plan('backup' if combined else 'package-backup', local=local))
                tablet.package_state.update({'com.amazon.weather': False, 'com.amazon.kindle': False})
                operation = 'restore-backup' if combined else 'package-restore'
                shell = tablet.shell
                def partial(serial, args, timeout=30):
                    if tuple(args[:2]) == ('pm', 'enable') and args[-1] == 'com.amazon.weather':
                        return 'Failure [Permission Denial]'
                    return shell(serial, args, timeout)
                tablet.shell = partial
                try:
                    with self.assertRaises(ToolkitError):
                        self.run_plan(self.plan(operation, local=local))
                finally:
                    tablet.shell = shell
                self.assertTrue(tablet.package_state['com.amazon.kindle'])
                journal = self.tool.state_dir / 'packages-state.json'
                self.assertTrue(journal.is_file())
                self.run_plan(self.plan(operation, local=local))
                undo = self.tool.plan_package_action(self.serial, 'undo')
                self.tool._execute_package_workflow(undo, self.done, lambda _: None)
                self.assertFalse(tablet.package_state['com.amazon.kindle'])
                self.assertFalse(tablet.package_state['com.amazon.weather'])
                tablet.package_state.update({'com.amazon.weather': True, 'com.amazon.kindle': True})

    def test_parental_settings_is_a_general_settings_shortcut(self):
        from open_fire_toolkit.feature_catalog import BY_KEY
        feature = BY_KEY['parental-settings']
        self.assertFalse(feature.fields)
        plan = self.plan('parental-settings')
        self.assertIn('android.settings.SETTINGS', str(plan.details))
        self.assertIn('authenticate', str(plan.warnings))
        with self.assertRaises(ToolkitError):
            self.plan('parental-settings', mode='hide')

    def test_combined_restore_changes_only_supported_packages_and_settings(self):
        tablet = self.tool.adb
        local = self.host / 'config'
        self.run_plan(self.plan('backup', local=str(local)))
        tablet.package_state.update({'org.example.shop': False, 'com.amazon.kindle': False})
        tablet.settings['system']['screen_off_timeout'] = '60000'
        plan = self.plan('restore-backup', local=str(local))
        self.assertIn('org.example.shop', ' '.join(plan.warnings))
        self.run_plan(plan)
        self.assertEqual('30000', tablet.settings['system']['screen_off_timeout'])
        self.assertEqual({'org.example.shop':False, 'com.amazon.kindle':True}, tablet.package_state)

    def test_profiles_and_permission_readback(self):
        self.run_plan(self.plan('user-create', name='New reader'))
        self.assertIn('13', self.tool.adb.profile_rows)
        self.run_plan(self.plan('user-remove', user_id='13'))
        self.assertNotIn('13', self.tool.adb.profile_rows)
        self.run_plan(self.plan('grant', package='org.example.shop', permission='android.permission.CAMERA'))
        self.assertIn('Confirmed', self.done[-1])

    def test_display_and_coordinate_form(self):
        self.run_plan(self.plan('display', density='320', size=''))
        self.assertEqual({'density':'320'}, self.tool.adb.overrides)
        self.run_plan(self.plan('display', density='reset'))
        self.assertEqual({}, self.tool.adb.overrides)
        self.run_plan(self.plan('remote-input', kind='tap', value='10,20'))
        self.assertEqual(['input','tap','10','20'], self.tool.adb.writes[-1])

    def test_partial_privacy_change_can_be_restored(self):
        self.tool.adb.change_after_write = True
        with self.assertRaises(ToolkitError):
            self.run_plan(self.plan('privacy', preset='limit-tracking'))
        self.tool.adb.change_after_write = False
        self.tool.adb.info = replace(self.tool.adb.info, user_id=0)
        self.run_plan(self.plan('privacy', preset='restore'))
        self.assertEqual({}, self.tool.adb.settings['secure'])

    def test_helper_signer_mismatch_prevents_grant(self):
        name = 'org.firetools.adshelper'
        self.tool.adb.extra_apps[name] = ['/data/app/shop/base.apk']
        self.tool._verifier = lambda: SimpleNamespace(inspect=lambda apk: SimpleNamespace(
            package=name, split=False, signer_sha256=('b'*64,), sha256='c'*64))
        with self.assertRaisesRegex(ToolkitError, 'signer'):
            self.plan('helper-start', signer='a'*64)
        self.assertEqual({}, self.tool.adb.permission_flags)
        self.run_plan(self.plan('helper-start', signer='b'*64))
        self.assertEqual('true', self.tool.adb.permission_flags['android.permission.WRITE_SECURE_SETTINGS'])

    def test_helper_stop_checks_installed_signer_and_rechecks_reviewed_bytes_before_launch(self):
        name = 'org.firetools.adshelper'
        self.tool.adb.extra_apps[name] = ['/data/app/shop/base.apk']
        signer = 'b'*64
        info = SimpleNamespace(package=name, split=False, signer_sha256=(signer,), sha256='c'*64)
        self.tool._verifier = lambda: SimpleNamespace(inspect=lambda apk: info)
        with self.assertRaisesRegex(ToolkitError, 'signer'):
            self.plan('helper-stop', signer='a'*64)
        plan = self.plan('helper-stop', signer=signer)
        # Call the launch step directly to exercise a change after the plan
        # recheck: an update with the same signer must still match reviewed bytes.
        info.sha256 = 'd'*64
        original_hash = 'c'*64
        with self.assertRaisesRegex(ToolkitError, 'changed since preview'):
            self.tool._apply_device_step(plan, ['helper-open', original_hash], self.done)
        self.assertEqual([], self.tool.adb.writes)
        info.sha256 = original_hash
        self.run_plan(plan)
        self.assertEqual(['am', 'start', '--user', '0', '-n', name + '/.MainActivity'],
                         self.tool.adb.writes[-1])
        self.assertEqual({}, self.tool.adb.permission_flags)

    def test_accessibility_enable_opens_tablet_consent_and_disable_preserves_others(self):
        tablet = self.tool.adb
        component = 'org.example.shop/.Reader'
        tablet.services['org.example.shop'] = component
        tablet.settings['secure']['enabled_accessibility_services'] = 'example.other/.Service:'+component
        self.run_plan(self.plan('accessibility', component=component, enable='true'))
        self.assertEqual('android.settings.ACCESSIBILITY_SETTINGS', tablet.writes[-1][-1])
        self.run_plan(self.plan('accessibility', component=component, enable='false'))
        self.assertEqual('example.other/.Service', tablet.settings['secure']['enabled_accessibility_services'])

    def test_restore_supports_current_optional_catalog_and_excludes_core(self):
        tablet = self.tool.adb
        tablet.package_state.update({'com.amazon.weather': True, 'com.android.settings': True})
        path = self.host / 'pkg.json'
        self.run_plan(self.plan('package-backup', local=str(path)))
        tablet.package_state.update({'com.amazon.weather': False, 'com.android.settings': False})
        self.run_plan(self.plan('package-restore', local=str(path)))
        self.assertTrue(tablet.package_state['com.amazon.weather'])
        self.assertFalse(tablet.package_state['com.android.settings'])

    def test_remote_pull_ignores_success_exit_when_file_is_short(self):
        dest = self.host / 'download'
        plan = self.plan('pull', remote='/sdcard/Download/item.txt', local=str(dest))
        def truncated(serial, args, timeout=30):
            Path(args[2]).write_bytes(b'x')
        self.tool.adb._run_device = truncated
        with self.assertRaisesRegex(ToolkitError, 'size'):
            self.run_plan(plan)
        self.assertFalse(dest.exists())

    def test_export_identifies_firmware_specific_settings_omitted_from_restore(self):
        self.tool.adb.settings['system']['screen_off_timeout'] = '2147483647'
        dest = self.host / 'settings.json'
        plan = self.plan('settings-export', local=str(dest))
        self.assertIn('screen_off_timeout', ' '.join(plan.warnings))
        self.run_plan(plan)
        restore = self.plan('settings-import', local=str(dest))
        self.assertFalse(any('screen_off_timeout' in detail for detail in restore.details))

    def test_user_export_files_are_private_on_posix(self):
        import os
        if os.name != 'posix':
            self.skipTest('POSIX mode bits')
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)
        local = self.host / 'private.json'
        self.run_plan(self.plan('settings-export', local=str(local)))
        self.assertEqual(0, local.stat().st_mode & 0o077)

    def test_assistant_settings_can_restore_their_recorded_original(self):
        component = 'org.example.shop/.Reader'
        self.tool.adb.services['org.example.shop'] = component
        self.tool.adb.settings['secure']['assistant'] = 'example.other/.Old'
        self.run_plan(self.plan('assistant', component=component))
        self.run_plan(self.plan('setting-undo', namespace='secure', key='assistant'))
        self.assertEqual('example.other/.Old', self.tool.adb.settings['secure']['assistant'])

    def test_general_permission_cannot_grant_helper_privilege(self):
        helper = 'org.firetools.adshelper'
        self.tool.adb.package_state[helper] = True
        with self.assertRaisesRegex(ToolkitError, 'helper-start'):
            self.plan('grant', package=helper, permission='android.permission.WRITE_SECURE_SETTINGS')
        self.assertFalse(self.tool.adb.permission_flags)

    def test_owner_boundary_for_diagnostic_logs(self):
        self.tool.adb.info = replace(self.tool.adb.info, user_id=10)
        with self.assertRaises(ToolkitError):
            self.tool.read_device_tool(self.serial, 'logcat')

    def test_new_undo_never_follows_symlinked_state_directory(self):
        redirected = self.host / 'unexpected'
        redirected.mkdir()
        try:
            self.tool.state_dir.symlink_to(redirected, target_is_directory=True)
        except OSError:
            self.skipTest('symlink unavailable')
        with self.assertRaises((OSError, ToolkitError)):
            self.run_plan(self.plan('timeout', value='15000'))
        self.assertEqual([], list(redirected.iterdir()))
        self.assertEqual([], self.tool.adb.writes)

    def test_output_staging_keeps_original_parent_if_renamed(self):
        import os
        if os.name != 'posix':
            self.skipTest('POSIX directory rename fixture')
        from open_fire_toolkit.device_workflows import _destination
        folder, moved, other = (self.host / name for name in ('folder','moved','other'))
        folder.mkdir()
        other.mkdir()
        class StopStaging(Exception):
            pass
        with self.assertRaises(StopStaging):
            with _destination(str(folder/'data'), False) as staged:
                folder.rename(moved)
                folder.symlink_to(other, target_is_directory=True)
                # Even staging writes issued after an ancestor is replaced must
                # stay attached to the directory that was originally opened.
                staged.write_bytes(b'private')
                self.assertEqual([], list(other.iterdir()))
                raise StopStaging()
        self.assertEqual([], list(moved.iterdir()))

    def test_stale_permission_and_appop_previews_are_refused(self):
        tablet = self.tool.adb
        name = 'android.permission.CAMERA'
        tablet.permission_flags[name] = 'false'
        plan = self.plan('grant', package='org.example.shop', permission=name)
        tablet.permission_flags[name] = 'true'
        with self.assertRaisesRegex(ToolkitError, 'changed'):
            self.run_plan(plan)
        tablet.appops = 'ignore'
        op = self.plan('appops', package='org.example.shop', op='CAMERA', value='allow')
        tablet.appops = 'deny'
        with self.assertRaisesRegex(ToolkitError, 'changed'):
            self.run_plan(op)
        self.assertEqual('deny', tablet.appops)

    def test_permission_readback_disconnect_reports_accepted_grant(self):
        tablet = self.tool.adb
        perm = 'android.permission.CAMERA'
        tablet.permission_flags[perm] = 'false'
        original = tablet.shell
        def unplug(serial, args, timeout=30):
            if args[0] == 'dumpsys' and tablet.permission_flags[perm] == 'true':
                raise ToolkitError('disconnected')
            return original(serial, args, timeout)
        tablet.shell = unplug
        with self.assertRaisesRegex(ToolkitError, 'disconnected'):
            self.run_plan(self.plan('grant', package='org.example.shop', permission=perm))
        self.assertIn('accepted', self.done[-1].lower())
        self.assertIn(perm, self.done[-1])

    def test_push_cleanup_failure_reports_published_file(self):
        tablet = self.tool.adb
        source = self.host/'in'
        source.write_bytes(b'bytes')
        original = tablet.shell
        def cleanup_failed(serial, args, timeout=30):
            if args[0] == 'rmdir':
                raise ToolkitError('disconnected during cleanup')
            return original(serial, args, timeout)
        tablet.shell = cleanup_failed
        with self.assertRaisesRegex(ToolkitError, 'cleanup'):
            self.run_plan(self.plan('push', local=str(source), remote='/sdcard/Download/out'))
        self.assertIn('Published', self.done[-1])
        self.assertEqual(b'bytes', tablet.files['/storage/emulated/0/Download/out'])

    def test_shared_permission_executor_refuses_unverified_helper_grant(self):
        helper, permission = 'org.firetools.adshelper', 'android.permission.WRITE_SECURE_SETTINGS'
        unrelated = self.plan('timeout', value='15000')
        with self.assertRaisesRegex(ToolkitError, 'helper-start'):
            self.tool._permission_step(unrelated, 'grant', helper, permission, None, self.done)
        self.assertFalse(self.tool.adb.permission_flags)
        self.assertEqual([], self.done)

    def test_appop_and_display_readback_failures_report_accepted_command(self):
        tablet = self.tool.adb
        tablet.appops = 'deny'
        original = tablet.shell
        def disconnect(serial, args, timeout=30):
            if args[:3] == ['cmd','appops','get'] and tablet.appops == 'allow':
                raise ToolkitError('disconnected')
            if args == ['wm','density'] and tablet.overrides.get('density') == '300':
                raise ToolkitError('disconnected')
            return original(serial, args, timeout)
        tablet.shell = disconnect
        cases = [('display', {'density':'300'}), ('appops', {'op':'CAMERA','value':'allow','package':'org.example.shop'})]
        for op, params in cases:
            with self.subTest(operation=op), self.assertRaisesRegex(ToolkitError, 'disconnected'):
                self.run_plan(self.plan(op, **params))
            self.assertIn('accepted', self.done[-1])

    def test_unreported_owner_state_disclosed_in_permission_preview(self):
        plan = self.plan('grant', package='org.example.shop', permission='android.permission.CAMERA')
        self.assertIn('prior state', ' '.join(plan.warnings))
        self.assertIn('unavailable', ' '.join(plan.details))

    def test_child_process_can_receive_file_at_pinned_staging_path(self):
        import os
        import subprocess
        import sys
        from open_fire_toolkit.device_workflows import _destination
        if os.name != 'posix' or not Path('/proc/self/fd').exists():
            self.skipTest('Linux child-process file descriptor path')
        target = self.host/'subprocess-output'
        with _destination(str(target), False) as stage:
            subprocess.run([sys.executable, '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b"content")',
                            str(stage)], check=True, close_fds=True)
        self.assertEqual(b'content', target.read_bytes())

    def test_staging_name_replacement_preserves_the_replacement_directory(self):
        import os
        from open_fire_toolkit.device_workflows import _pinned_directory, _private_stage
        if os.name != 'posix':
            self.skipTest('Windows denies the concurrent rename')
        parent = self.host/'shared'
        parent.mkdir()
        with _pinned_directory(parent) as held:
            with _private_stage(held) as stage:
                entry, = parent.iterdir()
                (stage/'snapshot').write_text('ours')
                entry.rename(parent/'moved-stage')
                entry.mkdir()
                (entry/'snapshot').write_text('someone else')
                (entry/'subfolder').mkdir()
                (entry/'subfolder'/'keep').write_text('unrelated')
        self.assertEqual('someone else', (entry/'snapshot').read_text())
        self.assertEqual('unrelated', (entry/'subfolder'/'keep').read_text())

    def test_changed_uid_appop_refused_even_when_package_line_is_unchanged(self):
        tablet = self.tool.adb
        original = tablet.shell
        for package_line in ('', '\nCAMERA: deny'):
            with self.subTest(package_line=package_line):
                modes = {'uid':'foreground', 'writes':0}
                def appop(serial, args, timeout=30):
                    if args[:3] == ['cmd','appops','get']:
                        return 'Uid mode: CAMERA: ' + modes['uid'] + package_line
                    if args[:3] == ['cmd','appops','set']:
                        modes['writes'] += 1
                        return ''
                    return original(serial, args, timeout)
                tablet.shell = appop
                plan = self.plan('appops', package='org.example.shop', op='CAMERA', value='allow')
                modes['uid'] = 'allow'
                with self.assertRaisesRegex(ToolkitError, 'changed'):
                    self.run_plan(plan)
                self.assertEqual(0, modes['writes'])
                self.assertIn('foreground', ' '.join(plan.details))

    def test_appop_readback_conflict_between_uid_and_package_is_reported(self):
        tablet = self.tool.adb
        original = tablet.shell
        package_mode = ['deny']
        def appop(serial, args, timeout=30):
            if args[:3] == ['cmd','appops','get']:
                return 'Uid mode: CAMERA: foreground\nCAMERA: ' + package_mode[0]
            if args[:3] == ['cmd','appops','set']:
                package_mode[0] = args[-1]
                return ''
            return original(serial, args, timeout)
        tablet.shell = appop
        plan = self.plan('appops', package='org.example.shop', op='CAMERA', value='allow')
        with self.assertRaisesRegex(ToolkitError, '(UID|uid).*foreground'):
            self.run_plan(plan)
        self.assertIn('accepted', self.done[-1])
