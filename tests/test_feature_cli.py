import contextlib
import io
import unittest
from unittest.mock import patch

from open_fire_toolkit import cli


class FeatureCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = cli.main(arguments)
        return result, output.getvalue()

    def test_catalog_is_discoverable_without_tools(self):
        result, output = self.run_cli(['tools'])
        self.assertEqual(result, 0)
        self.assertIn('debloat', output)
        self.assertIn('settings-set', output)
        self.assertIn('screenshot', output)

    def test_package_and_google_inspection_are_read_only_and_device_scoped(self):
        for key, params, expected in (
                ('package-info', ['--param', 'package=com.android.calendar'], 'installed, disabled'),
                ('google-status', [], 'Google Play Store (com.android.vending) - installed, enabled')):
            with self.subTest(key=key):
                code, help_text = self.run_cli(['tools', '--feature', key])
                self.assertEqual(code, 0)
                self.assertIn('Read only', help_text)
                code, text = self.run_cli(['--demo', 'tool', key, *params])
                self.assertEqual(code, 1)
                self.assertIn('--serial', text)
                with patch('subprocess.Popen', side_effect=AssertionError('hardware')):
                    code, text = self.run_cli(['--demo', 'tool', key, '--serial', 'DEMO_FIRE_HD10', *params])
                self.assertEqual(code, 0, text)
                self.assertIn(expected, text)
                self.assertNotIn('Preview only', text)

    def test_demo_package_details_rejects_empty_package_id(self):
        code, text = self.run_cli(['--demo', 'tool', 'package-info', '--serial', 'DEMO_FIRE_HD10'])
        self.assertEqual(code, 1)
        self.assertIn('package identifier', text)

    def test_package_details_unicode_version_in_windows_redirection(self):
        report = 'Version name: 版本3'
        buffer = io.BytesIO()
        output = io.TextIOWrapper(buffer, encoding='cp1252')
        with patch('open_fire_toolkit.cli.Toolkit') as constructor, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            constructor.return_value.package_info.return_value = report
            code = cli.main(['tool', 'package-info', '--serial', 'tablet', '--param', 'package=com.example.app'])
            output.flush()
        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue().decode('cp1252').strip(), report.encode('ascii', 'backslashreplace').decode())

    def test_demo_bulk_change_defaults_to_preview(self):
        with patch('subprocess.Popen', side_effect=AssertionError('hardware execution')):
            result, output = self.run_cli(['--demo', 'tool', 'debloat', '--serial', 'DEMO_FIRE_HD10', '--param', 'profile=standard'])
        self.assertEqual(result, 0)
        self.assertIn('Preview only', output)
        self.assertIn('SIMULATED', output)

    def test_unknown_parameter_is_refused_before_tool_instantiation(self):
        with patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('constructed')):
            result, output = self.run_cli(['tool', 'debloat', '--serial', 'SERIAL', '--param', 'random=value'])
        self.assertEqual(result, 1)
        self.assertIn('Unknown parameter', output)

    def test_preset_comparison_needs_no_android_tools(self):
        with patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('ADB setup')):
            result, output = self.run_cli(['tool', 'debloat-presets'])
        self.assertEqual(result, 0)
        self.assertIn('Standard Debloat (Recommended)', output)
        self.assertIn('Complete Debloat', output)
        self.assertIn('com.amazon.kindle.otter.oobe', output)

    def test_redirected_windows_preview_prints_state_changes_and_confirmation(self):
        buffer = io.BytesIO()
        output = io.TextIOWrapper(buffer, encoding='cp1252')
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = cli.main(['--demo', 'tool', 'debloat', '--serial', 'DEMO_FIRE_HD10'])
            output.flush()
        transcript = buffer.getvalue().decode('cp1252')
        self.assertEqual(result, 0, transcript)
        self.assertIn('SIMULATED — Standard Debloat (Recommended)', transcript)
        self.assertIn('enabled -> disabled', transcript)
        self.assertIn('Preview only', transcript)

    def test_restore_everything_requires_a_selected_tablet(self):
        with patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('unselected tablet')):
            result, output = self.run_cli(['tool', 'debloat-restore'])
        self.assertEqual(result, 1)
        self.assertIn('--serial', output)

    def test_recommended_profile_is_discoverable_and_accepted(self):
        _, help_output = self.run_cli(['tools', '--feature', 'debloat'])
        self.assertIn('recommended', help_output)
        result, output = self.run_cli([
            '--demo', 'tool', 'debloat', '--serial', 'DEMO_FIRE_HD10', '--param', 'profile=recommended',
        ])
        self.assertEqual(result, 0, output)
        self.assertIn('Preview only', output)

    def test_demo_file_operation_does_not_write_host_file(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('file access')), patch('subprocess.Popen', side_effect=AssertionError('hardware')):
            result, output = self.run_cli(['--demo', 'tool', 'screenshot', '--serial', 'DEMO_FIRE_HD10', '--param', 'local=/tmp/never-made-by-demo.png', '--yes'])
        self.assertEqual(result, 0)
        self.assertIn('SIMULATED', output)

    def test_demo_read_only_feature_needs_no_confirmation(self):
        result, output = self.run_cli(['--demo', 'tool', 'settings-list', '--serial', 'DEMO_FIRE_HD10'])
        self.assertEqual(result, 0)
        self.assertIn('SIMULATED', output)
        self.assertNotIn('Preview only', output)

    def test_duplicate_parameter_refused(self):
        result, output = self.run_cli(['--demo', 'tool', 'debloat', '--serial', 'DEMO_FIRE_HD10', '--param', 'profile=standard', '--param', 'profile=complete'])
        self.assertEqual(result, 1)
        self.assertIn('Duplicate parameter', output)

    def test_shell_command_stays_json_tokens(self):
        result, output = self.run_cli(['--demo', 'tool', 'shell', '--serial', 'DEMO_FIRE_HD10', '--param', 'argv=["getprop", "ro.product.model"]'])
        self.assertEqual(result, 0)
        self.assertIn('getprop', output)

    def test_source_directory_works_without_adb_or_tablet(self):
        with patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('ADB setup')):
            result, output = self.run_cli(['tool', 'source-catalog'])
        self.assertEqual(result, 0)
        self.assertIn('https://', output)

    def test_device_action_without_explicit_serial_is_refused(self):
        with patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('constructed')):
            result, output = self.run_cli(['tool', 'debloat'])
        self.assertEqual(result, 1)
        self.assertIn('serial', output.lower())

    def test_demo_endpoint_connection_needs_no_connected_tablet(self):
        with patch('subprocess.Popen', side_effect=AssertionError('real connection')):
            result, output = self.run_cli(['--demo', 'tool', 'wireless-connect', '--param', 'endpoint=192.168.1.50:5555', '--yes'])
        self.assertEqual(result, 0)
        self.assertIn('SIMULATED', output)


if __name__ == '__main__':
    unittest.main()
