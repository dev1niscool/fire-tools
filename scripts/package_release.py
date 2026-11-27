#!/usr/bin/env python3
"""Create a deterministic source-only archive and checksums. Never package tools/APKs."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT_FILES = {'README.md', 'SECURITY.md', 'LICENSE', 'pyproject.toml',
              'launch-windows.cmd', 'launch-linux.sh', '.gitignore'}


def source_files(root: Path):
    found = []
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        parts = relative.parts
        allowed = (len(parts) == 1 and parts[0] in ROOT_FILES) or (
            parts[0] in {'open_fire_toolkit', 'tests', 'scripts'}
            and path.suffix == '.py' and '__pycache__' not in parts
        ) or (parts[0] == 'docs' and path.suffix in {'.md', '.txt', '.png'}) or (
            parts[0] == 'companion' and path.suffix in {'.java', '.xml', '.md'}
            and not any(part in {'build', 'out', 'dist', '.gradle'} for part in parts)
        )
        if allowed:
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
                raise ValueError(f'Refusing symlinked release input: {relative}')
            if path.is_file():
                found.append((relative.as_posix(), path))
    return sorted(found)


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
