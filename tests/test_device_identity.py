import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from open_fire_toolkit.service import ToolConfig, Toolkit, ToolkitError


class PhysicalIdentityTests(unittest.TestCase):
    endpoint = '192.168.1.16:5555'
    usb_serial = 'G123456789ABCDEF'

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        adb = self.root / 'adb'
        adb.touch()
        self.tool = Toolkit(ToolConfig(str(adb)), self.root / 'state')
        self.boot_serial = self.usb_serial
        self.fallback_serial = ''
        self.ad_value = '1'
        self.writes = []
        self.enterContext(patch.object(self.tool.adb, 'shell', self.shell))
        self.enterContext(patch.object(self.tool.adb, '_run', side_effect=self.run_adb))

    def run_adb(self, args):
        if list(args) == ['devices', '-l']:
            return CompletedProcess(args, 0, f'List of devices attached\n{self.endpoint} device transport_id:21\n', '')
        raise AssertionError(args)

    def shell(self, serial, args, timeout=30):
        args = tuple(args)
        if args == ('getprop',):
            return '\n'.join((
                '[ro.product.model]: [KFTEST]',
                '[ro.product.manufacturer]: [Amazon]',
                '[ro.build.version.sdk]: [30]',
                f'[ro.boot.serialno]: [{self.boot_serial}]',
                f'[ro.serialno]: [{self.fallback_serial}]',
            ))
        if args == ('am', 'get-current-user'):
            return '0'
        if args == ('pm', 'list', 'users'):
            return 'UserInfo{0:Owner}'
        if args[:5] == ('pm', 'list', 'packages', '--user', '0'):
            return '' if '-d' in args else 'package:com.amazon.mp3'
        if args[:4] == ('settings', '--user', '0', 'list'):
            return ''
        if args == ('settings', '--user', '0', 'get', 'global', 'LOCKSCREEN_AD_ENABLED'):
            return self.ad_value
        if args[:4] == ('settings', '--user', '0', 'put'):
            self.ad_value = args[-1]
            self.writes.append(args)
            return ''
        raise AssertionError(args)

    def test_reused_endpoint_cannot_apply_reviewed_change(self):
        plan = self.tool.plan_ads(self.endpoint)
        self.boot_serial = 'G987654321ABCDEF'
        with self.assertRaises(ToolkitError):
            self.tool.execute(plan, confirmed=True)
        self.assertEqual(self.writes, [])

    def test_network_requires_identity_for_changes_but_still_reads(self):
        for endpoint in (self.endpoint, 'adb-Test-123._adb-tls-connect._tcp', 'adb-Test-123'):
            for value in ('', 'unknown', '0000000000000000', '0123456789ABCDEF', self.endpoint):
                with self.subTest(endpoint=endpoint, value=value):
                    self.boot_serial = value
                    self.assertEqual(self.tool.read_device_tool(endpoint, 'users'), 'UserInfo{0:Owner}')
                    with self.assertRaises(ToolkitError):
                        self.tool.plan_ads(endpoint)

    def test_same_tablet_reuses_usb_snapshot_and_saved_ad_state_over_wifi(self):
        snapshot = self.root / 'packages.json'
        self.tool.execute(self.tool.plan_device_action(
            self.usb_serial, 'package-backup', local=str(snapshot)), True, log=lambda _: None)
        self.assertNotIn(self.usb_serial, snapshot.read_text())
        self.assertIn(hashlib.sha256(self.usb_serial.encode()).hexdigest(), snapshot.read_text())
        self.tool.execute(self.tool.plan_ads(self.usb_serial), True, log=lambda _: None)
        self.boot_serial, self.fallback_serial = '', self.usb_serial
        self.tool.plan_device_action(self.endpoint, 'package-restore', local=str(snapshot))
        self.tool.execute(self.tool.plan_ads(self.endpoint, restore=True), True, log=lambda _: None)
        self.assertEqual(self.ad_value, '1')
        self.fallback_serial = 'G987654321ABCDEF'
        with self.assertRaises(ToolkitError):
            self.tool.plan_device_action(self.endpoint, 'package-restore', local=str(snapshot))

    def test_historical_usb_journals_require_same_tablet_on_wifi(self):
        digest = hashlib.sha256(self.usb_serial.encode()).hexdigest()
        identity = {'serial_sha256': digest, 'sdk': 30, 'model': 'KFTEST'}
        records = {
            'packages-state.json': {'schema': 1, 'devices': {
                digest: {'model': 'KFTEST', 'states': {'com.amazon.mp3': 'enabled'}}}},
            f'device-settings-{digest}.json': {
                'schema': 'fire-tools.setting-undo.v1', 'device': identity,
                'values': {'system/font_scale': '1.0'}},
            f'private-dns-{digest}.json': {
                'schema': 'fire-tools.private-dns-undo.v1', 'device': identity,
                'values': {'private_dns_mode': 'opportunistic', 'private_dns_specifier': None}},
        }
        self.tool.state_dir.mkdir()
        for name, contents in records.items():
            (self.tool.state_dir / name).write_text(json.dumps(contents))
        for hardware in (self.usb_serial, 'G987654321ABCDEF'):
            self.boot_serial = hardware
            for preview, args, params in (
                (self.tool.plan_package_action, ('undo',), {}),
                (self.tool.plan_device_action, ('setting-undo',), {'namespace': 'system', 'key': 'font_scale'}),
                (self.tool.plan_extra_action, ('private-dns-undo',), {}),
            ):
                with self.subTest(hardware=hardware, action=args[0]):
                    if hardware == self.usb_serial:
                        preview(self.endpoint, *args, **params)
                    else:
                        with self.assertRaises(ToolkitError):
                            preview(self.endpoint, *args, **params)
        self.assertEqual(self.writes, [])

    def test_legacy_endpoint_only_backup_and_undo_are_preserved_and_refused(self):
        legacy_key = hashlib.sha256(self.endpoint.encode()).hexdigest()
        record = {'schema': 1, 'ads': {legacy_key: {'model': 'KFTEST', 'value': '1'}}}
        self.tool.state_dir.mkdir()
        (self.tool.state_dir / 'state.json').write_text(json.dumps(record))
        snapshot = self.root / 'old-backup.json'
        snapshot.write_text(json.dumps({
            'schema': 'fire-tools.packages.v1',
            'device': {'model': 'KFTEST', 'sdk': 30, 'serial_sha256': legacy_key},
            'packages': {'com.amazon.mp3': 'enabled'},
        }))
        with self.assertRaises(ToolkitError):
            self.tool.plan_device_action(self.endpoint, 'package-restore', local=str(snapshot))
        with self.assertRaises(ToolkitError):
            self.tool.plan_ads(self.endpoint, restore=True)
        self.assertEqual(json.loads((self.tool.state_dir / 'state.json').read_text()), record)
        self.assertEqual(self.writes, [])
