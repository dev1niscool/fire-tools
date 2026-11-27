#!/usr/bin/env python3
"""Create a deterministic source-only archive and checksums. Never package tools/APKs."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import zipfile

INVENTORY = 'release-files.txt'


def _source_path(root, name):
    relative = PurePosixPath(name)
    if (not re.fullmatch(r'[A-Za-z0-9._/-]+', name) or relative.is_absolute()
            or '..' in relative.parts or relative.as_posix() != name or name == '.'):
        raise ValueError(f'Invalid release path: {name!r}')
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Refusing symlinked release input: {name}')
    if not path.is_file():
        raise ValueError(f'Missing release input: {name}')
    return path


def source_files(root: Path):
    names = _source_path(root, INVENTORY).read_text(encoding='utf-8').splitlines()
    if INVENTORY not in names or len(names) != len(set(names)) or 'SHA256SUMS' in names:
        raise ValueError('The release inventory must include itself, use unique paths and omit SHA256SUMS.')
    return [(name, _source_path(root, name)) for name in sorted(names)]


def build_release(root: Path, destination: Path) -> Path:
    root = Path(root).resolve(strict=True)
    destination = Path(destination)
    entries = [(name, path.read_bytes()) for name, path in source_files(root)]
    manifest = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in entries)
    entries.append(('SHA256SUMS', manifest.encode('utf-8')))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries):
            item = zipfile.ZipInfo('open-fire-toolkit/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            mode = 0o755 if name == 'launch-linux.sh' else 0o644
            item.external_attr = (0o100000 | mode) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + '.sha256').write_text(digest + '  ' + destination.name + '\n', encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = build_release(root, args.output or root / 'dist' / 'fire-tools-0.2.0.zip')
    print(path)
    print(path.with_suffix(path.suffix + '.sha256').read_text(), end='')


if __name__ == '__main__':
    main()
