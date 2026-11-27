"""Take a bounded snapshot of a local APK folder for the verified sideload workflow."""
from dataclasses import replace
from itertools import islice
import json
import os
from pathlib import Path
import stat

from .apk import MAX_APK_BYTES
from .apk_checks import scan_record
from .service import ToolkitError


MAX_BATCH_FILES = 32
MAX_BATCH_BYTES = 2 * 1024 ** 3
DESKTOP_METADATA = ('.DS_Store', 'desktop.ini', 'Thumbs.db')


def _is_link(info):
    return (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _folder_files(directory):
    info = directory.lstat()
    if _is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise ToolkitError('Select a local directory directly. Linked folders are unsupported.')
    max_entries = MAX_BATCH_FILES + len(DESKTOP_METADATA)
    with os.scandir(directory) as entries:
        batch = sorted(islice(entries, max_entries + 1), key=lambda e: (e.name.casefold(), e.name))
    if len(batch) > max_entries:
        raise ToolkitError('Choose a folder with at most 32 standalone APKs.')

    files = []
    total = 0
    for entry in batch:
        info = entry.stat(follow_symlinks=False)
        path = Path(entry.path)
        regular = stat.S_ISREG(info.st_mode) and not _is_link(info)
        if regular and entry.name in DESKTOP_METADATA:
            continue
        if not regular or path.suffix.lower() != '.apk' or not entry.name.isprintable():
            raise ToolkitError(f'Unsupported folder entry {entry.name!r}. Choose a folder containing only regular standalone APK files.')
        if len(files) >= MAX_BATCH_FILES:
            raise ToolkitError('Choose a folder with at most 32 standalone APKs.')
        if not 0 < info.st_size <= MAX_APK_BYTES:
            raise ToolkitError(f'{entry.name!r} must be a nonempty APK of at most 512 MiB.')
        total += info.st_size
        if total > MAX_BATCH_BYTES:
            raise ToolkitError('The combined APK size exceeds the 2 GiB folder limit.')
        files.append((path, info.st_size))
    if not files:
        raise ToolkitError('Choose a folder with at least one standalone APK.')
    return tuple(files)


def plan_sideload_folder(toolkit, serial, packages, **parameters):
    if packages or parameters.keys() - {'folder', 'signer'}:
        raise ToolkitError('Folder sideload accepts only a folder and an optional signer.')
    folder = parameters.get('folder')
    if not isinstance(folder, str) or not folder or len(folder) > 4096 or not folder.isprintable():
        raise ToolkitError('Choose a local APK folder.')
    selected = Path(folder)
    if selected.drive.startswith('\\\\'):
        raise ToolkitError('Choose a local folder on this computer.')
    try:
        # Canonicalize the parent without resolving a link at the selected folder itself.
        directory = Path(os.path.normpath(selected.parent.resolve(strict=True) / selected.name))
        files = _folder_files(directory)
        paths = [path for path, _size in files]
        plan = toolkit.plan_package_action(serial, 'sideload', paths=json.dumps(list(map(str, paths))),
                                           signer=parameters.get('signer', ''))
        if _folder_files(directory) != files or [apk.path for apk in plan.apks] != paths:
            raise ToolkitError('The folder changed during verification. Review the folder again.')
    except (OSError, RuntimeError) as exc:
        raise ToolkitError(f'Cannot review APK folder {folder!r}. {exc}') from exc

    details = tuple(f'{apk.path.name!r} — {detail}\n  {scan_record(apk.sha256)}'
                    for apk, detail in zip(plan.apks, plan.details, strict=True))
    return replace(plan, title=f'Install APK folder ({len(paths)} selected)', details=details,
                   warnings=(*plan.warnings, 'Only the listed APKs will be installed. '
                             f'Ignored desktop metadata: {", ".join(DESKTOP_METADATA)}.'))
