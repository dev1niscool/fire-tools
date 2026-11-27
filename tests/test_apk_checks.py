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
