from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import os
import struct
import subprocess
import sys
import tempfile
from time import monotonic
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from open_fire_toolkit.apk import ApkError, ApkInfo, ApkVerifier, _run_tool, file_sha256, google_play_order


PIN = "f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83"
BADGING = (
    "package: name='com.android.vending' versionCode='123' versionName='1.2.3'\n"
    "sdkVersion:'23'\nnative-code: 'arm64-v8a' 'armeabi-v7a'\n"
)
VERIFY = (
    "Verifies\nVerified using v1 scheme (JAR signing): false\n"
    "Verified using v2 scheme (APK Signature Scheme v2): true\n"
    "Number of signers: 1\nSigner #1 certificate DN: CN=Example\n"
    f"Signer #1 certificate SHA-256 digest: {PIN}\n"
)


class ApkInspectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name).resolve(strict=True)
        self.aapt, self.jar, self.java, self.apk = (
            root / name for name in ("aapt.exe", "apksigner.jar", "java.exe", "some app.apk")
        )
        for tool in (self.aapt, self.jar, self.java):
            tool.touch()
            tool.chmod(0o700)
        with ZipFile(self.apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"fixture")
            archive.writestr("lib/arm64-v8a/libapp.so", b"fixture")
            archive.writestr("lib/armeabi-v7a/libapp.so", b"fixture")
        self.badging = BADGING
        self.verify = VERIFY
        self.verify_code = 0
        self.xmltree = "E: manifest (line=1)\n  E: application (line=2)\n"

    def inspect(self, device_sdk=None, lineage="", lineage_exit=0):
        def run(args, **kwargs):
            self.assertFalse(kwargs.get("shell", False))
            sdk_flags = ("--min-sdk-version", str(device_sdk), "--max-sdk-version", str(device_sdk)) if device_sdk else ()
            commands = {
                (str(self.java), "-jar", str(self.jar), "lineage", "--in", str(self.apk),
                 "--print-certs"): (lineage, lineage_exit),
                (str(self.aapt), "dump", "badging", str(self.apk)): (self.badging, 0),
                (str(self.aapt), "dump", "xmltree", str(self.apk), "AndroidManifest.xml"): (
                    self.xmltree, 0
                ),
                (str(self.java), "-jar", str(self.jar), "verify", *sdk_flags, "--verbose", "--print-certs",
                 str(self.apk)): (self.verify, self.verify_code),
            }
            output, code = commands[tuple(args)]
            process = MagicMock()
            process.__enter__.return_value = process
            process.wait.return_value = code
            process.poll.return_value = code
            process.output = output.encode()
            return process

        with (
            patch("open_fire_toolkit.apk.subprocess.Popen", side_effect=run),
            patch("open_fire_toolkit.apk._read_tool_output", side_effect=lambda proc, *_: proc.output),
        ):
            return ApkVerifier(self.aapt, self.jar, self.java, device_sdk=device_sdk).inspect(self.apk)

    def test_returns_verified_immutable_metadata(self):
        apk = self.inspect()
        self.assertEqual(
            apk,
            ApkInfo(self.apk, "com.android.vending", 123, "1.2.3", 23,
                    ("arm64-v8a", "armeabi-v7a"), file_sha256(self.apk), (PIN,)),
        )
        with self.assertRaises(FrozenInstanceError):
            apk.package = "com.example.other"

    def test_rotated_gms_requires_verified_v3_and_exact_certificate_lineage(self):
        rotated = "7ce83c1b71f3d572fed04c8d40c5cb10ff75e6d87d9df6fbd53f0468c2905053"
        self.badging = BADGING.replace("com.android.vending", "com.google.android.gms")
        self.verify = (VERIFY.replace(PIN, rotated)
                       + "Verified using v3 scheme (APK Signature Scheme v3): true\n").replace("\n", "\r\n")
        chain = (f"Signer #1 in lineage certificate SHA-256 digest: {PIN}\n"
                 f"Signer #2 in lineage certificate SHA-256 digest: {rotated}\n")
        apk = self.inspect(30, chain)
        self.assertEqual(apk.signer_sha256, (rotated,))
        store = replace(apk, package="com.android.vending", signer_sha256=(PIN,), signer_lineage=())
        framework = replace(store, package="com.google.android.gsf")
        self.assertEqual(google_play_order((apk, store, framework), 30, ("arm64-v8a",))[1], apk)
        for bad_chain in ("", chain.replace(PIN, "0" * 64), chain.replace(rotated, PIN),
                          chain + chain, chain.replace("Signer #2 in lineage", "Source Stamp Signer")):
            with self.subTest(chain=bad_chain), self.assertRaises(ApkError):
                self.inspect(30, bad_chain)
        with self.assertRaises(ApkError):
            self.inspect(30, chain, lineage_exit=1)
        self.verify = self.verify.replace("v3): true", "v3): false")
        with self.assertRaises(ApkError):
            self.inspect(30, chain)
        for wrong in (replace(apk, signer_lineage=()), replace(apk, package="com.android.vending"),
                      replace(apk, signer_sha256=("1" * 64,))):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ApkError, "certificate mismatch"):
                google_play_order([wrong], 30, ("arm64-v8a",))

    def test_alternate_abi_must_match_archive_and_never_grants_primary_support(self):
        self.badging = BADGING.replace(" 'armeabi-v7a'", "\nalt-native-code: 'armeabi-v7a'")
        apk = self.inspect()
        self.assertEqual(apk.abis, ("arm64-v8a",))
        self.badging = self.badging.replace("alt-native-code: 'armeabi-v7a'", "alt-native-code: 'x86'")
        with self.assertRaisesRegex(ApkError, "match"):
            self.inspect()

    def test_invalid_signature_even_if_pin_is_printed(self):
        self.verify_code = 1
        with self.assertRaises(ApkError):
            self.inspect()

    def test_success_status_must_also_report_verification_and_signers(self):
        for output in (VERIFY.removeprefix("Verifies\n"), VERIFY.replace("signers: 1", "signers: 2"),
                       VERIFY.rsplit("Signer #1 certificate SHA-", 1)[0]):
            with self.subTest(output=output), self.assertRaises(ApkError):
                self.verify = output
                self.inspect()

    def test_malformed_metadata_is_rejected(self):
        for badging in (BADGING.replace("sdkVersion:'23'\n", ""),
                        BADGING.replace("sdkVersion:'23'", "sdkVersion:'Q'"),
                        BADGING.replace("com.android.vending", ";invalid"),
                        BADGING.replace("versionCode='123'", "versionCode='?'"),
                        BADGING + "sdkVersion:'24'\n"):
            with self.subTest(length=len(badging)), self.assertRaises(ApkError):
                self.badging = badging
                self.inspect()

    def test_split_and_split_dependent_manifest_are_rejected(self):
        for badging in (BADGING.replace("versionName='1.2.3'", "versionName='1.2.3' split='en'"),
                        BADGING + "uses-split:'config.en'\n"):
            with self.subTest(badging=badging), self.assertRaises(ApkError):
                self.badging = badging
                self.inspect()
        self.badging = BADGING
        self.xmltree += "    A: android:isSplitRequired(0x01010591)=(type 0x12)0xffffffff\n"
        with self.assertRaises(ApkError):
            self.inspect()

    def test_zip_requires_one_unambiguous_manifest(self):
        for names in (("other.xml",), ("AndroidManifest.xml", "../outside"),
                      ("AndroidManifest.xml", "AndroidManifest.xml/")):
            with self.subTest(names=names), self.assertRaises(ApkError):
                with ZipFile(self.apk, "w") as archive:
                    for name in names:
                        archive.writestr(name, b"fixture")
                self.inspect()
        self.apk.write_bytes(b"not a zip")
        with self.assertRaises(ApkError):
            self.inspect()

    def test_zip_central_directory_limit_checked_before_parsing(self):
        contents = bytearray(self.apk.read_bytes())
        contents[-10:-6] = (64 * 1024 * 1024).to_bytes(4, "little")
        self.apk.write_bytes(contents)
        with patch("open_fire_toolkit.apk.ZipFile") as load_archive, self.assertRaises(ApkError):
            try:
                self.inspect()
            finally:
                load_archive.assert_not_called()

    def test_oversized_file_is_rejected_before_hashing(self):
        with self.apk.open("r+b") as archive:
            archive.truncate(512 * 1024 * 1024 + 1)
        with patch("open_fire_toolkit.apk.file_sha256") as hash_apk:
            with self.assertRaisesRegex(ApkError, "512 MiB"):
                self.inspect()
            hash_apk.assert_not_called()

    def test_expansion_limits_are_checked_before_running_tools(self):
        for sizes in ((512 * 1024 * 1024 + 1,), (512 * 1024 * 1024,) * 4):
            with self.subTest(sizes=sizes):
                self.badging = BADGING.split("native-code:", 1)[0]
                with ZipFile(self.apk, "w") as archive:
                    archive.writestr("AndroidManifest.xml", b"fixture")
                    for index in range(len(sizes)):
                        archive.writestr(f"res/file{index}", b"x")
                data = bytearray(self.apk.read_bytes())
                central = data.index(b"PK\x01\x02")
                for size in sizes:
                    central = data.index(b"PK\x01\x02", central + 4)
                    struct.pack_into("<I", data, central + 24, size)
                self.apk.write_bytes(data)
                with self.assertRaisesRegex(ApkError, "expanded size"):
                    self.inspect()

    def test_zip64_locator_is_rejected_before_zipfile_parsing(self):
        data = bytearray(self.apk.read_bytes())
        central = data.rindex(b"PK\x01\x02")
        struct.pack_into("<H", data, central + 32, 20)
        size, = struct.unpack_from("<I", data, len(data) - 10)
        struct.pack_into("<I", data, len(data) - 10, size + 20)
        data[-22:-22] = struct.pack("<4sIQI", b"PK\x06\x07", 0, 0, 1)
        self.apk.write_bytes(data)
        with patch("open_fire_toolkit.apk.ZipFile") as load_archive:
            with self.assertRaisesRegex(ApkError, "ZIP64"):
                self.inspect()
            load_archive.assert_not_called()

    def test_excessive_child_output_is_stopped_before_child_exits(self):
        marker = self.apk.with_suffix(".marker")
        script = (
            "import sys, time; from pathlib import Path; "
            "sys.stderr.buffer.write(b'x' * (2 * 1024 * 1024)); sys.stderr.flush(); "
            "time.sleep(2); Path(sys.argv[1]).touch()"
        )
        with self.assertRaisesRegex(ApkError, "output exceeds"):
            _run_tool("fixture", [sys.executable, "-c", script, str(marker)])
        self.assertFalse(marker.exists())

    def test_quiet_child_is_stopped_at_timeout(self):
        start = monotonic()
        with patch("open_fire_toolkit.apk._TOOL_TIMEOUT", 0.1):
            with self.assertRaisesRegex(ApkError, "timed out"):
                _run_tool("fixture", [sys.executable, "-c", "import time; time.sleep(5)"])
        self.assertLess(monotonic() - start, 3)

    def test_batch_wrapper_is_refused(self):
        batch = self.aapt.with_suffix(".cmd")
        batch.touch()
        batch.chmod(0o700)
        with self.assertRaises(ApkError):
            ApkVerifier(batch, self.jar, self.java)

    def test_native_abi_metadata_must_match_the_archive(self):
        self.badging = BADGING.replace(" 'armeabi-v7a'", "")
        with self.assertRaises(ApkError):
            self.inspect()

    def test_tool_timeout_surfaces_as_apk_error(self):
        expired = subprocess.TimeoutExpired("fixture", 60)
        with patch("open_fire_toolkit.apk.subprocess.Popen", side_effect=expired):
            with self.assertRaisesRegex(ApkError, "apksigner timed out"):
                ApkVerifier(self.aapt, self.jar, self.java).inspect(self.apk)

    @unittest.skipUnless(os.name == "posix", "executable fixture uses a POSIX shebang")
    def test_real_subprocess_preserves_paths_with_spaces_and_metacharacters(self):
        original = self.apk
        self.apk = self.apk.with_name("a package; dollar$.apk")
        original.rename(self.apk)
        commands = (
            (self.java, {
                ("-jar", str(self.jar), "verify", "--verbose", "--print-certs", str(self.apk)): VERIFY,
            }),
            (self.aapt, {
                ("dump", "badging", str(self.apk)): BADGING,
                ("dump", "xmltree", str(self.apk), "AndroidManifest.xml"): self.xmltree,
            }),
        )
        for tool, responses in commands:
            tool.write_text(f"#!{sys.executable}\nimport sys\nprint({responses!r}[tuple(sys.argv[1:])])\n")
        info = ApkVerifier(self.aapt, self.jar, self.java).inspect(self.apk)
        self.assertEqual(info.path, self.apk)
        self.assertEqual(info.signer_sha256, (PIN,))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture")
    def test_hash_rejects_fifo_without_waiting_for_writer(self):
        self.apk.unlink()
        os.mkfifo(self.apk)
        script = """
import sys
from open_fire_toolkit.apk import ApkError, file_sha256
try:
    file_sha256(sys.argv[1])
except ApkError as error:
    print(error)
else:
    raise AssertionError("FIFO accepted")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.apk)], capture_output=True, text=True,
            check=True, timeout=2,
        )
        self.assertIn("regular file", result.stdout)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture")
    def test_preview_rejects_fifo_replaced_after_path_validation(self):
        script = """
