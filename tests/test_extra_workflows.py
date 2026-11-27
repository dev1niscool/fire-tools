"""Exercise settings, transport, and storage workflows without a live tablet."""
from dataclasses import replace
import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import threading
import unittest
from unittest.mock import patch

from open_fire_toolkit.adb import AdbError, DeviceInfo
from open_fire_toolkit.device_workflows import DeviceWorkflows
from open_fire_toolkit.extra_workflows import ExtraWorkflows
from open_fire_toolkit.feature_catalog import BY_KEY, feature_values, run_feature
from open_fire_toolkit.service import Toolkit, ToolkitError


class Tablet:
    def __init__(self):
        self.device = DeviceInfo('fire-test', 'Fire Test', 'Amazon', '8', '11', 30, ('arm64-v8a',), 0)
        self.installed = ['com.example.home', 'com.google.android.gms']
        self.commands = []
        self.writes = []
        self.whitelist = set()
        self.widget_grants = set()
        self.widget_dump_available = True
        self.setting_values = {}
        self.restrict_background = False
        self.metered = {'Home; Wi-Fi': 'none'}
        self.paths = {
            '/storage/emulated/0': ('directory', '1|9|41ed|0|2024-04-02 00:00:00.000000000|2024-04-02 00:00:00.000000000'),
            '/storage/emulated/0/Report.txt': ('regular file', '1|12|81a4|4|2024-04-02 00:00:01.000000000|2024-04-02 00:00:01.000000000'),
        }
        self.connect_reply = ''
        self.transport_stderr = ''
        self.launch_reply = 'Starting: Intent { act=android.settings.ADD_ACCOUNT_SETTINGS }'
        self.ignore_wifi_write = False
        self.switch_after_setting_write = False
        self.missing_device = False

    def info(self, serial):
        if self.missing_device:
            raise AdbError('No attached tablets.')
        assert serial == self.device.serial
        return self.device

    def packages(self, serial):
        assert serial == self.device.serial
        return list(self.installed)

    def shell(self, serial, args, timeout=30):
        assert serial == self.device.serial
        args = tuple(args)
        self.commands.append(args)
        if args[:5] == ('settings', '--user', '0', 'list', 'global'):
            return '\n'.join(f'{key}={value}' for key, value in sorted(self.setting_values.items()))
        if args[:3] == ('settings', '--user', '0'):
            _, _, _, verb, namespace, key, *values = args
            assert namespace == 'global'
            self.writes.append(args)
            if verb == 'put':
                self.setting_values[key] = values.pop()
            elif verb == 'delete':
                self.setting_values.pop(key, None)
            else:
                raise AssertionError(args)
            if self.switch_after_setting_write:
                self.device = replace(self.device, user_id=12)
            return ''
        if args[:3] == ('cmd', 'deviceidle', 'whitelist'):
            if len(args) == 3:
                return '\n'.join('user,' + package + ',10151' for package in sorted(self.whitelist))
            self.writes.append(args)
            marker, package = args[3][0], args[3][1:]
            if marker == '+':
                self.whitelist.add(package)
            elif marker == '-':
                self.whitelist.discard(package)
            else:
                raise AssertionError(args)
            return ''
        if args == ('dumpsys', 'appwidget'):
            if not self.widget_dump_available:
                raise AdbError('Permission Denial: cannot dump appwidget')
            grants = [f'  [{i}] user=0 package={package}' for i, package in enumerate(self.widget_grants)]
            return '\n'.join(['Providers:', 'Widgets:', 'Hosts:', 'Grants:', *grants])
        if args[:1] == ('appwidget',):
            assert args[2] == '--package' and args[4:] == ('--user', '0')
            self.writes.append(args)
            if args[1] == 'grantbind':
                self.widget_grants.add(args[3])
            elif args[1] == 'revokebind':
                self.widget_grants.discard(args[3])
            else:
                raise AssertionError(args)
            return ''
        if args[:4] == ('am', 'start', '--user', '0'):
            self.writes.append(args)
            return self.launch_reply
        if args == ('cmd', 'netpolicy', 'get', 'restrict-background'):
            return 'Restrict background status: ' + ('enabled' if self.restrict_background else 'disabled')
        if args == ('cmd', 'netpolicy', 'list', 'wifi-networks'):
            return '\n'.join(f'{key};{value}' for key, value in self.metered.items())
        if args[:4] == ('cmd', 'netpolicy', 'set', 'restrict-background'):
            self.writes.append(args)
            self.restrict_background = args[4] == 'true'
            return ''
        if args[:4] == ('cmd', 'netpolicy', 'set', 'metered-network'):
            self.writes.append(args)
            if not self.ignore_wifi_write:
                self.metered[args[4]] = 'none' if args[5] == 'undefined' else args[5]
            raise AdbError('ADB exited with status 255.')
        if args[0] == 'realpath':
            if args[1] in self.paths:
                return args[1]
            raise AdbError('No such file')
        if args[:2] == ('stat', '-c'):
            kind, metadata = self.paths[args[3]]
            if args[2] == '%d:%i:%f:%s:%Y:%Z':
                identity = metadata.split('|')[:4]
                return ':'.join([*identity, '1712000001', '1712000001'])
            return {'%F': kind, '%d|%i|%f|%s|%y|%z': metadata}[args[2]]
        if args[:2] == ('test', '!'):
            if args[2] == '-e' and args[3] in self.paths:
                raise AdbError('ADB exited with status 1.')
            return ''
        if args[0] == 'mkdir':
            self.writes.append(args)
            self.paths[args[-1]] = ('directory', '1|13|41ed|0|2024-04-02 00:00:10.000000000|2024-04-02 00:00:10.000000000')
            return ''
        if args[:2] == ('mv', '-nT'):
            self.writes.append(args)
            if args[-1] not in self.paths:
                self.paths[args[-1]] = self.paths.pop(args[-2])
            return ''
        if args[0] == 'rm':
            self.writes.append(args)
            del self.paths[args[-1]]
            return ''
        raise AssertionError(args)

    def _run(self, args, timeout=30):
        args = tuple(args)
        assert args[0] in ('connect', 'disconnect') and len(args) == 2
        self.writes.append(args)
        return CompletedProcess(args, 0, self.connect_reply, self.transport_stderr)

    def _run_device(self, serial, args, timeout=30):
        assert serial == self.device.serial
        args = tuple(args)
        self.writes.append((serial, *args))
        if args[0] == 'tcpip':
            return CompletedProcess(args, 0, f'restarting in TCP mode port: {args[1]}\n', '')
        if args == ('usb',):
            return CompletedProcess(args, 0, 'restarting in USB mode\n', '')
        raise AssertionError(args)


