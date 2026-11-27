"""Inspect local APKs with Android build tools before planning installation."""

from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
from selectors import DefaultSelector, EVENT_READ
import stat
import struct
import subprocess
from time import monotonic, sleep
from zipfile import BadZipFile, ZipFile


GOOGLE_SIGNER_SHA256 = "f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83"
# This observed Play services rotation also requires a verified v3 signature
# and its signed, in-APK proof of rotation from GOOGLE_SIGNER_SHA256.
_GMS_ROTATED_SIGNER = "7ce83c1b71f3d572fed04c8d40c5cb10ff75e6d87d9df6fbd53f0468c2905053"
PLAY_CORE = (
    "com.google.android.gsf",
    "com.google.android.gms",
    "com.android.vending",
)
SYNC_PROVIDERS = {
    "com.google.android.syncadapters.calendar": "com.android.providers.calendar",
    "com.google.android.syncadapters.contacts": "com.android.providers.contacts",
}
PLAY_PACKAGES = ("com.google.android.gsf.login", *PLAY_CORE, *SYNC_PROVIDERS)
MAX_APK_BYTES = 512 * 1024 * 1024
_MAX_EXPANDED_ARCHIVE = 2 * 1024 * 1024 * 1024
_MAX_CENTRAL_DIRECTORY = 8 * 1024 * 1024
_MAX_ENTRIES = 50_000
_MAX_TOOL_OUTPUT = 1024 * 1024
_TOOL_TIMEOUT = 60
_PACKAGE = re.compile(
    r"package: name='([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)' "
    r"versionCode='([0-9]{1,19})' versionName='([^']*)'(?: .*)?"
)
_SPLIT_XML = re.compile(
    r"^[ \t]*(?:E: uses-split\b|A: (?:android:)?(?:requiredSplitTypes|splitTypes)\b"
    r"|A: (?:android:)?isSplitRequired\b(?!.*=(?:\(type 0x12\))?0x0+$)"
    r'|A: android:name\b.*="com\.android\.vending\.splits\.required")',
    re.MULTILINE,
)


class ApkError(Exception):
    """The APK, verifier tools, or requested install set failed validation."""


@dataclass(frozen=True)
class ApkInfo:
    path: Path
    package: str
    version_code: int
    version_name: str
    min_sdk: int
    abis: tuple[str, ...]
    sha256: str
    signer_sha256: tuple[str, ...]
    split: bool = False
    signer_lineage: tuple[str, ...] = ()