import os
import sys
from unittest.mock import patch
from open_fire_toolkit import apk

verifier = apk.ApkVerifier(*sys.argv[1:4])
validate = apk._local_file

def replace_after_validation(path, label):
    validated = validate(path, label)
    validated.unlink()
    os.mkfifo(validated)
    return validated

with patch.object(apk, "_local_file", side_effect=replace_after_validation):
    try:
        verifier.inspect(sys.argv[4])
    except apk.ApkError as error:
        print(error)
    else:
        raise AssertionError("FIFO accepted")
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.aapt), str(self.jar), str(self.java), str(self.apk)],
            capture_output=True, text=True, check=True, timeout=2,
        )
        self.assertIn("regular file", result.stdout)

    def test_hash_reads_full_file(self):
        self.apk.write_bytes(b"abc")
        self.assertEqual(file_sha256(self.apk),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class ApkOrderingTests(unittest.TestCase):
    def setUp(self):
        self.store = ApkInfo(Path("store.apk"), "com.android.vending", 1, "", 23,
                             ("arm64-v8a",), "unused", (PIN,))
        self.gms = replace(self.store, package="com.google.android.gms")
        self.gsf = replace(self.store, package="com.google.android.gsf", abis=())
        self.login = replace(self.gsf, package="com.google.android.gsf.login")
        self.apks = (self.gms, self.store, self.gsf)

    def order(self, apks):
        return google_play_order(apks, 28, ("arm64-v8a",))

    def test_dependencies_install_in_order_with_optional_login_first(self):
        self.assertEqual(self.order(self.apks), (self.gsf, self.gms, self.store))
        self.assertEqual(self.order((*self.apks, self.login)),
                         (self.login, self.gsf, self.gms, self.store))

    def test_sync_adapters_follow_store_or_can_be_added_together(self):
        calendar = replace(self.gsf, package="com.google.android.syncadapters.calendar")
        contacts = replace(self.gsf, package="com.google.android.syncadapters.contacts")
        self.assertEqual(self.order((contacts, self.store, self.gms, calendar, self.login, self.gsf)),
                         (self.login, self.gsf, self.gms, self.store, calendar, contacts))
        self.assertEqual(self.order((contacts, calendar)), (calendar, contacts))
        for invalid in (replace(contacts, signer_sha256=("1" * 64,)), replace(contacts, split=True)):
            with self.subTest(invalid=invalid), self.assertRaises(ApkError):
                self.order((invalid,))

    def test_rejects_incomplete_duplicate_and_unknown_sets(self):
        for apks in (self.apks[:-1], (*self.apks, self.gms),
                     (*self.apks, replace(self.store, package="com.example.extra"))):
            with self.subTest(apks=apks), self.assertRaises(ApkError):
                self.order(apks)

    def test_checks_all_present_signers(self):
        for signers in ((), ("1" * 64,), (PIN, "1" * 64)):
            with self.subTest(signers=signers), self.assertRaises(ApkError):
                self.order((replace(self.gms, signer_sha256=signers), self.store, self.gsf))

    def test_rejects_incompatible_and_split_apks(self):
        for apk in (replace(self.gms, min_sdk=29), replace(self.gms, min_sdk=0),
                    replace(self.gms, abis=("x86",)), replace(self.gms, split=True)):
            with self.subTest(apk=apk), self.assertRaises(ApkError):
                self.order((apk, self.store, self.gsf))
