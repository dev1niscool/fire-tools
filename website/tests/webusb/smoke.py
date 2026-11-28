"""Exercise the built browser tools through a simulated WebUSB ADB device.

Requires Python 3.11+, the Playwright Python package, and Chromium. Set
CHROMIUM_PATH to an installed Chromium executable or install Playwright's Chromium.
Run from the repository root:

    python website/tests/webusb/smoke.py
    python website/tests/webusb/smoke.py --apk-dir /path/to/your/audited-apks

This test never contacts or flashes a real device. USB selection and transfers are
simulated; the page, transport, browser cryptography, and binary verifier are real.
"""

import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from open_fire_toolkit.apk_checks import SCANNED_FILES

# The simulated package manager reports the manifest identity for each test APK.
SIZES = {
    6552461: "com.google.android.gsf.login",
    4296499: "com.google.android.gsf",
    228440903: "com.google.android.gms",
    59468089: "com.android.vending",
    2450495: "com.google.android.syncadapters.calendar",
    2763377: "com.google.android.syncadapters.contacts",
}


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def audited_files(directory):
    if not directory.is_dir():
        raise ValueError(f"APK directory does not exist: {directory}")
    files = {}
    for path in directory.rglob("*.apk"):
        size = path.stat().st_size
        if size in SIZES and size not in files:
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() in SCANNED_FILES:
                    files[size] = path.resolve()
    if missing := set(SIZES) - files.keys():
        raise ValueError("Missing audited APKs for " + ", ".join(SIZES[n] for n in sorted(missing)))
    return [files[size] for size in reversed(SIZES)]


def select_real_files(page, paths):
    # Give Chrome real disk-backed File objects without sending APKs over HTTP.
    cdp = page.context.new_cdp_session(page)
    try:
        document = cdp.send("DOM.getDocument")["root"]["nodeId"]
        field = cdp.send("DOM.querySelector", {"nodeId": document, "selector": "#web-google-files"})
        cdp.send("DOM.setFileInputFiles", {"nodeId": field["nodeId"], "files": [str(p) for p in paths]})
    finally:
        cdp.detach()


def change_ads(page, action, *, confirm):
    page.locator("#web-action").select_option(action)
    page.locator("#web-change-review").click()
    expect(page.locator("#web-confirm")).to_be_enabled()
    page.locator("#web-confirm" if confirm else "#web-cancel").click()
    expect(page.locator("#web-change-review")).to_be_enabled()


def run(browser, url, apks):
    page = browser.new_page()
    page.add_init_script(path=HERE / "fakeusb.js")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    connect = page.locator("#web-connect")
    expect(connect).to_be_enabled()
    assert page.evaluate("mockTablet.chooserCount") == 0
    page.evaluate("mockTablet.cancel = true")
    connect.click()
    expect(connect).to_be_enabled()
    assert page.evaluate("mockTablet.wire.length") == 0
    page.evaluate("mockTablet.cancel = false")
    connect.click()
    expect(page.locator("#web-identity")).to_contain_text("KFTUWI")
    assert page.evaluate("mockTablet.authKeys") == 1

    page.locator("#web-tab-changes").click()
    change_ads(page, "ads-disable", confirm=False)
    assert page.evaluate("mockTablet.writes") == []

    # The owner was selected at preview; a profile switch must invalidate approval.
    page.locator("#web-change-review").click()
    expect(page.locator("#web-confirm")).to_be_enabled()
    page.evaluate("mockTablet.selectedUser = 10")
    page.locator("#web-confirm").click()
    expect(page.locator("#web-message")).to_contain_text("changed")
    assert page.evaluate("mockTablet.writes") == []
    page.evaluate("mockTablet.selectedUser = 0")
    change_ads(page, "ads-disable", confirm=True)
    assert page.evaluate("mockTablet.settings.global.LOCKSCREEN_AD_ENABLED") == "0"
    change_ads(page, "ads-undo", confirm=True)
    assert page.evaluate("'LOCKSCREEN_AD_ENABLED' in mockTablet.settings.global") is False
    print("Passed Chromium USB chooser, RSA authorization, preview, apply and undo.", flush=True)

    if apks:
        page.locator("#web-tab-google").click()
        page.evaluate("(sizes) => mockTablet.filesBySize = sizes", {str(k): v for k, v in SIZES.items()})
        select_real_files(page, apks)
        page.locator("#web-google-review").click()
        expect(page.locator("#web-confirm")).to_be_enabled(timeout=90_000)
        assert page.evaluate("mockTablet.installs") == []
        page.locator("#web-confirm").click()
        expect(page.locator("#web-google-review")).to_be_enabled(timeout=240_000)
        assert page.evaluate("mockTablet.installs") == list(SIZES.values())
        assert page.evaluate("mockTablet.reads") == list(SIZES.values())
        assert "Open Play Store" in page.locator("#web-log").text_content()
        print("Passed all six real APKs through streamed installs and installed-byte readback.", flush=True)
    else:
        print("Skipped real APK installation; supply --apk-dir to include all six audited files.")

    page.locator("#web-tab-changes").click()
    page.locator("#web-action").select_option("ads-disable")
    page.locator("#web-change-review").click()
    expect(page.locator("#web-confirm")).to_be_enabled()
    prior_writes = page.evaluate("mockTablet.writes")
    page.evaluate("mockTablet.unplug()")
    expect(connect).to_be_enabled()
    expect(page.locator("#web-confirm")).not_to_be_visible()
    assert page.evaluate("mockTablet.writes") == prior_writes
    assert not page.evaluate("mockTablet.failures")
    assert not errors, errors
    print("Passed disconnect with an unconfirmed change.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk-dir", type=Path, help="Directory containing the six audited Google APKs")
    args = parser.parse_args()
    apks = audited_files(args.apk_dir) if args.apk_dir else []
    with TemporaryDirectory() as folder, sync_playwright() as playwright:
        site = Path(folder) / "fire-tools"
        subprocess.run([sys.executable, "website/build.py", "--output", str(site)], cwd=REPO, check=True)
        handler = partial(QuietFiles, directory=folder)
        with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            Thread(target=server.serve_forever, daemon=True).start()
            executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
            browser = playwright.chromium.launch(executable_path=executable)
            try:
                run(browser, f"http://127.0.0.1:{server.server_port}/fire-tools/browser.html", apks)
            finally:
                browser.close()
                server.shutdown()


if __name__ == "__main__":
    main()
