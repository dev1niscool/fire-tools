import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from open_fire_toolkit import apk_pack
from open_fire_toolkit.apk import ApkError
from scripts.package_personal import build_personal


NAMES = ('com.google.android.gsf.login.apk', 'com.google.android.gsf.apk',
         'com.google.android.gms.apk', 'com.android.vending.apk')


class PersonalPackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'launch.sh').write_text('echo Test\n', encoding='utf-8')
        (self.source / 'release-files.txt').write_text('launch.sh\nrelease-files.txt\n', encoding='utf-8')
        self.folder = self.root / 'google-apks'
        self.folder.mkdir()
        self.data = {name: b'A' * (10 + index) for index, name in enumerate(NAMES)}
        self.digests = {name: hashlib.sha256(data).hexdigest() for name, data in self.data.items()}
        self.enterContext(patch.dict(apk_pack.BUNDLED_HASHES, self.digests, clear=True))
        self.enterContext(patch.dict(apk_pack.BUNDLED_SIZES,
                                     {name: len(data) for name, data in self.data.items()}, clear=True))
        for name, data in self.data.items():
            (self.folder / name).write_bytes(data)

    def test_recognizes_whole_verified_set_in_install_order(self):
        self.assertTrue(apk_pack.pack_available(self.root))
        self.assertEqual(apk_pack.bundled_apks(self.root), tuple(self.folder / name for name in NAMES))
        (self.folder / NAMES[1]).write_bytes(b'X' * 11)
        with self.assertRaisesRegex(ApkError, 'SHA-256'):
            apk_pack.bundled_apks(self.root)

    def test_file_manager_metadata_does_not_become_pack_content(self):
        for name in ('.DS_Store', 'desktop.ini', 'Thumbs.db'):
            (self.folder / name).write_bytes(b'local metadata')
        expected = tuple(self.folder / name for name in NAMES)
        self.assertEqual(apk_pack.bundled_apks(self.root), expected)
        output = build_personal(self.source, self.root / 'clean.zip', [self.folder])
        with zipfile.ZipFile(output) as archive:
            self.assertEqual({name.split('/')[-1] for name in archive.namelist() if '/google-apks/' in name},
                             set(NAMES))
        (self.folder / 'extra.apk').write_bytes(b'other download')
        with self.assertRaises(ApkError):
            apk_pack.bundled_apks(self.root)
        with self.assertRaises(ApkError):
            build_personal(self.source, self.root / 'bad.zip', [self.folder])

    def test_detects_corrupt_or_incomplete_pack_and_unexpected_members(self):
        with self.assertRaises(ApkError):
            apk_pack.bundled_apks(self.source)
        self.assertFalse(apk_pack.pack_available(self.source))
        extra = self.folder / 'unreviewed.apk'
        extra.write_bytes(b'do not include')
        with self.assertRaises(ApkError):
            apk_pack.bundled_apks(self.root)
        extra.unlink()
        (self.folder / NAMES[0]).unlink()
        self.assertTrue(apk_pack.pack_available(self.root))
        with self.assertRaises(ApkError):
            apk_pack.bundled_apks(self.root)

    def test_refuses_linked_apks_and_linked_pack_folder(self):
        original = self.folder / NAMES[0]
        outside = original.rename(self.root / 'outside.apk')
        try:
            original.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links unavailable')
        with self.assertRaisesRegex(ApkError, 'link'):
            apk_pack.bundled_apks(self.root)
        original.unlink()
        outside.rename(original)
        real = self.folder.rename(self.root / 'otherwise-valid')
        self.folder.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ApkError, 'link'):
            apk_pack.bundled_apks(self.root)
        with self.assertRaisesRegex(ApkError, 'link'):
            build_personal(self.source, self.root / 'linked.zip', [self.folder / name for name in NAMES])

    @unittest.skipIf(os.name == 'nt', 'Windows locks the open file against replacement')
    def test_replacement_during_copy_cannot_publish_stale_verification(self):
        name = NAMES[1]
        path = self.folder / name
        replacement = self.root / 'replacement.apk'
        replacement.write_bytes(b'X' * len(self.data[name]))

        class ReplaceDuringWrite(io.BytesIO):
            def write(self, data):
                replacement.replace(path)
                return super().write(data)

        with self.assertRaisesRegex(ApkError, 'changed'):
            apk_pack.verify_pack_file(path, name, ReplaceDuringWrite())

    def test_packages_renamed_inputs_reproducibly_with_a_complete_manifest(self):
        inputs = [self.folder / name for name in NAMES]
        one = build_personal(self.source, self.root / 'one.zip', [self.folder])
        inputs[0] = inputs[0].rename(self.folder / 'account-manager-downloaded.apk')
        two = build_personal(self.source, self.root / 'two.zip', list(reversed(inputs)))
        self.assertEqual(one.read_bytes(), two.read_bytes())
        with zipfile.ZipFile(one) as archive:
            prefix = 'open-fire-toolkit/'
            manifest = archive.read(prefix + 'SHA256SUMS').decode().splitlines()
            manifest_files = set()
            for line in manifest:
                digest, name = line.split('  ', 1)
                self.assertEqual(digest, hashlib.sha256(archive.read(prefix + name)).hexdigest())
                manifest_files.add(prefix + name)
            self.assertEqual(manifest_files, set(archive.namelist()) - {prefix + 'SHA256SUMS'})
            self.assertEqual(archive.getinfo(prefix + 'launch.sh').external_attr >> 16, 0o100755)
            for name in NAMES:
                self.assertEqual(archive.read(prefix + 'google-apks/' + name), self.data[name])

    def test_bad_or_missing_inputs_do_not_publish_or_overwrite(self):
        paths = [self.folder / name for name in NAMES]
        destination = self.root / 'previous.zip'
        destination.write_bytes(b'keep previous copy')
        for picked in [paths[:-1], [paths[0], *paths[:3]]]:
            with self.assertRaises(ApkError):
                build_personal(self.source, destination, picked)
        paths[-1].write_bytes(b'Z' * 13)
        with self.assertRaisesRegex(ApkError, 'SHA-256'):
            build_personal(self.source, destination, paths)
        self.assertEqual(destination.read_bytes(), b'keep previous copy')
