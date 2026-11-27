"""Check ADB's live connection identity during confirmed network operations."""
from pathlib import Path
import shlex
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from open_fire_toolkit.adb import AdbError
from open_fire_toolkit.service import ToolConfig, Toolkit, ToolkitError


ENDPOINT = '192.0.2.18:5555'


class TransportBindingTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.adb_path = Path(folder) / 'adb'
        self.adb_path.touch()
        self.toolkit = Toolkit(ToolConfig(str(self.adb_path)), Path(folder) / 'state')
        self.client = self.toolkit.adb
        self.transport = '21'
        self.commands = []
        self.writes = []
        self.replace_at_dispatch = False
        self.enterContext(patch.object(self.client, '_run', side_effect=self.run_adb))

    def run_adb(self, args, timeout=30):
        self.commands.append(list(args))
        if args == ['devices', '-l']:
            return CompletedProcess([], 0, f'List of devices attached\n{ENDPOINT} device model:KFTUWI transport_id:{self.transport}\n', '')
        mode, destination, op, *rest = args
        if op == 'reboot' and self.replace_at_dispatch:
            self.transport = '22'
        if (mode, destination) not in {('-s', ENDPOINT), ('-t', self.transport)}:
            raise AdbError('ADB transport disappeared')
        if op == 'shell':
            command = shlex.split(rest[0])
            if command == ['getprop']:
                output = ('[ro.product.model]: [KFTUWI]\n[ro.product.manufacturer]: [Amazon]\n'
                          '[ro.boot.serialno]: [G0W1000012345678]\n[ro.build.version.sdk]: [30]\n')
            elif command == ['am', 'get-current-user']:
                output = '0'
            else:
                raise AssertionError(command)
        elif op == 'reboot':
            self.writes.append(self.transport)
            output = ''
        else:
            raise AssertionError(args)
        return CompletedProcess([], 0, output, '')

    def test_reviewed_network_plan_checks_identity_and_writes_on_one_transport(self):
        plan = self.toolkit.plan_reboot(ENDPOINT)
        self.commands.clear()
        self.toolkit.execute(plan, confirmed=True, log=lambda line: None)
        addressed = [cmd for cmd in self.commands if cmd[0] != 'devices']
        self.assertEqual([cmd[2] for cmd in addressed], ['shell', 'shell', 'reboot'])
        self.assertTrue(all(cmd[:2] == ['-t', '21'] for cmd in addressed))
        self.assertEqual(self.writes, ['21'])

    def test_reassignment_between_final_check_and_dispatch_never_targets_new_device(self):
        plan = self.toolkit.plan_reboot(ENDPOINT)
        self.commands.clear()
        self.replace_at_dispatch = True
        with self.assertRaisesRegex(ToolkitError, 'transport'):
            self.toolkit.execute(plan, confirmed=True, log=lambda line: None)
        self.assertEqual(self.writes, [])
        self.assertIn(['-t', '21', 'reboot'], self.commands)
        self.assertFalse(any(command[0] == '-s' for command in self.commands))
        self.assertFalse((self.toolkit.state_dir / 'operation.lock').exists())
        with self.client.bind_transport(ENDPOINT):
            self.client.shell(ENDPOINT, ['am', 'get-current-user'])
        self.assertEqual(self.commands[-1][:2], ['-t', '22'])

    def test_bound_operation_rejects_another_selection_or_a_reconnect(self):
        with self.client.bind_transport(ENDPOINT):
            with self.assertRaises(AdbError):
                self.client.reboot('OTHER')
            self.transport = '22'
            with self.assertRaisesRegex(AdbError, 'transport|connection'):
                self.client.reboot(ENDPOINT)
        self.assertEqual(self.writes, [])

    def test_invalid_absent_and_duplicate_transport_ids_cannot_be_bound(self):
        for rows in ('', 'transport_id:', 'transport_id:0', 'transport_id:01', 'transport_id:-1',
                     'transport_id:18446744073709551616', 'transport_id:1 transport_id:2',
                     'transport_id:1\nOTHER device transport_id:1'):
            with self.subTest(rows=rows):
                result = CompletedProcess([], 0, f'List of devices attached\n{ENDPOINT} device {rows}\n', '')
                with patch.object(self.client, '_run', return_value=result) as runner:
                    with self.assertRaisesRegex(AdbError, 'transport'):
                        with self.client.bind_transport(ENDPOINT):
                            self.client.reboot(ENDPOINT)
                    self.assertTrue(all(call.args[0] == ['devices', '-l'] for call in runner.call_args_list))

    def test_old_adb_without_ids_still_supports_unbound_diagnostics(self):
        result = CompletedProcess([], 0, f'List of devices attached\n{ENDPOINT} device\n', '')
        with patch.object(self.client, '_run', side_effect=[result, CompletedProcess([], 0, '0', '')]) as runner:
            self.assertEqual(self.client.shell(ENDPOINT, ['am', 'get-current-user']), '0')
            self.assertEqual(runner.call_args.args[0][:2], ['-s', ENDPOINT])


if __name__ == '__main__':
    unittest.main()
