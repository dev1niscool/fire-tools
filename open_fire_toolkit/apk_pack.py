"""Identify and verify the four audited APKMirror files for a local HD 10 pack."""

import hashlib
from itertools import islice
import os
from pathlib import Path
import stat

from .apk import ApkError
from .apk_checks import HD10_APKMIRROR


BUNDLED_HASHES = {name: digest for digest, (_, name, _) in HD10_APKMIRROR.items()}
BUNDLED_SIZES = {name: size for _, name, size in HD10_APKMIRROR.values()}
_FILE_MANAGER_METADATA = {'.ds_store', 'desktop.ini', 'thumbs.db'}


def _folder(root):
    return (Path(root) if root is not None else Path(__file__).resolve().parents[1]) / 'google-apks'


def pack_available(root=None) -> bool:
    """Report a directory entry beside the launchers, without trusting its contents."""
    return os.path.lexists(_folder(root))


def _checked_stat(path):
    # Also catches Windows junctions and symlinks in intermediate directories.
    absolute = Path(path).absolute()
    for part in (*reversed(absolute.parents), absolute):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ApkError(f'Unexpected link in Google APK path: {part}')
    return info


def _members(folder):
    if not stat.S_ISDIR(_checked_stat(folder).st_mode):
        raise ApkError(f'Expected a directory containing four Google APKs: {folder}')
    with os.scandir(folder) as entries:
        candidates = (entry for entry in entries if entry.name.lower() not in _FILE_MANAGER_METADATA
                      or not entry.is_file(follow_symlinks=False))
        return [folder / entry.name for entry in islice(candidates, len(BUNDLED_HASHES) + 1)]


def input_apks(inputs):
    """Map four selected files (or one folder) to their expected pack entries by size.

    A size match only selects a candidate. verify_pack_file checks the exact bytes.
    """
    try:
        paths = [Path(p) for p in inputs]
        if len(paths) == 1 and stat.S_ISDIR(_checked_stat(paths[0]).st_mode):
            paths = _members(paths[0])
        if len(paths) != len(BUNDLED_HASHES):
            raise ApkError('Choose the four audited Google APKs or a folder containing exactly those four files.')
        by_size = {size: name for name, size in BUNDLED_SIZES.items()}
        by_name = {}
        for path in paths:
            info = _checked_stat(path)
            if path.suffix.lower() != '.apk' or not stat.S_ISREG(info.st_mode) or info.st_size not in by_size:
                raise ApkError(f'File is not a recognized standalone Google APK for the HD 10 pack: {path}')
            name = by_size[info.st_size]
            if name in by_name:
                raise ApkError(f'Duplicate Google APK candidate for {name}. Select each component once.')
            by_name[name] = path
        return by_name
    except OSError as exc:
        raise ApkError(f'Cannot read the selected Google APK files: {exc}') from exc


def verify_pack_file(path, name, output=None):
    """Hash a checked file descriptor and optionally copy those same bytes."""
    size = BUNDLED_SIZES[name]
    try:
        before = _checked_stat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ApkError(f'{name} has an unexpected file type or size.')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(path, flags), 'rb') as source:
            opened = os.fstat(source.fileno())
            if not os.path.samestat(before, opened) or opened.st_size != size:
                raise ApkError(f'The Google APK changed before opening: {path}')
            digest = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ApkError(f'The Google APK changed during reading: {path}')
                digest.update(chunk)
                if output is not None:
                    output.write(chunk)
                remaining -= len(chunk)
            after = _checked_stat(path)
            if (source.read(1) or not os.path.samestat(opened, after)
                    or after.st_size != size or after.st_mtime_ns != opened.st_mtime_ns):
                raise ApkError(f'The Google APK changed during reading: {path}')
            if digest.hexdigest() != BUNDLED_HASHES[name]:
                raise ApkError(f'SHA-256 mismatch for {name}. Obtain the exact audited APKMirror build.')
    except OSError as exc:
        raise ApkError(f'Cannot read or copy {name}: {exc}') from exc


def bundled_apks(root=None) -> tuple[Path, ...]:
    """Return the verified local pack in install order; never access the network."""
    folder = _folder(root)
    try:
        members = _members(folder)
    except FileNotFoundError as exc:
        raise ApkError(f'No local Google APK pack found at {folder}. Choose APKs or build a personal copy.') from exc
    except OSError as exc:
        raise ApkError(f'Cannot open the local Google APK pack: {exc}') from exc
    if {member.name for member in members} != set(BUNDLED_HASHES):
        raise ApkError('The google-apks folder must contain all four original pack entries and no extra files.')
    paths = tuple(folder / name for name in BUNDLED_HASHES)
    for path in paths:
        verify_pack_file(path, path.name)
    return paths
