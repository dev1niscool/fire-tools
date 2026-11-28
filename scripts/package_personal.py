#!/usr/bin/env python3
"""Build a personal Fire Tools ZIP containing four locally supplied, verified Google APKs."""

import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))

from open_fire_toolkit.apk import ApkError
from open_fire_toolkit.apk_pack import BUNDLED_HASHES, input_apks, verify_pack_file
from scripts.package_release import build_release


def build_personal(root, destination, inputs) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('Choose a .zip output path for the personal copy.')
    selected = input_apks(inputs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = 'open-fire-toolkit/'
    sums = prefix + 'SHA256SUMS'
    # Keep the public release builder and its allowlist unchanged. Everything is
    # staged on the destination filesystem so a failed check preserves the old ZIP.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        work = Path(temporary)
        source_zip = build_release(root, work / 'sources.zip')
        staged = work / 'personal.zip'
        with zipfile.ZipFile(source_zip) as source, zipfile.ZipFile(staged, 'w') as personal:
            manifest = source.read(sums)
            for entry in source.infolist():
                if entry.filename.startswith(prefix + 'google-apks/'):
                    raise ValueError('The source release already contains the private pack directory.')
                if entry.filename != sums:
                    personal.writestr(entry, source.read(entry))
            for name, digest in BUNDLED_HASHES.items():
                member = 'google-apks/' + name
                entry = zipfile.ZipInfo(prefix + member)  # Fixed timestamp for reproducible output.
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_STORED  # APKs are already compressed.
                with personal.open(entry, 'w') as target:
                    verify_pack_file(selected[name], name, target)
                manifest += f'{digest}  {member}\n'.encode('ascii')
            personal.writestr(source.getinfo(sums), manifest)
        os.replace(staged, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='Destination ZIP for your own use')
    parser.add_argument('apks', nargs='+', type=Path, help='Four standalone APKs, or one folder containing only those files')
    args = parser.parse_args()
    try:
        archive = build_personal(ROOT, args.output, args.apks)
        with archive.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        print(f'{checksum}  {archive}')
    except (ApkError, OSError, ValueError) as exc:
        parser.exit(1, f'Cannot build the personal copy: {exc}\n')


if __name__ == '__main__':
    main()
