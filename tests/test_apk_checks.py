import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from open_fire_toolkit import apk_checks
from open_fire_toolkit.cli import main


class OfflineCheckTests(unittest.TestCase):
    def test_checks_bytes_before_device_setup_and_reports_mixed_results(self):
        with tempfile.TemporaryDirectory() as temp:
            sample = Path(temp) / 'renamed-file.apk'
            other_version = Path(temp) / 'Google Play Store.apk'
            sample.write_bytes(b'local test specimen')
            other_version.write_bytes(b'different bytes')
            digest = hashlib.sha256(sample.read_bytes()).hexdigest()
            with (patch.dict(apk_checks.SCANNED_FILES, {digest: 'Reviewed fixture'}),
                  patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('device access')),
                  contextlib.redirect_stdout(io.StringIO()) as output):
                self.assertEqual(main(['check-apks', str(sample)]), 0)
                self.assertEqual(main(['check-apks', str(Path(temp)/'missing.apk'), str(other_version), str(sample)]), 1)
            self.assertIn('Reviewed fixture', output.getvalue())
            self.assertIn('No local scan record', output.getvalue())
            self.assertIn('Cannot read APK', output.getvalue())

    def test_historical_partial_scan_status_is_visible(self):
        for digest in apk_checks.PARTIAL_CHECK:
            self.assertIn('timed out', apk_checks.scan_record(digest))


class GoogleSignatureCheckTests(unittest.TestCase):
    def setUp(self):
        from open_fire_toolkit.apk import ApkInfo, GOOGLE_SIGNER_SHA256, file_sha256
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.selected = root / 'renamed.apk'
        self.selected.write_bytes(b'local selected bytes')
        self.info = ApkInfo(self.selected, 'com.android.vending', 12, '1.2', 23,
                            ('arm64-v8a',), file_sha256(self.selected), (GOOGLE_SIGNER_SHA256,))
        self.options = ['--aapt', 'aapt', '--apksigner-jar', 'apksigner.jar', '--java', 'java',
                        'check-apks', '--verify-google', '--sdk', '30']
        self.enterContext(patch('open_fire_toolkit.cli.Toolkit', side_effect=AssertionError('no ADB')))

    def invoke(self, options, *paths):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main([*options, *map(str, paths)])
        return code, stdout.getvalue() + stderr.getvalue()

    def test_independent_unknown_hash_can_verify_and_uses_private_copy(self):
        with patch('open_fire_toolkit.apk_checks.ApkVerifier') as factory:
            staged = []
            def inspect(candidate):
                staged.append(candidate)
                self.assertNotEqual(candidate.parent, self.selected.parent)
                self.assertEqual(candidate.read_bytes(), self.selected.read_bytes())
                return self.info
            factory.return_value.inspect.side_effect = inspect
            result, report = self.invoke(self.options, self.selected)
            self.assertEqual(result, 0, report)
            self.assertIn("PASSED (1 of 1 verified)", report.splitlines()[0])
            factory.assert_called_once_with('aapt', 'apksigner.jar', 'java', device_sdk=30)
            self.assertFalse(staged[0].exists())
        for field in ('VERIFIED', 'com.android.vending', '1.2', 'arm64-v8a',
                      self.info.sha256, self.info.signer_sha256[0], 'No local scan record'):
            self.assertIn(field, report)

    def test_wrong_signer_package_sdk_split_and_replaced_selection_fail(self):
        from dataclasses import replace
        for metadata in ({'signer_sha256': ('a' * 64,)}, {'package': 'com.example.lookalike'},
                         {'min_sdk': 32}, {'split': True}):
            with self.subTest(metadata=metadata), patch('open_fire_toolkit.apk_checks.ApkVerifier') as factory:
                factory.return_value.inspect.return_value = replace(self.info, **metadata)
                result, report = self.invoke(self.options, self.selected)
                self.assertEqual(result, 1, report)
                self.assertIn('REJECTED', report)
                self.assertNotIn('VERIFIED', report)
        with patch('open_fire_toolkit.apk_checks.ApkVerifier') as factory:
            def replace_after_staging(candidate):
                self.selected.write_bytes(b'replacement')
                return self.info
            factory.return_value.inspect.side_effect = replace_after_staging
            result, report = self.invoke(self.options, self.selected)
            self.assertEqual(result, 1)
            self.assertIn('changed', report)

    def test_explicit_api_and_standalone_files_required(self):
        for options in (self.options[:-2], self.options[:-1] + ['0'], ['check-apks', '--sdk', '30']):
            with self.subTest(options=options):
                result, report = self.invoke(options, self.selected)
                self.assertEqual(result, 1, report)
        bundle = self.selected.with_suffix('.apkm')
        bundle.write_bytes(self.selected.read_bytes())
        with patch('open_fire_toolkit.apk_checks.ApkVerifier') as factory:
            result, report = self.invoke(self.options, bundle)
            self.assertEqual(result, 1)
            self.assertIn('standalone', report)
            factory.return_value.inspect.assert_not_called()

    def test_mixed_file_results_show_each_failed_or_verified_input(self):
        missing = self.selected.with_name('missing.apk')
        with patch('open_fire_toolkit.apk_checks.ApkVerifier') as factory:
            factory.return_value.inspect.return_value = self.info
            result, report = self.invoke(self.options, self.selected, missing)
        self.assertEqual(result, 1)
        self.assertIn('FAILED (1 of 2 verified)', report.splitlines()[0])
        self.assertIn(repr(str(missing)), report)
        self.assertIn(repr(str(self.selected)), report)
        self.assertEqual(report.count('REJECTED:'), 1)
        self.assertEqual(report.count('VERIFIED:'), 1)

    def test_gui_uses_entered_api_and_only_sdk_tools_without_selected_device(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from open_fire_toolkit.gui import App
        app = App.__new__(App)
        app.demo = False
        app.root = object()
        app.device = None
        app.apk_paths = [self.selected]
        app.paths = [Mock(get=Mock(side_effect=AssertionError('ADB is unnecessary'))),
                     *[Mock(get=Mock(return_value=name)) for name in ('aapt', 'jar', 'java')]]
        app._show_tool_output = Mock()
        def run(_title, action, complete):
            complete(action(None))
        app._start = run
        ask = Mock(side_effect=[None, 30, 30])
        with (patch.dict('sys.modules', {'tkinter.simpledialog': SimpleNamespace(askinteger=ask)}),
              patch('open_fire_toolkit.apk_checks.verify_google_apk_files', return_value=('verified', True)) as verify):
            app._verify_google_files()
            verify.assert_not_called()
            app._verify_google_files()
            verify.assert_called_once_with((self.selected,), sdk=30, aapt_path='aapt', apksigner_jar='jar', java_path='java')
            app._show_tool_output.assert_called_once_with('Verify Google signatures', '', 'verified')
            verify.return_value = ('FAILED (1 of 2 verified)', False)
            app._verify_google_files()
            app._show_tool_output.assert_called_with('Google signature check failed', '', 'FAILED (1 of 2 verified)')
