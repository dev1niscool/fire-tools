import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from open_fire_toolkit.adb import AdbClient, AdbError, Device, DeviceInfo


class AdbBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve(strict=True)
        self.adb = self.directory / "Google platform-tools" / "adb"
        self.adb.parent.mkdir()
        self.adb.touch()
        self.client = AdbClient(self.adb)
        self.run = self.enterContext(patch("open_fire_toolkit.adb._capture"))
        self.connected = self.result("List of devices attached\nFIRE123 device product:fire model:KFTRWI\n")

    @staticmethod
    def result(stdout="", stderr="", returncode=0):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_inventory_uses_explicit_local_server_and_clears_overrides(self):
        self.run.return_value = self.result(
            "List of devices attached\nFIRE123 device model:KFTRWI\n"
            "FIRE456 unauthorized usb:2-1\nFIRE789 offline\n"
            "FIRE900 no permissions (missing udev rules)\n"
        )
        overrides = {
            "ADB_SERVER_SOCKET": "tcp:foreign.example:1234",
            "ANDROID_ADB_SERVER_ADDRESS": "foreign.example",
            "ANDROID_ADB_SERVER_PORT": "1234",
            "ANDROID_SERIAL": "FIRE456",
        }
        with patch.dict(os.environ, overrides):
            self.assertEqual(self.client.devices(), [
                Device("FIRE123", "device", "KFTRWI"),
                Device("FIRE456", "unauthorized"),
                Device("FIRE789", "offline"),
                Device("FIRE900", "no permissions"),
            ])
            invocation = self.run.call_args
            self.assertEqual(invocation.args[0], [str(self.adb), "-H", "localhost", "-P", "5037", "devices", "-l"])
            self.assertTrue(overrides.keys().isdisjoint(invocation.kwargs["env"]))
            self.assertGreater(invocation.kwargs["timeout"], 0)

    def test_shell_preserves_tokens_and_targets_only_selected_serial(self):
        self.run.side_effect = [
            self.result("List of devices attached\nOTHER device\nFIRE123 device\n"),
            self.result("  setting value  \n"),
        ]
        tokens = ["settings", "put", "global", "test", "quote' && $(echo injected); $HOME", ""]
        self.assertEqual(self.client.shell("FIRE123", tokens, timeout=5), "  setting value  ")
        invocation = self.run.call_args
        self.assertEqual(invocation.args[0][5:8], ["-s", "FIRE123", "shell"])
        self.assertEqual(len(invocation.args[0]), 9)
        self.assertEqual(shlex.split(invocation.args[0][-1]), tokens)
        self.assertIn("'quote'", invocation.args[0][-1])
        self.assertEqual(invocation.kwargs["timeout"], 5)

    def test_rejects_invalid_serials_before_subprocess(self):
        for serial in ("", "-s", "FIRE 123", "FIRE;123", "FIRE\n123"):
            with self.subTest(serial=serial), self.assertRaises(AdbError):
                self.client.reboot(serial)
        self.run.assert_not_called()

    def test_unusable_serial_never_reaches_device_command(self):
        for rows in (
            "FIRE123 unauthorized",
            "FIRE123 offline",
            "OTHER device",
            "FIRE123 device\nFIRE123 device",
        ):
            with self.subTest(rows=rows):
                self.run.reset_mock()
                self.run.return_value = self.result(f"List of devices attached\n{rows}\n")
                with self.assertRaises(AdbError):
                    self.client.reboot("FIRE123")
                self.assertEqual(self.run.call_count, 1)
                self.assertEqual(self.run.call_args.args[0][-2:], ["devices", "-l"])

    def test_info_reads_properties_and_current_user(self):
        self.run.side_effect = [self.connected, self.result(
            "[ro.product.model]: [KFTRWI]\n"
            "[ro.product.manufacturer]: [Amazon]\n"
            "[ro.build.version.fireos]: [8.3.1.3]\n"
            "[ro.build.version.release]: [11]\n"
            "[ro.build.version.sdk]: [30]\n"
            "[ro.product.cpu.abilist]: [arm64-v8a,armeabi-v7a]\n"
        ), self.connected, self.result("10\n")]
        self.assertEqual(self.client.info("FIRE123"), DeviceInfo(
            "FIRE123", "KFTRWI", "Amazon", "8.3.1.3", "11", 30,
            ("arm64-v8a", "armeabi-v7a"), 10,
        ))
        self.assertEqual(shlex.split(self.run.call_args_list[1].args[0][-1]), ["getprop"])
        self.assertEqual(shlex.split(self.run.call_args.args[0][-1]), ["am", "get-current-user"])

    def test_info_reads_amazon_marketing_fire_os_property(self):
        self.run.side_effect = [self.connected, self.result(
            "[ro.product.model]: [KFTUWI]\n"
            "[ro.product.manufacturer]: [Amazon]\n"
            "[ro.build.mktg.fireos]: [8.3.3.8]\n"
            "[ro.build.version.sdk]: [30]\n"
        ), self.connected, self.result("0\n")]
        self.assertEqual(self.client.info("FIRE123").fire_os, "8.3.3.8")

    def test_info_rejects_unknown_sdk(self):
        for sdk in ("", "unknown", "0", "-1"):
            with self.subTest(sdk=sdk):
                self.run.side_effect = [self.connected, self.result(f"[ro.build.version.sdk]: [{sdk}]\n")]
                with self.assertRaisesRegex(AdbError, "SDK"):
                    self.client.info("FIRE123")

    def test_info_rejects_unknown_current_user(self):
        for user in ("", "Current user: ?", "-1", "0\n10"):
            with self.subTest(user=user):
                self.run.side_effect = [
                    self.connected, self.result("[ro.build.version.sdk]: [30]\n"),
                    self.connected, self.result(user),
                ]
                with self.assertRaisesRegex(AdbError, "current user"):
                    self.client.info("FIRE123")

    def test_install_rejects_reported_failure_at_exit_zero(self):
        apk = self.directory / "-staged app.apk"
        apk.touch()
        for stdout, stderr in (
            ("Performing Streamed Install\nFailure [INSTALL_FAILED]\n", ""),
            ("Success\n", "adb: Failure [INSTALL_FAILED]\n"),
            ("Performing Streamed Install\n", ""),
        ):
            with self.subTest(stdout=stdout, stderr=stderr):
                self.run.side_effect = [self.connected, self.result(stdout, stderr)]
                with self.assertRaises(AdbError):
                    self.client.install("FIRE123", apk)

    def test_install_passes_absolute_apk_path(self):
        apk = self.directory / "-staged app.apk"
        apk.touch()
        self.run.side_effect = [self.connected, self.result("Performing Streamed Install\nSuccess\n")]
        self.assertIn("Success", self.client.install("FIRE123", apk))
        invocation = self.run.call_args.args[0]
        self.assertEqual(invocation[5:], ["-s", "FIRE123", "install", "-r", "--user", "0", str(apk)])

    def test_lists_disabled_packages(self):
        self.run.side_effect = [self.connected, self.result("package:com.example.one\npackage:com.example.two\n")]
        self.assertEqual(self.client.packages("FIRE123", disabled_only=True), ["com.example.one", "com.example.two"])
        self.assertEqual(
            shlex.split(self.run.call_args.args[0][-1]), ["pm", "list", "packages", "--user", "0", "-d"]
        )

    def test_package_listing_rejects_stderr_at_exit_zero(self):
        self.run.side_effect = [self.connected, self.result(stderr="SecurityException: permission denied")]
        with self.assertRaisesRegex(AdbError, "permission denied"):
            self.client.packages("FIRE123", disabled_only=True)

    def test_reboot_uses_explicit_serial(self):
        self.run.side_effect = [self.connected, self.result()]
        self.assertIsNone(self.client.reboot("FIRE123"))
        self.assertEqual(self.run.call_args.args[0][5:], ["-s", "FIRE123", "reboot"])

    def test_timeouts_surface_as_adb_error(self):
        self.run.side_effect = subprocess.TimeoutExpired([str(self.adb)], 30)
        with self.assertRaisesRegex(AdbError, "timed out"):
            self.client.devices()

    def test_failed_process_surfaces_stderr(self):
        self.run.return_value = self.result(stderr="cannot bind listener", returncode=1)
        with self.assertRaisesRegex(AdbError, "cannot bind listener"):
            self.client.devices()

    def test_rejects_batch_files_and_missing_tools(self):
        for name in ("adb.bat", "adb.cmd", "different.exe"):
            script = self.directory / name
            script.touch()
            with self.subTest(name=name), self.assertRaises(AdbError):
                AdbClient(script)
        with self.assertRaises(AdbError):
            AdbClient(self.directory / "adb.exe")


