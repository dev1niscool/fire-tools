import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import hashlib

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/package_release.py'
spec=importlib.util.spec_from_file_location('package_release',SCRIPT)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def test_local_docs_and_companion_notes_are_ignored_after_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            archive = release.build_release(SCRIPT.parents[1], out / 'original.zip')
            with zipfile.ZipFile(archive) as source:
                source.extractall(out / 'extracted')
            root = out / 'extracted/open-fire-toolkit'
            private = ['docs/images/my-tablet.png', 'docs/local-logcat.txt', 'companion/local-notes.xml',
                       'companion/local-key.p12', 'companion/local.apk', 'scripts/local.py']
            for name in private:
                (root / name).write_text('private')
            built = release.build_release(root, out / 'rebuilt.zip')
            with zipfile.ZipFile(built) as result:
                names = set(result.namelist())
                self.assertIn('open-fire-toolkit/docs/images/demo.png', names)
                self.assertFalse(names.intersection('open-fire-toolkit/' + name for name in private))
            self.assertEqual(archive.read_bytes(), built.read_bytes())

    def test_reproducible_allowlisted_source_archive_with_verifiable_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'src';out=Path(d)/'out';root.mkdir()
            (root/'README.md').write_text('read me')
            (root/'open_fire_toolkit').mkdir()
            (root/'open_fire_toolkit/__init__.py').write_text('__version__="0.1.0"')
            (root/'open_fire_toolkit/bad.exe').write_bytes(b'MZ fake')
            (root/'secret.env').write_text('do not ship')
            (root/'release-files.txt').write_text('README.md\nopen_fire_toolkit/__init__.py\nrelease-files.txt\n')
            one=release.build_release(root,out/'one.zip')
            two=release.build_release(root,out/'two.zip')
            self.assertEqual(one.read_bytes(),two.read_bytes())
            with zipfile.ZipFile(one) as z:
                self.assertNotIn('open-fire-toolkit/secret.env',z.namelist())
                self.assertNotIn('open-fire-toolkit/open_fire_toolkit/bad.exe',z.namelist())
                manifest=z.read('open-fire-toolkit/SHA256SUMS').decode()
                for line in manifest.splitlines():
                    digest,name=line.split('  ',1)
                    self.assertEqual(hashlib.sha256(z.read('open-fire-toolkit/'+name)).hexdigest(),digest)
    def test_symlink_cannot_add_outside_content(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'src';root.mkdir();secret=Path(d)/'secret';secret.write_text('private')
            (root/'release-files.txt').write_text('README.md\nrelease-files.txt\n')
            try:(root/'README.md').symlink_to(secret)
            except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError):release.build_release(root,Path(d)/'out.zip')

    def test_companion_source_is_shipped_without_keys_or_built_apks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'src';helper=root/'companion';helper.mkdir(parents=True)
            (helper/'MainActivity.java').write_text('class MainActivity {}')
            (helper/'AndroidManifest.xml').write_text('<manifest/>')
            (helper/'README.md').write_text('Build instructions')
            (helper/'debug.keystore').write_bytes(b'private signing key')
            (helper/'output.apk').write_bytes(b'not source')
            (root/'release-files.txt').write_text('companion/MainActivity.java\ncompanion/AndroidManifest.xml\ncompanion/README.md\nrelease-files.txt\n')
            archive=release.build_release(root,Path(d)/'out.zip')
            with zipfile.ZipFile(archive) as z:
                self.assertIn('open-fire-toolkit/companion/MainActivity.java',z.namelist())
                self.assertIn('open-fire-toolkit/companion/AndroidManifest.xml',z.namelist())
                self.assertNotIn('open-fire-toolkit/companion/debug.keystore',z.namelist())
                self.assertNotIn('open-fire-toolkit/companion/output.apk',z.namelist())

if __name__=='__main__':unittest.main()
