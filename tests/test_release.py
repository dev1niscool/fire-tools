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
    def test_reproducible_allowlisted_source_archive_with_verifiable_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'src';out=Path(d)/'out';root.mkdir()
            (root/'README.md').write_text('read me')
            (root/'open_fire_toolkit').mkdir()
            (root/'open_fire_toolkit/__init__.py').write_text('__version__="0.1.0"')
            (root/'open_fire_toolkit/bad.exe').write_bytes(b'MZ fake')
            (root/'secret.env').write_text('do not ship')
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
            try:(root/'README.md').symlink_to(secret)
            except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError):release.build_release(root,Path(d)/'out.zip')

if __name__=='__main__':unittest.main()
