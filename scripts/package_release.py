#!/usr/bin/env python3
"""Create a deterministic source-only archive and checksums. Never package tools/APKs."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

INVENTORY = 'release-files.txt'
TEXT_SUFFIXES = {'.py', '.java', '.xml', '.md', '.txt', '.toml', '.json'}
OTHER_SOURCE_FILES = {'LICENSE', '.gitignore', 'launch-linux.sh', 'launch-windows.cmd'}
DEMO_IMAGE = 'docs/images/demo.png'


def _source_path(root, name):
    relative = PurePosixPath(name)
    if (not re.fullmatch(r'[A-Za-z0-9._/-]+', name) or relative.is_absolute()
            or '..' in relative.parts or relative.as_posix() != name or name == '.'):
        raise ValueError(f'Invalid release path: {name!r}')
    if (relative.suffix not in TEXT_SUFFIXES and name not in OTHER_SOURCE_FILES
            and name != DEMO_IMAGE):
        raise ValueError(f'Unsupported distribution file: {name!r}')
    path = root
    for part in relative.parts:
        path = path / part
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f'Refusing symlinked release input: {name}')
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f'Expected a regular file for {name!r}')
    return path


def _source_bytes(root, name):
    path = _source_path(root, name)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f'Expected a regular file for {name!r}')
        data = stream.read()
        after = _source_path(root, name).lstat()
        if not os.path.samestat(opened, after) or opened.st_mtime_ns != after.st_mtime_ns or len(data) != after.st_size:
            raise ValueError(f'Release input changed while reading {name!r}')
    if name == DEMO_IMAGE:
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Expected a PNG demo image.')
    else:
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError(f'Expected UTF-8 text for {name!r}') from exc
        if b'\x00' in data:
            raise ValueError(f'Unexpected binary content in {name!r}')
    return data


def build_release(root: Path, destination: Path) -> Path:
    root = Path(root).resolve(strict=True)
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('Choose a .zip file for the release output.')
    inventory = _source_bytes(root, INVENTORY)
    names = inventory.decode('utf-8').splitlines()
    if INVENTORY not in names or len(names) != len(set(names)) or 'SHA256SUMS' in names:
        raise ValueError('The release inventory must include itself, use unique paths and omit SHA256SUMS.')
    entries = [(name, inventory if name == INVENTORY else _source_bytes(root, name))
               for name in sorted(names)]
    manifest = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in entries)
    entries.append(('SHA256SUMS', manifest.encode('utf-8')))
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum = destination.with_suffix(destination.suffix + '.sha256')
    # Create fresh files and replace directory entries. Writing through an old
    # output could overwrite an unrelated file linked as the ZIP or checksum.
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        staged_zip = Path(folder) / 'archive'
        staged_sum = Path(folder) / 'checksum'
        with zipfile.ZipFile(staged_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(entries):
                item = zipfile.ZipInfo('open-fire-toolkit/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                mode = 0o755 if name == 'launch-linux.sh' else 0o644
                item.external_attr = (0o100000 | mode) << 16
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item, data)
        digest = hashlib.sha256(staged_zip.read_bytes()).hexdigest()
        staged_sum.write_text(digest + '  ' + destination.name + '\n', encoding='utf-8')
        os.replace(staged_zip, destination)
        os.replace(staged_sum, checksum)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = build_release(root, args.output or root / 'dist' / 'fire-tools-0.4.0.zip')
    print(path)
    print(path.with_suffix(path.suffix + '.sha256').read_text(), end='')


if __name__ == '__main__':
    main()
