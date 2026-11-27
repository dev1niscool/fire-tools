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

Compare the source ZIP with the accompanying checksum before extraction. On Linux use `sha256sum -c open-fire-toolkit-0.1.0.zip.sha256` from the directory with the ZIP and its companion checksum file. On Windows use `Get-FileHash .\archive.zip -Algorithm SHA256` in PowerShell and compare the result with the digest in `open-fire-toolkit-0.1.0.zip.sha256`. After extraction, the internal `SHA256SUMS` lists every shipped source/document file; run `sha256sum -c SHA256SUMS` inside that extracted project folder. Inspect the ZIP's contents and run the offline demo from the extracted folder.

The checksum verifies that the ZIP matches the checksum you obtained. Obtain both files from a source you trust.

## Recorded validation (2026-11-27)

- All 76 automated tests passed in the final source tree. Python compilation and whitespace checks passed. Independent reviews closed all reported findings; these are code-review results, not malware certification.
- The Tk UI was exercised in an isolated Xvfb display, including error recovery, cancelled and confirmed previews, ad restore, app enable/disable and reboot in clearly labeled demo mode. Repeat with `python3 tests/gui_smoke.py` in a display, or `xvfb-run -a python3 tests/gui_smoke.py`.
- Google's Build Tools 36.0.0 and OpenJDK 21 verified and parsed a real signed Automate 1.51.1 APK as a test specimen. A modified copy was rejected by apksigner. Neither the APK nor its bundled executables were executed or included in this release. This validates the tool integration, not Google Play compatibility.
- Build Tools archive SHA-1 matched the value in Google's HTTPS SDK repository manifest: `b0b6376977657e8ad9b969bacf4093601da2c6fb` for `build-tools_r36_linux.zip`.
- The signed test specimen SHA-256 was `5782cf0fa6db321a3f0de1bc6d1ce6eaea2ecf9c25e7d4b3f20a4d1eb39941fb`. Tests operate on local inputs; they do not download or distribute that specimen.
- Google Platform-Tools 37.0.3 (`adb` 1.0.41) was also exercised through the real CLI device-listing path. It correctly reported no connected devices. Its archive SHA-1 matched Google's HTTPS manifest (`e1579b288a7ae4e9bc28dedec6a154d78b3c04ed`). No tablet command was issued.
- No physical Fire tablet, actual Google account sign-in, ad visibility/persistence, Windows runtime, or Windows GUI was tested. These are release limitations, not passing checks.

Run `python3 scripts/package_release.py` to recreate the deterministic source archive. The archive uses explicit file allowlists, fixed timestamps, an internal file manifest, and an external ZIP checksum. A checksum is integrity evidence, not malware certification.
