import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_ads_helper.py"
STATE_SOURCE = ROOT / "companion/src/org/firetools/adshelper/AdsState.java"


class CompanionBuildTests(unittest.TestCase):
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
            result = self.run_builder("--sdk", directory, "--output", output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.readlink(), target)
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
