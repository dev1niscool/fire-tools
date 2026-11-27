"""Local file fingerprints from the documented 2026-11-27 APK audit."""

from .apk import ApkError, file_sha256


# These identify whole files, independently of filenames and signing certificates.
# The evidence and download records are in docs/GOOGLE-APKS.md and docs/TESTING.md.
SCANNED_FILES = {
    '3324ee2f67d23848ae3d9086f20ada10f2cb0dbb6d202067b918cc4fb4d167be': 'Google Account Manager 7.1.2',
    '32156365bcff60f2a0576abe1f15ef7e2b705aea9536bfcbd6fef784d131ccb5': 'Google Services Framework 10-6494331',
    '1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07': 'Google Play services 25.20.37',
    '03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa': 'Google Play Store 36.3.12-21',
    '87fb81b621d060c9779f0942ea379f7cad4f7b551b4d9f1d651a8980f3a6f749': 'Google Calendar Sync 2021.23.3',
    'e6c7f541dba8c334ff416ea6e63df6c6b2a5991db54ac99b5c97d0f2b62068b3': 'Google Contacts Sync 11',
}
PARTIAL_CHECK = {
    '1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07',
    '03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa',
}


def scan_record(digest):
    name = SCANNED_FILES.get(digest)
    if name is None:
        return 'No local scan record for these bytes. A different release has a different hash.'
    result = f'Matches scanned file: {name}. ClamAV reported zero detections on 2026-11-27.'
    if digest in PARTIAL_CHECK:
        result += ' One legacy Android scanner check timed out.'
    return result


def check_apk_files(paths) -> tuple[str, bool]:
    """Compare bytes against prior scan records before any Android tools are configured."""
    records = []
    all_matched = True
    for path in paths:
        try:
            digest = file_sha256(path)
        except ApkError as error:
            records.append(f'{str(path)!r} — {str(error)!r}')
            all_matched = False
            continue
        records.append(f'{str(path)!r}\n  SHA-256 {digest}\n  {scan_record(digest)}')
        if digest not in SCANNED_FILES:
            all_matched = False
    return '\n'.join(records), all_matched