@unittest.skipIf(os.name == "nt", "Executable script fixture requires a POSIX host.")
class AdbSubprocessTests(unittest.TestCase):
    def fake_adb(self, source):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "platform tools" / "adb"
        path.parent.mkdir()
        interpreter = shlex.quote(sys.executable)
        path.write_text(f"#!/bin/sh\nexec {interpreter} -c {shlex.quote(source)} \"$@\"\n", encoding="utf-8")
        path.chmod(0o700)
        return AdbClient(path)

    def test_combined_output_exceeding_one_mib_is_rejected(self):
        client = self.fake_adb(
            "import sys; print('List of devices attached'); "
            "sys.stdout.write(' ' * 600_000); sys.stdout.flush(); "
            "sys.stderr.write(' ' * 600_000)"
        )
        with self.assertRaisesRegex(AdbError, "output exceeds"):
            client.devices()

    def test_quiet_process_times_out(self):
        client = self.fake_adb(
            "import sys, time; "
            "print('List of devices attached\\nFIRE123 device') "
            "if sys.argv[-1] == '-l' else time.sleep(10)"
        )
        with self.assertRaisesRegex(AdbError, "timed out"):
            client.shell("FIRE123", ["getprop"], timeout=0.1)

    def test_actual_stderr_remains_separate_from_stdout(self):
        client = self.fake_adb(
            "import sys; "
            "print('List of devices attached\\nFIRE123 device') "
            "if sys.argv[-1] == '-l' else print('permission denied', file=sys.stderr)"
        )
        with self.assertRaisesRegex(AdbError, "ADB shell reported an error: permission denied"):
            client.shell("FIRE123", ["pm", "list", "packages"])

    def test_quoted_tokens_survive_remote_shell_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adb"
            path.write_text(
                """#!/bin/sh
set -eu
[ "$1" = "-H" ] && [ "$2" = "localhost" ] && [ "$3" = "-P" ] && [ "$4" = "5037" ] || exit 9
shift 4
if [ "$*" = 'devices -l' ]; then
  printf 'List of devices attached\\nFIRE123 device\\n'
  exit
fi
[ "$1" = '-s' ] && [ "$2" = 'FIRE123' ] && [ "$3" = 'shell' ] && [ "$#" = 4 ] || exit 10
exec /bin/sh -c "$4"
""",
                encoding="utf-8",
            )
            path.chmod(0o700)
            payload = "'; printf BAD; # $(printf BAD) `printf BAD`"
            self.assertEqual(
                AdbClient(path).shell("FIRE123", ["printf", "<%s>\n", payload, ""]),
                f"<{payload}>\n<>",
            )
