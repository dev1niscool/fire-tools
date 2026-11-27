# Testing

From the project root, use Python 3.11 or later. Substitute `py -3` on Windows. The automated suite needs the source tree and standard library.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q open_fire_toolkit tests
python3 -m open_fire_toolkit --help
python3 -m open_fire_toolkit --demo devices
python3 -m open_fire_toolkit --demo info --serial DEMO_FIRE_HD10
```

The test suite includes fake external tools and simulated devices. It exercises device targeting, verifier output and rejection paths, confirmation, staged files, partial failures, settings restore and desktop-worker behavior. Physical tablet behavior and Windows launcher behavior require checks on their respective platforms.

## Desktop smoke test

Run `python3 -m open_fire_toolkit gui --demo` in a desktop session with Tk. On Linux with Xvfb installed, `xvfb-run -a python3 -m open_fire_toolkit gui --demo` can start the GUI on a virtual display. Use an interactive display to follow these steps.

1. Scan for the sample tablet, select it and confirm its model, Android API level and ABI list appear.
2. On **Google Play**, use the sample APK list and review the plan. Cancel one plan and confirm a second plan. Look for simulated progress in the activity log.
3. On **Lock-screen ads**, confirm a simulated setting change, then preview and confirm its restore. On **Apps**, read the app states and preview a single app change.
4. On **Connection**, preview a reboot and check that the review identifies the demo tablet.

## Release archive

Compare the source ZIP with the accompanying checksum before extraction. On Linux use `sha256sum -c fire-tools-0.3.0.zip.sha256` from the directory with the ZIP and its companion checksum file. On Windows use `Get-FileHash .\fire-tools-0.3.0.zip -Algorithm SHA256` in PowerShell and compare the result with the digest in `fire-tools-0.3.0.zip.sha256`. After extraction, the internal `SHA256SUMS` lists every shipped source/document file; run `sha256sum -c SHA256SUMS` inside that extracted project folder. Inspect the ZIP's contents and run the offline demo from the extracted folder.

The checksum verifies that the ZIP matches the checksum you obtained. Obtain both files from a source you trust.

## Fire Toolbox v46 workflow checks (0.3, 2026-11-27)

* **Play installation.** Fire Tools inspected six actual standalone APKs with Android Build Tools 36 and JDK 21 for API 30 on ARM64. The four core files matched the v46 catalog selections by SHA-256. The Calendar and Contacts samples were distinct Google-signed Open GApps files. A simulated ADB device received the six staged and reverified inputs in the reviewed order. Both sync providers were enabled and read back in the simulation. The v46 Play services file passed its v3 signing-key rotation check and was rejected for a 32-bit-only target. The [source guide](GOOGLE-APKS.md) identifies the exact files and marks the newer listing examples separately.
* **Ad controls.** Simulated device tests covered a missing setting, default and explicit Special Offers package modes, firmware refusal after the first write, restart and retry, and undo in the presence of an older saved change. A rendered GUI test performed the paired change and undo. Ad visibility still requires observation on the tablet.
* **Debloat.** Static comparison matched the 22 Standard and 35 Complete preset identifiers. All three custom lists shipped in v46 could be read as data. Tests exercise package protections, restore-list direction and undo after retrying an interrupted batch.
* **Firmware.** Tablet operations in these checks used simulated device responses. Installation, account sign-in, actual ad suppression and persistence through a Fire OS update have not been tested on a physical tablet.

## Expanded release validation (0.2, 2026-11-27)

- The integrated Linux suite passed 212 tests with a JDK available, with no skips. Python compilation and whitespace checks passed. These tests include simulated device responses and do not establish physical-tablet compatibility.
- Both rendered Tk smoke scripts passed under Xvfb: `tests/gui_smoke.py` and `tests/gui_expanded_smoke.py`. The expanded script visits all 85 catalog forms, tests parameter capture, selection, package picking, previews, cancellation, read-only output, source links without a tablet, and connection-only plans. Simulation does not access hardware or save screenshots to the selected user path.
- The controller independently verified the final API-24 helper with real Google `aapt` and `apksigner` through the product's verifier. The signed test artifact SHA-256 was `748557ca7c4120d83c100dc1543ae791d7d387a7b2c4418fefabdab127b9a563`; its test-key signer was `c1d6a57d46c25e365898e368fcd482587b56a08fdfb30f3ff098fea7351e2d2d`. This is test evidence, not a fingerprint users should trust for their own separately signed builds.
- Helper tests exercise its Java state logic on the host; SDK build/signature checks do not exercise Android lifecycle, notifications, boot behavior, permission grant or actual ad visibility.
- [GitHub Actions run 46046662331](https://github.com/dev1niscool/fire-tools/actions/runs/46046662331) passed on Linux and Windows with Python 3.11 and 3.13 at commit `d2a6d5b`. Each Linux job passed all 212 tests; each Windows job passed with 16 explicitly POSIX-only cases skipped. All four jobs also passed compilation, the offline CLI demo and source archive generation. These hosted checks do not exercise a physical tablet or the Windows desktop GUI.
- Reviews and fix evidence are retained in `docs/reviews/parity-*.txt`. They include tests for partial mutations, stale previews, journal preservation, endpoint validation, output-directory replacement and helper permission provenance.
- No physical Fire tablet, Google account login, live Wi-Fi ADB endpoint or Android helper runtime was tested. Full feature-and-option equivalence with the original is not established; see [coverage and limits](FEATURES.md).

## Earlier release validation (0.1, 2026-11-27)

- All 76 automated tests passed in the 0.1 source tree. Python compilation and whitespace checks passed. Independent reviews closed all reported findings for that version; these are code-review results, not malware certification.
- The Tk UI was exercised in an isolated Xvfb display, including error recovery, cancelled and confirmed previews, ad restore, app enable/disable and reboot in clearly labeled demo mode. Repeat with `python3 tests/gui_smoke.py` in a display, or `xvfb-run -a python3 tests/gui_smoke.py`.
- Google's Build Tools 36.0.0 and OpenJDK 21 verified and parsed a real signed Automate 1.51.1 APK as a test specimen. A modified copy was rejected by apksigner. Neither the APK nor its bundled executables were executed or included in this release. This validates the tool integration, not Google Play compatibility.
- Build Tools archive SHA-1 matched the value in Google's HTTPS SDK repository manifest: `b0b6376977657e8ad9b969bacf4093601da2c6fb` for `build-tools_r36_linux.zip`.
- The signed test specimen SHA-256 was `5782cf0fa6db321a3f0de1bc6d1ce6eaea2ecf9c25e7d4b3f20a4d1eb39941fb`. Tests operate on local inputs; they do not download or distribute that specimen.
- Google Platform-Tools 37.0.3 (`adb` 1.0.41) was also exercised through the real CLI device-listing path. It correctly reported no connected devices. Its archive SHA-1 matched Google's HTTPS manifest (`e1579b288a7ae4e9bc28dedec6a154d78b3c04ed`). No tablet command was issued.
- No physical Fire tablet, actual Google account sign-in, ad visibility/persistence, Windows runtime, or Windows GUI was tested. These are release limitations, not passing checks.

Run `python3 scripts/package_release.py` to recreate the deterministic source archive. The builder reads the exact paths in `release-files.txt` and checks that each input exists. When adding a distribution file, review its contents and add its repository-relative path to that inventory. The archive includes the inventory, fixed timestamps, an internal SHA-256 manifest and an external ZIP checksum. A checksum is integrity evidence, not malware certification.