class Harness(DeviceWorkflows, ExtraWorkflows):
    def _owner_device(self, serial):
        return self._writable_device(serial)

    def _writable_device(self, serial):
        device = self.adb.info(serial)
        if device.user_id != 0 or device.manufacturer != 'Amazon':
            raise ToolkitError('Select an Amazon owner profile.')
        return device


class ExtraWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tablet = Tablet()
        self.tool = Harness()
        self.tool.adb = self.tablet
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tool.state_dir = Path(tmp.name) / 'state'
        self.serial = self.tablet.device.serial

    def plan(self, operation, **params):
        return self.tool.plan_extra_action(self.serial, operation, **params)

    def run_plan(self, plan):
        done = []
        if plan.action == 'transport':
            self.tool._execute_transport(plan, done, lambda _: None)
        else:
            self.tool._execute_extra_workflow(plan, done, lambda _: None)
        return '\n'.join(done)

    def test_settings_open_requests_google_accounts_without_host_credentials(self):
        plan = self.plan('settings-open', target='google-account-add')
        self.assertEqual([], self.tablet.writes)
        result = self.run_plan(plan)
        self.assertIn('requested', result.lower())
        self.assertEqual([
            ('am', 'start', '--user', '0', '-a', 'android.settings.ADD_ACCOUNT_SETTINGS',
             '--esa', 'account_types', 'com.google')
        ], self.tablet.writes)

    def test_settings_open_reports_unresolved_activity(self):
        plan = self.plan('settings-open', target='app-details', package='com.example.home')
        self.tablet.launch_reply = 'Starting: Intent {...}\nError: Activity not started, unable to resolve Intent'
        with self.assertRaisesRegex(ToolkitError, 'error|Error'):
            self.run_plan(plan)

    def test_feature_forms_allow_unused_blank_optional_fields(self):
        settings = BY_KEY['settings-open']
        dns = BY_KEY['private-dns']
        first = run_feature(self.tool, self.serial, settings, feature_values(settings, []))
        second = run_feature(self.tool, self.serial, dns, feature_values(dns, ['mode=off']))
        self.assertEqual({'target': 'accounts'}, first.params)
        self.assertEqual({'mode': 'off'}, second.params)
        self.assertEqual([], self.tablet.writes)

    def test_battery_exemption_defaults_to_play_services_and_reads_back(self):
        plan = self.plan('battery-exemption', enabled=True)
        self.assertTrue(any('battery' in warning.lower() for warning in plan.warnings))
        self.assertRegex(self.run_plan(plan), 'verified|read back')
        self.assertEqual({'com.google.android.gms'}, self.tablet.whitelist)
        self.run_plan(self.plan('battery-exemption', enabled=False))
        self.assertEqual(set(), self.tablet.whitelist)

    def test_widget_readback_only_claimed_if_available(self):
        plan = self.plan('widget-bind', package='com.example.home', enabled=True)
        self.assertTrue(any('widget' in warning.lower() and 'read' in warning.lower() for warning in plan.warnings))
        self.assertRegex(self.run_plan(plan), 'verified|read back')
        self.tablet.widget_dump_available = False
        plan = self.plan('widget-bind', package='com.example.home', enabled=False)
        self.assertIn('accepted', self.run_plan(plan).lower())
        self.assertEqual(set(), self.tablet.widget_grants)

    def test_wireless_connect_requires_recognized_connection_response(self):
        self.tablet.missing_device = True
        plan = self.tool.plan_extra_action('', 'wireless-connect', endpoint='192.168.1.14:5555')
        self.assertEqual('', plan.serial)
        self.tablet.connect_reply = 'failed to connect to 192.168.1.14:5555: Connection refused'
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.tablet.connect_reply = 'already connected to 192.168.1.14:5555'
        self.assertIn('transport', self.run_plan(plan).lower())
        self.assertEqual([('connect', '192.168.1.14:5555')] * 2, self.tablet.writes)

    def test_usb_and_tcp_mode_are_scoped_to_reviewed_serial(self):
        self.run_plan(self.plan('wireless-enable'))
        self.run_plan(self.plan('wireless-usb'))
        self.assertEqual([(self.serial, 'tcpip', '5555'), (self.serial, 'usb')], self.tablet.writes)

    def test_wireless_connect_accepts_local_daemon_startup_messages(self):
        self.tablet.missing_device = True
        plan = self.tool.plan_extra_action('', 'wireless-connect', endpoint='fire-tablet.local:5555')
        self.tablet.connect_reply = 'connected to fire-tablet.local:5555'
        self.tablet.transport_stderr = ('* daemon not running; starting now at tcp:localhost:5037\n'
                                        '* daemon started successfully\n')
        self.assertIn('connected', self.run_plan(plan))
        self.tablet.transport_stderr += 'error: transport failed\n'
        with self.assertRaisesRegex(ToolkitError, 'transport failed'):
            self.run_plan(plan)

    def test_wireless_disconnect_requires_matching_endpoint_response(self):
        self.tablet.missing_device = True
        plan = self.tool.plan_extra_action('', 'wireless-disconnect', endpoint='fire-tablet.local:5555')
        self.tablet.connect_reply = 'disconnected fire-tablet.local:5556'
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.tablet.connect_reply = 'disconnected fire-tablet.local:5555'
        self.assertIn('disconnected', self.run_plan(plan).lower())
        self.assertEqual([('disconnect', 'fire-tablet.local:5555')] * 2, self.tablet.writes)

    def test_adb_reserved_transport_labels_are_refused_during_preview(self):
        for operation in ('wireless-connect', 'wireless-disconnect'):
            for endpoint in ('EmU:5555', 'vsock:5555', 'localfilesystem:5555', 'tcp:5555', 'acceptfd:5555',
                             'local:5555', 'localabstract:5555', 'localreserved:5555'):
                with self.subTest(operation=operation, endpoint=endpoint), self.assertRaises(ToolkitError):
                    self.tool.plan_extra_action('', operation, endpoint=endpoint)
        benign = self.tool.plan_extra_action('', 'wireless-connect', endpoint='emu.lab.example:5555')
        self.assertEqual('emu.lab.example:5555', benign.params['endpoint'])
        self.assertEqual([], self.tablet.writes)

    def test_host_transport_refuses_operations_other_than_connect_or_disconnect(self):
        plan = self.plan('wireless-connect', endpoint='fire-tablet.local:5555')
        forged = replace(plan, operation='wireless-enable')
        with self.assertRaises(ToolkitError):
            self.tool._execute_transport(forged, [], lambda _: None)
        self.assertEqual([], self.tablet.writes)

    def test_invalid_paths_ports_settings_and_endpoints_do_not_write(self):
        cases = [
            ('settings-open', dict(target='android.settings.SETTINGS')),
            ('settings-open', dict(target='app-details')),
            ('settings-open', dict(target='app-details', package='com.example.home; reboot')),
            ('wireless-enable', dict(port='65536')),
            ('wireless-connect', dict(endpoint='--help:5555')),
            ('wireless-connect', dict(endpoint='999.0.0.1:5555')),
            ('wireless-connect', dict(endpoint='fire.local:5555\necho')),
            ('file-delete', dict(remote='/sdcard')),
            ('file-delete', dict(remote='/sdcard/../data/example')),
            ('file-delete', dict(remote='/sdcard/-rf')),
            ('file-delete', dict(remote='/sdcard/Report.txt\u009b')),
            ('file-delete', dict(remote='/sdcard/Report.txt/')),
            ('file-delete', dict(remote='/data/report')),
            ('private-dns', dict(mode='hostname', hostname='8.8.8.8')),
            ('data-saver', dict(enabled='yes')),
        ]
        for operation, values in cases:
            with self.subTest(operation=operation, values=values), self.assertRaises(ToolkitError):
                self.plan(operation, **values)
        self.assertEqual([], self.tablet.writes)

    def test_file_tools_keep_storage_arguments_literal(self):
        self.run_plan(self.plan('file-mkdir', remote='/sdcard/My files'))
        new_path = '/storage/emulated/0/My files/$(reboot).txt'
        self.run_plan(self.plan('file-rename', remote='/sdcard/Report.txt',
                                destination='/sdcard/My files/$(reboot).txt'))
        self.assertIn(new_path, self.tablet.paths)
        plan = self.plan('file-delete', remote='/sdcard/My files/$(reboot).txt')
        self.assertTrue(any('permanent' in warning.lower() for warning in plan.warnings))
        self.run_plan(plan)
        self.assertNotIn(new_path, self.tablet.paths)
        self.assertEqual(('rm', new_path), self.tablet.writes[-1])

    def test_file_delete_refuses_directories_and_changed_source(self):
        path = '/storage/emulated/0/Report.txt'
        plan = self.plan('file-delete', remote='/sdcard/Report.txt')
        self.tablet.paths[path] = ('regular file', '1|12|81a4|4|2024-04-02 00:00:01.000000001|2024-04-02 00:00:01.000000001')
        with self.assertRaisesRegex(ToolkitError, 'changed'):
            self.run_plan(plan)
        self.tablet.paths[path] = ('directory', '1|88|41ed|0|2024-04-02 00:00:01.000000000|2024-04-02 00:00:01.000000000')
        with self.assertRaisesRegex(ToolkitError, 'file'):
            self.plan('file-delete', remote='/sdcard/Report.txt')
        self.assertEqual([], self.tablet.writes)

    def test_rename_refuses_destination_created_after_preview(self):
        plan = self.plan('file-rename', remote='/sdcard/Report.txt', destination='/sdcard/New.txt')
        self.tablet.paths['/storage/emulated/0/New.txt'] = (
            'regular empty file', '1|15|81a4|0|2024-04-02 00:00:10.000000000|2024-04-02 00:00:10.000000000')
        with self.assertRaises((AdbError, ToolkitError)):
            self.run_plan(plan)
        self.assertEqual([], self.tablet.writes)

    def test_post_write_disconnect_reports_accepted_targets(self):
        cases = (
            ('file-mkdir', dict(remote='/sdcard/Work'), ('mkdir',), '/sdcard/Work', 'accepted'),
            ('file-delete', dict(remote='/sdcard/Report.txt'), ('rm',), '/sdcard/Report.txt', 'accepted'),
            ('file-rename', dict(remote='/sdcard/Report.txt', destination='/sdcard/New.txt'), ('mv',),
             '/sdcard/New.txt', 'accepted'),
            ('battery-exemption', dict(enabled=True), ('cmd', 'deviceidle', 'whitelist', '+com.google.android.gms'),
             'com.google.android.gms', 'accepted'),
            ('widget-bind', dict(enabled=True, package='com.example.home'), ('appwidget', 'grantbind'),
             'com.example.home', 'accepted'),
            ('data-saver', dict(enabled=True), ('cmd', 'netpolicy', 'set', 'restrict-background'),
             'Data Saver', 'accepted'),
            ('wifi-metered', dict(network_id='Home; Wi-Fi', metered='true'),
             ('cmd', 'netpolicy', 'set', 'metered-network'), 'Home; Wi-Fi', 'unverified'),
            ('private-dns', dict(mode='hostname', hostname='resolver.example.com'),
             ('settings', '--user', '0', 'put'), 'private_dns_specifier', 'accepted'),
        )
        for operation, parameters, prefix, subject, status in cases:
            with self.subTest(operation=operation):
                toolkit = Toolkit.__new__(Toolkit)
                toolkit.adb = Tablet()
                toolkit.state_dir = self.tool.state_dir
                toolkit._operation_lock = threading.Lock()
                plan = toolkit.plan_extra_action(self.serial, operation, **parameters)
                shell = toolkit.adb.shell

                def disconnect_after_command(serial, args, timeout=30):
                    try:
                        return shell(serial, args, timeout)
                    finally:
                        if tuple(args[:len(prefix)]) == prefix:
                            toolkit.adb.missing_device = True

                with patch.object(toolkit.adb, 'shell', side_effect=disconnect_after_command):
                    with self.assertRaises(ToolkitError) as error:
                        toolkit.execute(plan, confirmed=True, log=lambda _: None)
                self.assertIn('No attached tablets', str(error.exception))
                self.assertIn(subject, str(error.exception))
                self.assertIn(status, str(error.exception).lower())
                self.assertNotIn('verified.', str(error.exception).replace('unverified.', ''))

    def test_source_catalog_has_first_party_links_and_needs_no_device(self):
        result = self.tool.read_extra_tool('', 'source-catalog')
        self.assertIn('https://f-droid.org/', result)
        self.assertIn('org.videolan.vlc', result)
        self.assertIn('com.netflix.mediaclient', result)
        self.assertIn('com.disney.disneyplus', result)
        self.assertEqual([], self.tablet.commands)

    def test_private_dns_saves_and_restores_both_original_settings(self):
        self.tablet.setting_values['private_dns_mode'] = 'off'
        plan = self.plan('private-dns', mode='hostname', hostname='resolver.example.com')
        self.assertFalse(self.tool.state_dir.exists())
        self.run_plan(plan)
        self.assertEqual({'private_dns_mode': 'hostname', 'private_dns_specifier': 'resolver.example.com'},
                         self.tablet.setting_values)
        self.run_plan(self.plan('private-dns-undo'))
        self.assertEqual({'private_dns_mode': 'off'}, self.tablet.setting_values)
        with self.assertRaisesRegex(ToolkitError, 'saved|undo'):
            self.plan('private-dns-undo')

    def test_private_dns_stops_if_profile_changes_between_writes(self):
        plan = self.plan('private-dns', mode='hostname', hostname='resolver.example.com')
        self.tablet.switch_after_setting_write = True
        with self.assertRaises(ToolkitError):
            self.run_plan(plan)
        self.assertEqual(1, len(self.tablet.writes))
        self.tablet.switch_after_setting_write = False
        self.tablet.device = replace(self.tablet.device, user_id=0)
        self.run_plan(self.plan('private-dns-undo'))
        self.assertEqual({}, self.tablet.setting_values)

    def test_private_dns_refuses_a_linked_directory_before_its_first_save(self):
        folder = self.tool.state_dir
        outside = folder.with_name('outside')
        outside.mkdir()
        try:
            folder.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('host cannot create directory symlinks')
        with self.assertRaises((ToolkitError, OSError)):
            self.plan('private-dns', mode='off')
        self.assertEqual([], self.tablet.writes)
        self.assertEqual([], list(outside.iterdir()))

    @unittest.skipUnless(os.name == 'posix', 'directory rename fixture requires POSIX')
    def test_private_dns_journal_publish_stays_in_original_directory(self):
        folder = self.tool.state_dir
        moved, outside = (folder.with_name(name) for name in ('moved', 'outside'))
        folder.mkdir()
        outside.mkdir()
        plan = self.plan('private-dns', mode='off')
        real_replace, real_link, real_rename = os.replace, os.link, os.rename

        def redirect_before_publish(operation, source, destination, *args, **kwargs):
            real_rename(folder, moved)
            folder.symlink_to(outside, target_is_directory=True)
            operation(source, destination, *args, **kwargs)

        with (
            patch.object(os, 'replace', side_effect=lambda *args, **kwargs:
                         redirect_before_publish(real_replace, *args, **kwargs)),
            patch.object(os, 'link', side_effect=lambda *args, **kwargs:
                         redirect_before_publish(real_link, *args, **kwargs)),
        ):
            with self.assertRaisesRegex(ToolkitError, 'directory changed'):
                self.run_plan(plan)
        self.assertEqual([], self.tablet.writes)
        self.assertEqual([], list(outside.iterdir()))
        self.assertEqual(1, len(list(moved.glob('private-dns-*.json'))))
        self.assertEqual(folder, self.tool.state_dir)

    def test_private_dns_first_publish_does_not_overwrite_an_intervening_entry(self):
        plan = self.plan('private-dns', mode='off')
        real_replace, real_link, real_rename = os.replace, os.link, os.rename

        def create_entry_before_publish(operation, source, destination, *args, **kwargs):
            with Path(destination).open('x') as entry:
                entry.write('intervening journal')
            operation(source, destination, *args, **kwargs)

        with (
            patch.object(os, 'replace', side_effect=lambda *args, **kwargs:
                         create_entry_before_publish(real_replace, *args, **kwargs)),
            patch.object(os, 'link', side_effect=lambda *args, **kwargs:
                         create_entry_before_publish(real_link, *args, **kwargs)),
            patch.object(os, 'rename', side_effect=lambda *args, **kwargs:
                         create_entry_before_publish(real_rename, *args, **kwargs)),
        ):
            with self.assertRaisesRegex(ToolkitError, 'journal.*appeared'):
                self.run_plan(plan)
        journal, = self.tool.state_dir.glob('private-dns-*.json')
        self.assertEqual('intervening journal', journal.read_text())
        self.assertEqual([], self.tablet.writes)

    def test_private_dns_refuses_the_second_write_if_journal_contents_change(self):
        plan = self.plan('private-dns', mode='hostname', hostname='resolver.example.com')
        shell = self.tablet.shell

        def replace_values_after_write(serial, args, timeout=30):
            result = shell(serial, args, timeout)
            if tuple(args[:6]) == ('settings', '--user', '0', 'put', 'global', 'private_dns_specifier'):
                journal, = self.tool.state_dir.glob('private-dns-*.json')
                document = json.loads(journal.read_text())
                document['values']['private_dns_mode'] = 'off'
                journal.write_text(json.dumps(document))
            return result

        with patch.object(self.tablet, 'shell', side_effect=replace_values_after_write):
            with self.assertRaisesRegex(ToolkitError, 'journal changed'):
                self.run_plan(plan)
        self.assertEqual({'private_dns_specifier': 'resolver.example.com'}, self.tablet.setting_values)
        journal, = self.tool.state_dir.glob('private-dns-*.json')
        self.assertEqual('off', json.loads(journal.read_text())['values']['private_dns_mode'])

    def test_private_dns_undo_preserves_a_same_content_replacement_journal(self):
        self.run_plan(self.plan('private-dns', mode='off'))
        journal, = self.tool.state_dir.glob('private-dns-*.json')
        original = journal.read_bytes()
        plan = self.plan('private-dns-undo')
        shell = self.tablet.shell

        def replace_journal_after_write(serial, args, timeout=30):
            result = shell(serial, args, timeout)
            if tuple(args[:4]) == ('settings', '--user', '0', 'delete'):
                replacement = journal.with_suffix('.replacement')
                replacement.write_bytes(original)
                replacement.replace(journal)
            return result

        with patch.object(self.tablet, 'shell', side_effect=replace_journal_after_write):
            with self.assertRaisesRegex(ToolkitError, 'journal changed'):
                self.run_plan(plan)
        self.assertEqual(original, journal.read_bytes())
        self.assertEqual({}, self.tablet.setting_values)

    def test_private_dns_undo_preserves_unrecognized_entry_arriving_during_consumption(self):
        self.run_plan(self.plan('private-dns', mode='off'))
        journal, = self.tool.state_dir.glob('private-dns-*.json')
        plan = self.plan('private-dns-undo')
        real_rename = os.rename
        real_unlink = Path.unlink

        def replace_before_consuming(source):
            if journal.exists() and os.path.samefile(source, journal):
                journal.write_text('unrecognized replacement')

        def before_move(source, destination, *args, **kwargs):
            replace_before_consuming(source)
            return real_rename(source, destination, *args, **kwargs)

        def before_unlink(path, *args, **kwargs):
            replace_before_consuming(path)
            return real_unlink(path, *args, **kwargs)

        with patch.object(os, 'rename', side_effect=before_move), patch.object(Path, 'unlink', new=before_unlink):
            with self.assertRaisesRegex(ToolkitError, 'journal changed'):
                self.run_plan(plan)
        self.assertEqual('unrecognized replacement', journal.read_text())
        self.assertEqual({}, self.tablet.setting_values)

    def test_private_dns_no_write_undo_keeps_journal_when_tablet_drifts(self):
        self.run_plan(self.plan('private-dns', mode='off'))
        self.tablet.setting_values.clear()
        plan = self.plan('private-dns-undo')
        guard = self.tool._device_guard

        def drift_after_execution_preview(preview):
            guard(preview)
            self.tablet.setting_values['private_dns_mode'] = 'off'

        with patch.object(self.tool, '_device_guard', side_effect=drift_after_execution_preview):
            with self.assertRaisesRegex(ToolkitError, 'settings changed'):
                self.run_plan(plan)
        self.assertEqual(1, len(self.tablet.writes))
        self.assertEqual(1, len(list(self.tool.state_dir.glob('private-dns-*.json'))))

    @unittest.skipUnless(os.name == 'posix', 'directory rename fixture requires POSIX')
    def test_private_dns_undo_delete_stays_in_original_directory(self):
        folder = self.tool.state_dir
        moved, outside = (folder.with_name(name) for name in ('moved', 'outside'))
        outside.mkdir()
        self.run_plan(self.plan('private-dns', mode='off'))
        journal, = folder.glob('private-dns-*.json')
        other = outside / journal.name
        other.write_text('outside journal')
        plan = self.plan('private-dns-undo')
        real_unlink = Path.unlink

        def redirect_before_unlink(path):
            folder.rename(moved)
            folder.symlink_to(outside, target_is_directory=True)
            real_unlink(path)

        with patch.object(Path, 'unlink', new=redirect_before_unlink):
            self.run_plan(plan)
        self.assertEqual('outside journal', other.read_text())
        self.assertEqual([], list(moved.iterdir()))
        self.assertEqual({}, self.tablet.setting_values)

    def test_network_commands_read_back_expected_values(self):
        self.run_plan(self.plan('data-saver', enabled=True))
        self.run_plan(self.plan('wifi-metered', network_id='Home; Wi-Fi', metered='true'))
        result = self.tool.read_extra_tool(self.serial, 'network-info')
        self.assertIn('enabled', result)
        self.assertIn('Home; Wi-Fi;true', result)
        self.run_plan(self.plan('wifi-metered', network_id='Home; Wi-Fi', metered='undefined'))
        self.assertEqual('none', self.tablet.metered['Home; Wi-Fi'])

    def test_wifi_metered_exit_code_alone_is_not_success(self):
        plan = self.plan('wifi-metered', network_id='Home; Wi-Fi', metered='true')
        self.tablet.ignore_wifi_write = True
        with self.assertRaisesRegex(ToolkitError, 'confirm|verify'):
            self.run_plan(plan)


if __name__ == '__main__':
    unittest.main()