def _local_file(path: str | Path, label: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("expected a regular file")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ApkError(f"Invalid {label} path {path!s}: {exc}") from exc
    return resolved


def _tool(path: str | Path, label: str, *, jar: bool = False) -> Path:
    tool = _local_file(path, label)
    suffixes = {Path(path).suffix.lower(), tool.suffix.lower()}
    if jar:
        if tool.suffix.lower() != ".jar":
            raise ApkError("apksigner must be the official apksigner.jar file.")
    elif suffixes & {".bat", ".cmd"} or (os.name == "nt" and tool.suffix.lower() != ".exe"):
        raise ApkError(f"Choose the {label} executable directly. Batch wrappers are unsupported.")
    elif not os.access(tool, os.X_OK):
        raise ApkError(f"The {label} file is not executable: {tool}")
    return tool


@contextmanager
def _open_regular_file(path: str | Path):
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("expected a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            yield source, info.st_size
    finally:
        os.close(descriptor)


def file_sha256(path: str | Path) -> str:
    """Return a streaming SHA-256 digest of a local file."""
    try:
        with _open_regular_file(path) as (source, file_size):
            _check_file_size(file_size)
            digest = sha256()
            size = 0
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                size += len(chunk)
                _check_file_size(size)
                digest.update(chunk)
            return digest.hexdigest()
    except OSError as exc:
        raise ApkError(f"Cannot read APK {path!s}: {exc}") from exc


def _check_file_size(size: int) -> None:
    if size > MAX_APK_BYTES:
        raise ApkError("APK file exceeds the 512 MiB inspection limit.")


def _check_central_directory(source, file_size: int) -> int:
    """Validate the ZIP directory bounds before ZipFile allocates entry objects."""
    _check_file_size(file_size)
    tail_start = max(0, file_size - 65_557)
    source.seek(tail_start)
    tail = source.read(65_557)
    end = tail.rfind(b"PK\x05\x06")
    if end < 0 or len(tail) - end < 22:
        raise BadZipFile("missing ZIP end record")
    disk, central_disk, disk_entries, entries, size, offset, comment = struct.unpack_from(
        "<4H2IH", tail, end + 4
    )
    if (
        disk or central_disk or disk_entries != entries or not 0 < entries <= _MAX_ENTRIES
        or not 0 < size <= _MAX_CENTRAL_DIRECTORY or len(tail) - end != 22 + comment
        or offset + size != tail_start + end
    ):
        raise BadZipFile("invalid or oversized ZIP central directory")

    eocd_offset = tail_start + end
    if eocd_offset >= 20:
        source.seek(eocd_offset - 20)
        if source.read(4) == b"PK\x06\x07":
            raise BadZipFile("ZIP64 archives are unsupported")
    source.seek(offset)
    directory = source.read(size)
    cursor = 0
    for _ in range(entries):
        if cursor + 46 > len(directory) or directory[cursor:cursor + 4] != b"PK\x01\x02":
            raise BadZipFile("invalid ZIP central directory entry")
        name, extra, comment = struct.unpack_from("<3H", directory, cursor + 28)
        cursor += 46 + name + extra + comment
    if cursor != len(directory):
        raise BadZipFile("ZIP central directory entry count mismatch")
    return offset


def _check_archive(path: Path) -> set[str]:
    try:
        with _open_regular_file(path) as (source, file_size):
            central_offset = _check_central_directory(source, file_size)
            with ZipFile(source) as archive:
                names = set()
                native_abis = set()
                expanded_size = 0
                for entry in archive.infolist():
                    expanded_size += entry.file_size
                    if entry.file_size > MAX_APK_BYTES or expanded_size > _MAX_EXPANDED_ARCHIVE:
                        raise BadZipFile("ZIP expanded size exceeds the inspection limit")
                    name = entry.orig_filename.removesuffix("/")
                    parts = name.split("/")
                    if (
                        name in names or "\\" in name or "\x00" in name
                        or any(part in {"", ".", ".."} for part in parts)
                        or entry.flag_bits & 1 or not 0 <= entry.header_offset < central_offset
                    ):
                        raise BadZipFile("ambiguous, encrypted, or invalid ZIP entry")
                    names.add(name)
                    if len(parts) == 3 and parts[0] == "lib" and parts[2].endswith(".so"):
                        native_abis.add(parts[1])
                manifest = archive.getinfo("AndroidManifest.xml")
                if not 0 < manifest.file_size <= 16 * 1024 * 1024:
                    raise BadZipFile("invalid AndroidManifest.xml size")
                return native_abis
    except (BadZipFile, KeyError, OSError, ValueError) as exc:
        raise ApkError(f"Invalid APK archive {path.name}: {exc}") from exc


def _read_windows_pipe(fd: int, count: int, deadline: float) -> bytes:
    # Windows selectors handle sockets only. Peek before reading the sole pipe.
    import ctypes
    from ctypes import wintypes
    import msvcrt

    peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
    peek.argtypes = (
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD,
        wintypes.LPDWORD, wintypes.LPDWORD,
    )
    peek.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(fd)
    available = wintypes.DWORD()
    while monotonic() < deadline:
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            error = ctypes.get_last_error()
            if error in {109, 232, 233}:  # Pipe closed or disconnected.
                return b""
            raise ctypes.WinError(error)
        if available.value:
            return os.read(fd, min(count, available.value))
        sleep(0.01)
    raise TimeoutError


def _read_tool_output(process: subprocess.Popen, label: str, deadline: float, limit: int) -> bytes:
    fd = process.stdout.fileno()
    with DefaultSelector() as selector:
        if os.name != "nt":
            selector.register(fd, EVENT_READ)
        output = bytearray()
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            count = min(65_536, limit + 1 - len(output))
            if os.name == "nt":
                chunk = _read_windows_pipe(fd, count, deadline)
            else:
                if not selector.select(remaining):
                    raise TimeoutError
                chunk = os.read(fd, count)
            if not chunk:
                return bytes(output)
            output.extend(chunk)
            if len(output) > limit:
                raise ApkError(f"{label} output exceeds the inspection limit.")


def _run_tool(label: str, args: list[str], *, output_limit: int = _MAX_TOOL_OUTPUT) -> str:
    env = os.environ.copy()
    for name in ("JDK_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS"):
        env.pop(name, None)
    deadline = monotonic() + _TOOL_TIMEOUT
    try:
        with subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, shell=False,
        ) as process:
            try:
                output = _read_tool_output(process, label, deadline, output_limit)
                code = process.wait(timeout=max(0, deadline - monotonic()))
            finally:
                if process.poll() is None:
                    process.kill()
            if code:
                diagnostic = output[:2048].decode("utf-8", errors="replace")
                detail = " ".join(diagnostic.split())
                raise ApkError(f"{label} failed (exit {code})" + (f": {detail}" if detail else "."))
            return output.decode("utf-8")
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        raise ApkError(f"{label} timed out after {_TOOL_TIMEOUT} seconds.") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ApkError(f"Cannot run or read {label}: {exc}") from exc


def _parse_badging(output: str, zip_abis: set[str]) -> tuple[str, int, str, int, tuple[str, ...]]:
    lines = output.splitlines()
    package_lines = [line for line in lines if line.startswith("package:")]
    package = _PACKAGE.fullmatch(package_lines[0]) if len(package_lines) == 1 else None
    if package is None:
        raise ApkError("aapt did not report valid package and version metadata.")
    if re.search(r"(?:^| )split\s*=", package_lines[0]) or any(
        line.startswith("uses-split:") for line in lines
    ):
        raise ApkError("Split APKs and APKs requiring splits are unsupported.")

    sdk_lines = [line for line in lines if line.startswith("sdkVersion:")]
    sdk = re.fullmatch(r"sdkVersion:'([1-9][0-9]{0,8})'", sdk_lines[0]) if len(sdk_lines) == 1 else None
    if sdk is None:
        raise ApkError("aapt did not report a known numeric minimum SDK.")

    def declared_abis(label):
        rows = [line for line in lines if line.startswith(label + ":")]
        if not rows:
            return ()
        if len(rows) != 1 or not re.fullmatch(label + r":(?: '[a-zA-Z0-9_-]+')+\s*", rows[0]):
            raise ApkError("aapt did not report valid native ABI metadata.")
        return tuple(re.findall(r"'([a-zA-Z0-9_-]+)'", rows[0]))

    abis = declared_abis("native-code")
    alternate = declared_abis("alt-native-code")
    # Some multi-arch Google APKs include only a subset of libs for the alternate ABI.
    # Account for all packaged libs but advertise only the primary installable ABIs.
    if (alternate and not abis) or set(abis).union(alternate) != zip_abis:
        raise ApkError("aapt native ABI metadata does not match the APK archive.")
    return package[1], int(package[2]), package[3], int(sdk[1]), abis


def _parse_signers(output: str) -> tuple[str, ...]:
    lines = output.splitlines()
    numbers = [line for line in lines if line.startswith("Number of signers:")]
    count = re.fullmatch(r"Number of signers: ([1-9][0-9]{0,4})", numbers[0]) if len(numbers) == 1 else None
    if lines.count("Verifies") != 1 or "DOES NOT VERIFY" in lines or count is None:
        raise ApkError("apksigner did not report a valid APK signature.")

    cert_lines = [line for line in lines if line.startswith("Signer #") and " certificate SHA-256 digest:" in line]
    if len(cert_lines) != int(count[1]):
        raise ApkError("apksigner did not report every signer certificate.")
    digests = []
    for index, line in enumerate(cert_lines, start=1):
        cert = re.fullmatch(rf"Signer #{index} certificate SHA-256 digest: ([0-9a-fA-F]{{64}})", line)
        if cert is None:
            raise ApkError("apksigner reported malformed signer certificate metadata.")
        digests.append(cert[1].lower())
    return tuple(digests)


def google_signer_is_trusted(apk: ApkInfo) -> bool:
    if apk.signer_sha256 == (GOOGLE_SIGNER_SHA256,):
        return True
    return (apk.package == "com.google.android.gms"
            and apk.signer_sha256 == (_GMS_ROTATED_SIGNER,)
            and apk.signer_lineage == (GOOGLE_SIGNER_SHA256, _GMS_ROTATED_SIGNER))


class ApkVerifier:
    """Verify APK signatures and collect APK metadata using explicit local tools."""

    def __init__(self, aapt_path, apksigner_jar, java_path, *, device_sdk: int | None = None):
        self._sdk = device_sdk
        self._aapt = _tool(aapt_path, "aapt")
        self._jar = _tool(apksigner_jar, "apksigner", jar=True)
        self._java = _tool(java_path, "Java")

    def inspect(self, path: str | Path) -> ApkInfo:
        apk = _local_file(path, "APK")
        if apk.suffix.lower() != ".apk":
            raise ApkError("Choose a standalone .apk file.")
        zip_abis = _check_archive(apk)
        digest = file_sha256(apk)
        signer_tool = [str(self._java), "-jar", str(self._jar)]
        platform = [] if self._sdk is None else ["--min-sdk-version", str(self._sdk), "--max-sdk-version", str(self._sdk)]
        verification = _run_tool("apksigner", [*signer_tool, "verify", *platform, "--verbose", "--print-certs", str(apk)])
        signers = _parse_signers(verification)
        badging = _run_tool("aapt badging", [str(self._aapt), "dump", "badging", str(apk)])
        package, version_code, version_name, min_sdk, abis = _parse_badging(badging, zip_abis)
        lineage = ()
        if package == "com.google.android.gms" and signers == (_GMS_ROTATED_SIGNER,):
            # apksigner verify validates the v3 signature and proof of rotation.
            # Its lineage command then identifies the authenticated ancestors.
            v3_success = {
                "Verified using v3 scheme (APK Signature Scheme v3): true",
                "Verified using v3.1 scheme (APK Signature Scheme v3.1): true",
            }
            if v3_success.isdisjoint(verification.splitlines()):
                raise ApkError("The rotated Google Play services signer requires a verified v3 signature.")
            lineage_output = _run_tool("apksigner lineage", [*signer_tool, "lineage", "--in", str(apk), "--print-certs"])
            rows = [row.lower() for row in lineage_output.splitlines()
                    if row.startswith("Signer #") and " in lineage certificate SHA-256 digest:" in row]
            lineage = (GOOGLE_SIGNER_SHA256, _GMS_ROTATED_SIGNER)
            if rows != [f"signer #{n} in lineage certificate sha-256 digest: {digest}"
                        for n, digest in enumerate(lineage, start=1)]:
                raise ApkError("The Google Play services signing lineage does not match the trusted rotation.")
        manifest = _run_tool(
            "aapt manifest", [str(self._aapt), "dump", "xmltree", str(apk), "AndroidManifest.xml"],
            output_limit=4 * 1024 * 1024,
        )
        if not re.search(r"^[ \t]*E: manifest\b", manifest, re.MULTILINE):
            raise ApkError("aapt did not report a readable Android manifest.")
        if _SPLIT_XML.search(manifest):
            raise ApkError("Split APKs and APKs requiring splits are unsupported.")
        if digest != file_sha256(apk):
            raise ApkError("The APK changed during inspection.")
        return ApkInfo(apk, package, version_code, version_name, min_sdk, abis, digest, signers, signer_lineage=lineage)


def google_play_order(
    apks: Sequence[ApkInfo], sdk: int, abis: Sequence[str],
) -> tuple[ApkInfo, ...]:
    """Enforce the Google signing pin and order compatible standalone APKs."""
    entries = {}
    device_abis = set(abis)
    for apk in apks:
        if apk.package not in PLAY_PACKAGES:
            raise ApkError(f"Unexpected Google Play package: {apk.package}")
        if apk.package in entries:
            raise ApkError(f"Duplicate Google Play package: {apk.package}")
        if apk.split:
            raise ApkError(f"Split APK is unsupported: {apk.package}")
        if not 0 < apk.min_sdk <= sdk:
            raise ApkError(f"{apk.package} requires Android SDK {apk.min_sdk}, device SDK is {sdk}.")
        if apk.abis and not device_abis.intersection(apk.abis):
            raise ApkError(f"{apk.package} has no native ABI supported by the device.")
        if not google_signer_is_trusted(apk):
            raise ApkError(f"Google signing certificate mismatch: {apk.package}")
        entries[apk.package] = apk
    # The service checks the tablet's enabled core packages for an adapter-only addition.
    if not entries or not entries.keys() <= SYNC_PROVIDERS.keys():
        missing = [package for package in PLAY_CORE if package not in entries]
        if missing:
            raise ApkError(f"Missing required Google Play packages: {', '.join(missing)}")
    return tuple(entries[package] for package in PLAY_PACKAGES if package in entries)
