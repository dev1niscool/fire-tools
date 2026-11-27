"""Batch-folder boundaries through the same entry points used by the GUI and CLI."""
import contextlib
from dataclasses import replace
import hashlib
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from open_fire_toolkit import cli
from open_fire_toolkit.apk import ApkInfo
from open_fire_toolkit.feature_catalog import BY_KEY, run_feature
from open_fire_toolkit.service import Toolkit, ToolkitError, ToolConfig
from test_package_workflows import SERIAL, Tablet


class BatchFolderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        self.folder = root / 'APKs with spaces'
        self.folder.mkdir()
        self.adb = Tablet()
        with patch('open_fire_toolkit.service.AdbClient', return_value=self.adb):
            self.toolkit = Toolkit(ToolConfig('adb'), root / 'state')
        self.feature = BY_KEY.get('sideload-folder')
        self.assertIsNotNone(self.feature, 'Missing folder sideload in GUI and CLI catalog')

    def write_apk(self, name, package):
        path = self.folder / name
        path.write_text(package, encoding='ascii')
        return path

    @staticmethod
    def inspect(path):
        data = path.read_bytes()
        return ApkInfo(path, data.decode('ascii'), 1, '1', 23, (), hashlib.sha256(data).hexdigest(),
                       ('a' * 64,))

    def preview(self, **params):
        return run_feature(self.toolkit, SERIAL, self.feature, {'folder': str(self.folder), **params})

    def cli(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = cli.main(list(arguments))
        return result, output.getvalue()

    def test_review_freezes_exact_filenames_hashes_and_signers_in_order(self):
        self.write_apk('zzz.apk', 'org.example.last')
        self.write_apk('Alpha APP.APK', 'org.example.first')
        with patch.object(self.toolkit, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = self.inspect
            plan = self.preview(signer='a' * 64)
            self.assertEqual(self.adb.installs, [])
            self.assertEqual([a.path.name for a in plan.apks], ['Alpha APP.APK', 'zzz.apk'])
            text = '\n'.join(plan.details)
            for apk in plan.apks:
                for value in (apk.path.name, apk.package, apk.sha256, apk.signer_sha256[0]):
                    self.assertIn(value, text)
            self.assertEqual(text.count('No local scan record'), 2)
            self.write_apk('later.apk', 'org.example.late')
            self.toolkit.execute(plan, confirmed=True, log=lambda _: None)
        self.assertEqual(self.adb.installs, ['org.example.first', 'org.example.last'])
        self.assertEqual(self.adb.apk_files['org.example.first'], b'org.example.first')

    def test_cli_token_rejects_changed_folder_and_changed_reviewed_bytes(self):
        path = self.write_apk('app.apk', 'org.example.app')
        args = ['tool', 'sideload-folder', '--serial', SERIAL, '--param', f'folder={self.folder}']
        with patch('open_fire_toolkit.cli.Toolkit', return_value=self.toolkit), patch.object(self.toolkit, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = self.inspect
            code, preview = self.cli(*args)
            self.assertEqual(code, 0, preview)
            token = re.search(r'--confirm-token ([a-f0-9]{64})', preview)[1]
            extra = self.write_apk('new.apk', 'org.example.new')
            self.assertEqual(self.cli(*args, '--yes', '--confirm-token', token)[0], 1)
            extra.unlink()
            path.write_bytes(b'org.example.replaced')
            self.assertEqual(self.cli(*args, '--yes', '--confirm-token', token)[0], 1)
            self.assertEqual(self.adb.installs, [])
            path.write_bytes(b'org.example.app')
            self.assertEqual(self.cli(*args, '--yes', '--confirm-token', token)[0], 0)
        self.assertEqual(self.adb.installs, ['org.example.app'])

    def test_folder_rejects_mixed_inputs_and_subdirectories_before_verification(self):
        self.write_apk('good.apk', 'org.example.good')
        with patch.object(self.toolkit, '_verifier', side_effect=AssertionError('incomplete set')):
            for name in ('bundle.apkm', 'bundle.xapk', 'more.apks', 'notes.txt', 'junk.apk'):
                with self.subTest(name=name):
                    entry = self.folder / name
                    if name == 'bundle.apkm':
                        with ZipFile(entry, 'w') as bundle:
                            bundle.writestr('base.apk', b'a packaged APK')
                    elif name == 'junk.apk':
                        entry.mkdir()
                    else:
                        entry.touch()
                    with self.assertRaisesRegex(ToolkitError, re.escape(name)):
                        self.preview()
                    (entry.rmdir if entry.is_dir() else entry.unlink)()

    def test_only_regular_desktop_metadata_is_ignored_in_full_folder(self):
        names = ('.DS_Store', 'desktop.ini', 'Thumbs.db')
        for name in names:
            (self.folder / name).touch()
        with self.assertRaisesRegex(ToolkitError, 'at least one'):
            self.preview()
        for index in range(32):
            self.write_apk(f'{index}.apk', f'org.example.test{index}')
        with patch.object(self.toolkit, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = self.inspect
            plan = self.preview()
            self.assertEqual(len(plan.apks), 32)
            for name in names:
                self.assertIn(name, '\n'.join(plan.warnings))
        metadata = self.folder / 'desktop.ini'
        metadata.unlink()
        metadata.mkdir()
        with self.assertRaisesRegex(ToolkitError, 'desktop.ini'):
            self.preview()

    def test_refuses_symlinked_file_and_selected_directory(self):
        source = self.write_apk('app.apk', 'org.example.app')
        link = self.folder / 'link.apk'
        try:
            link.symlink_to(source)
        except OSError as exc:
            self.skipTest(f'File symlinks unavailable: {exc}')
        with self.assertRaisesRegex(ToolkitError, 'link.apk'):
            self.preview()
        link.unlink()
        metadata = self.folder / '.DS_Store'
        metadata.symlink_to(source)
        with self.assertRaisesRegex(ToolkitError, '.DS_Store'):
            self.preview()
        metadata.unlink()
        directory_link = self.folder.parent / 'linked'
        directory_link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaisesRegex(ToolkitError, '(?i)link|regular'):
            self.preview(folder=str(directory_link))

    def test_count_size_empty_and_blank_folder_limits(self):
        with self.assertRaisesRegex(ToolkitError, 'folder'):
            self.preview(folder='')
        with self.assertRaisesRegex(ToolkitError, 'empty|at least one'):
            self.preview()
        empty = self.folder / 'empty.apk'
        empty.touch()
        with self.assertRaisesRegex(ToolkitError, 'nonempty|empty'):
            self.preview()
        empty.write_bytes(b'xx')
        with patch('open_fire_toolkit.batch_folder.MAX_APK_BYTES', 1):
            with self.assertRaisesRegex(ToolkitError, '512 MiB'):
                self.preview()
        empty.unlink()
        for n in range(33):
            self.write_apk(f'{n}.apk', 'org.example.app')
        with self.assertRaisesRegex(ToolkitError, '32'):
            self.preview()

    def test_refuses_total_over_budget_before_verification(self):
        self.write_apk('a.apk', 'org.example.app')
        self.write_apk('b.apk', 'org.example.app')
        with patch('open_fire_toolkit.batch_folder.MAX_BATCH_BYTES', 15), \
                patch.object(self.toolkit, '_verifier', side_effect=AssertionError('oversize batch')):
            with self.assertRaisesRegex(ToolkitError, 'combined|total'):
                self.preview()

    def test_refuses_duplicate_packages_and_mismatched_signer(self):
        self.write_apk('one.apk', 'org.example.app')
        with patch.object(self.toolkit, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = self.inspect
            with self.assertRaisesRegex(ToolkitError, 'Signer mismatch'):
                self.preview(signer='b' * 64)
            self.write_apk('two.apk', 'org.example.app')
            with self.assertRaisesRegex(ToolkitError, 'Duplicate package'):
                self.preview()
        self.assertEqual(self.adb.installs, [])

    def test_every_signer_must_be_distinct_and_a_single_pin_rejects_cosigners(self):
        self.write_apk('one.apk', 'org.example.app')
        with patch.object(self.toolkit, '_verifier') as verifier:
            def signed(path):
                return replace(self.inspect(path), signer_sha256=certificates)

            verifier.return_value.inspect.side_effect = signed
            certificates = ('a' * 64, 'a' * 64)
            for pin in ('a' * 64, ''):
                with self.subTest(pin=pin), self.assertRaisesRegex(ToolkitError, 'Duplicate signer'):
                    self.preview(signer=pin)
            certificates = ('a' * 64, 'b' * 64)
            with self.assertRaisesRegex(ToolkitError, 'Signer mismatch'):
                self.preview(signer='a' * 64)
            plan = self.preview()
            for digest in certificates:
                self.assertIn(digest, plan.details[0])

    def test_relative_parent_path_and_changes_during_inspection(self):
        self.write_apk('one.apk', 'org.example.one')
        directory = self.folder.parent / 'selections'
        directory.mkdir()
        selected = directory / '..' / self.folder.name
        with patch.object(self.toolkit, '_verifier') as verifier:
            verifier.return_value.inspect.side_effect = self.inspect
            self.assertEqual(self.preview(folder=str(selected)).packages, ('org.example.one',))

            def add_file(path):
                self.write_apk('two.apk', 'org.example.two')
                return self.inspect(path)

            verifier.return_value.inspect.side_effect = add_file
            with self.assertRaisesRegex(ToolkitError, 'folder changed'):
                self.preview()
        self.assertEqual(self.adb.installs, [])

    def test_demo_never_reads_selected_folder(self):
        with patch('os.scandir', side_effect=AssertionError('folder read')):
            code, text = self.cli('--demo', 'tool', 'sideload-folder', '--serial', 'DEMO_FIRE_HD10',
                                  '--param', 'folder=/missing', '--yes')
        self.assertEqual(code, 0, text)
        self.assertIn('SIMULATED', text)
