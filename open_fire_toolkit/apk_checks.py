"""Local file fingerprints from the documented 2026-11-27 APK audit."""

from pathlib import Path
import tempfile

from .apk import ApkError, ApkVerifier, PLAY_PACKAGES, check_google_component, file_sha256, stage_apk


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


def verify_google_apk_files(paths, *, sdk, aapt_path, apksigner_jar, java_path) -> tuple[str, bool]:
    """Check independently selected Google components against one Android API offline."""
    if type(sdk) is not int or not 1 <= sdk <= 2_147_483_647:
        raise ApkError('Specify the target Android API as a positive integer with --sdk.')
    if not 1 <= len(paths) <= len(PLAY_PACKAGES):
        raise ApkError('Select one to six local Google APKs per check.')
    if not all((aapt_path, apksigner_jar, java_path)):
        raise ApkError('Choose the official aapt, apksigner.jar and Java paths to verify signatures.')
    verifier = ApkVerifier(aapt_path, apksigner_jar, java_path, device_sdk=sdk)
    lines = ['Compare native ABIs with your tablet. Scan records describe only the identified bytes.']
    verified = 0
    for path in paths:
        lines.extend(('', repr(str(path))))
        try:
            source = Path(path)
            if source.suffix.lower() != '.apk':
                raise ApkError('Choose a standalone .apk file.')
            with tempfile.TemporaryDirectory(prefix='fire-tools-google-check-') as folder:
                staged = Path(folder) / 'selected.apk'
                stage_apk(source, staged)
                apk = verifier.inspect(staged)
                if apk.sha256 != file_sha256(source):
                    raise ApkError('The selected APK changed during verification. Select the file again.')
            lines.extend((f'  Package: {apk.package}', f'  Version: {apk.version_name!r} ({apk.version_code})',
                          f'  Minimum Android API: {apk.min_sdk}',
                          '  Native ABIs: ' + (', '.join(apk.abis) or 'no native library requirement reported'),
                          f'  APK SHA-256: {apk.sha256}', '  Signer SHA-256: ' + ', '.join(apk.signer_sha256)))
            if apk.signer_lineage:
                lines.append('  Verified signing lineage: ' + ' -> '.join(apk.signer_lineage))
            lines.append('  ' + scan_record(apk.sha256))
            check_google_component(apk, sdk)
            lines.append('  VERIFIED: approved Google package and signing identity for the selected API.')
            verified += 1
        except (ApkError, OSError, ValueError) as error:
            lines.append(f'  REJECTED: {str(error)!r}')
    all_verified = verified == len(paths)
    verdict = 'PASSED' if all_verified else 'FAILED'
    lines.insert(0, f'Google signature check {verdict} ({verified} of {len(paths)} verified) for Android API {sdk}.')
    return '\n'.join(lines), all_verified
