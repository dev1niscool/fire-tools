import os
import json
import shlex
from pathlib import Path, PurePosixPath
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_ads_helper.py"
STATE_SOURCE = ROOT / "companion/src/org/firetools/adshelper/AdsState.java"


class CompanionBuildTests(unittest.TestCase):
    def test_setup_uses_the_source_build_signer_for_the_privileged_grant(self):
        guide = (ROOT / 'companion/README.md').read_text()
        self.assertIn('helper-start', guide)
        self.assertIn('signer=', guide)
        self.assertNotIn('shell pm grant', guide)
        from open_fire_toolkit.cli import parser
        previews = [parser().parse_args(shlex.split(line)[3:]) for line in guide.splitlines()
                    if line.startswith('python -m open_fire_toolkit')]
        install, grant = previews
        self.assertEqual([install.feature, grant.feature], ['sideload', 'helper-start'])
        options = dict(item.split('=', 1) for item in install.param)
        helper_path, = json.loads(options['paths'])
        self.assertTrue(PurePosixPath(helper_path).is_absolute())
        self.assertIn('signer=CERTIFICATE_SHA256', grant.param)

    def run_builder(self, *args):
        return subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), *map(str, args)],
            capture_output=True, text=True, timeout=15, check=False,
        )

    def test_rejects_build_tools_path_traversal(self):
        result = self.run_builder("--sdk", ROOT, "--build-tools-version", "../outside")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("build-tools version", result.stderr)

    def test_rejects_a_compile_platform_below_the_required_api(self):
        result = self.run_builder("--sdk", ROOT, "--android-api", "23")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 28", result.stderr)

    def test_apk_minimum_supports_checking_the_app_notification_switch(self):
        manifest = ET.parse(ROOT / "companion/AndroidManifest.xml")
        uses_sdk = manifest.find("uses-sdk")
        minimum = uses_sdk.get("{http://schemas.android.com/apk/res/android}minSdkVersion")
        self.assertGreaterEqual(int(minimum), 24)
        self.assertEqual(runpy.run_path(str(BUILD_SCRIPT))["MIN_ANDROID_API"], minimum)

    def test_builder_excludes_unrelated_local_source_and_annotation_processors(self):
        builder = runpy.run_path(str(BUILD_SCRIPT))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            shutil.copytree(ROOT / "companion" / "src", root / "src")
            shutil.copyfile(ROOT / "companion/AndroidManifest.xml", root / "AndroidManifest.xml")
            extra = root / "src/local/Unrelated.java"
            extra.parent.mkdir()
            extra.write_text("class Unrelated {}")
            args = builder["parse_args"](["--sdk", str(root), "--output", str(root/"new.apk")])
            tools = builder["Tools"](*([root / "tool"] * 7), keytool=None)
            build = builder["build"]
            run = Mock(side_effect=RuntimeError("captured compiler invocation"))
            with patch.dict(build.__globals__, COMPANION=root, resolve_tools=lambda _: tools, run=run):
                with self.assertRaisesRegex(RuntimeError, "captured compiler invocation"):
                    build(args)
            command, = run.call_args.args
            self.assertEqual({"AdsService.java", "AdsState.java", "BootReceiver.java",
                              "HelperSettings.java", "MainActivity.java"},
                             {Path(arg).name for arg in command if str(arg).endswith(".java")})
            self.assertIn("-proc:none", command)
            self.assertIn("-sourcepath", command)

    def test_builder_removes_ambient_java_options_from_signing_subprocess(self):
        builder = runpy.run_path(str(BUILD_SCRIPT))
        env = {"JAVA_TOOL_OPTIONS": "example", "JDK_JAVAC_OPTIONS": "example",
               "JDK_JAVA_OPTIONS": "example", "_JAVA_OPTIONS": "example",
               "CLASSPATH": "extra.jar", "SIGNING_PASSWORD_FOR_TEST": "placeholder"}
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "")) as invoke:
            builder["run"](["javac", "-version"], env=env)
        self.assertEqual({"SIGNING_PASSWORD_FOR_TEST": "placeholder"}, invoke.call_args.kwargs["env"])

    @unittest.skipIf(os.name == "nt", "Windows protects signing keys with filesystem ACLs")
    def test_reused_fixed_password_key_requires_private_permissions(self):
        get_key = runpy.run_path(str(BUILD_SCRIPT))["development_keystore"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "ads-helper-development.p12"
            key.write_bytes(b"existing local key")
            with patch.dict(get_key.__globals__, BUILD_DIR=root):
                for mode in (0o640, 0o602):
                    with self.subTest(mode=oct(mode)):
                        key.chmod(mode)
                        with self.assertRaisesRegex(ValueError, "private"):
                            get_key(None, {})
                        self.assertEqual(key.read_bytes(), b"existing local key")
                key.chmod(0o600)
                self.assertEqual(get_key(None, {}), key)

    @unittest.skipIf(os.name == "nt", "Windows protects signing keys with filesystem ACLs")
    def test_private_key_cannot_be_reused_from_a_shared_writable_directory(self):
        get_key = runpy.run_path(str(BUILD_SCRIPT))["development_keystore"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "ads-helper-development.p12"
            key.write_bytes(b"existing local key")
            key.chmod(0o600)
            root.chmod(0o770)
            with patch.dict(get_key.__globals__, BUILD_DIR=root):
                with self.assertRaisesRegex(ValueError, "directory"):
                    get_key(None, {})

    def test_reports_a_missing_sdk_platform_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_builder("--sdk", directory, "--android-api", "36")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("platforms", result.stderr)
            self.assertIn("android.jar", result.stderr)

    def test_existing_output_is_left_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.apk"
            output.write_bytes(b"existing APK")
            result = self.run_builder("--sdk", directory, "--output", output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.read_bytes(), b"existing APK")

    def test_dangling_output_symlink_is_left_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing.apk"
            output = Path(directory) / "link.apk"
            try:
                output.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("This host cannot create symlinks")
            original_link = output.readlink()
            result = self.run_builder("--sdk", directory, "--output", output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.readlink(), original_link)
            self.assertFalse(target.exists())


class CompanionStateTests(unittest.TestCase):
    def test_preserves_original_across_restarts_stops_and_failed_restore(self):
        java_bin = Path(os.environ["JAVA_HOME"]) / "bin" if os.environ.get("JAVA_HOME") else None
        javac = shutil.which("javac", path=str(java_bin) if java_bin else None)
        java = shutil.which("java", path=str(java_bin) if java_bin else None)
        if not javac or not java:
            self.skipTest("A JDK is needed to exercise Java helper state")

        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "StateTest.java"
            program.write_text(
                """
package org.firetools.adshelper;

import java.util.Objects;

public class StateTest {
    private static class Store implements AdsState.Storage {
        boolean enabled;
        boolean saved;
        AdsState.Entry original;
        boolean failSave;

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) { this.enabled = enabled; }
        public boolean hasOriginal() { return saved; }
        public AdsState.Entry originalValue() { return original; }
        public void saveOriginal(AdsState.Entry value) {
            if (failSave) throw new IllegalStateException("Save failed");
            saved = true;
            original = value;
        }
        public void clearOriginal() { saved = false; original = null; }
    }

    private static class Setting implements AdsState.Setting {
        String value;
        boolean present;
        boolean accept = true;

        public String read() { return value; }
        public AdsState.Entry snapshot() { return new AdsState.Entry(present, value); }
        public boolean write(String next) {
            if (!accept) return false;
            value = next;
            present = true;
            return true;
        }
        public void delete() {
            if (accept) {
                present = false;
                value = null;
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        for (AdsState.Entry original : new AdsState.Entry[]{
                new AdsState.Entry(false, null), new AdsState.Entry(true, null),
                new AdsState.Entry(true, "1"), new AdsState.Entry(true, "null")}) {
            Store store = new Store();
            Setting setting = new Setting();
            setting.value = original.value;
            setting.present = original.present;
            AdsState session = new AdsState(store, setting);
            session.apply();
            require(!store.saved, "Disabled session must not write or save");
            session.enable();
            store.failSave = true;
            try {
                session.apply();
                throw new AssertionError("Journal failure must be reported");
            } catch (IllegalStateException expected) {
                require(setting.present == original.present && Objects.equals(setting.value, original.value),
                        "Journal failure must prevent a write");
            }
            store.failSave = false;
            session.apply();
            require(store.saved && store.original.present == original.present
                    && Objects.equals(store.original.value, original.value), "Save absent or exact original");
            require("0".equals(setting.value), "Enable writes zero");

            AdsState restarted = new AdsState(store, setting);
            setting.value = "external change";
            restarted.apply();
            require("0".equals(setting.value), "Restart resumes enforcement");
            restarted.stop();
            require(!store.enabled && store.saved, "Stop retains the journal");
            require("0".equals(setting.value), "Stop leaves the setting untouched");

            setting.accept = false;
            try {
                restarted.restore();
                throw new AssertionError("Provider rejection must be reported");
            } catch (IllegalStateException expected) {
                require(store.saved && !store.enabled, "Failed restore must remain retryable");
            }
            setting.accept = true;
            require(restarted.restore(), "Restore must report success");
            require(setting.present == original.present && Objects.equals(setting.value, original.value)
                    && !store.saved, "Restore original or delete absent entry");
            require(!restarted.restore(), "No journal must mean nothing to restore");
        }
    }
}
""",
                encoding="utf-8",
            )
            compile_result = subprocess.run(
                [javac, "-d", directory, str(STATE_SOURCE), str(program)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [java, "-cp", directory, "org.firetools.adshelper.StateTest"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)


if __name__ == "__main__":
    unittest.main()
