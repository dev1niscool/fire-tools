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

The GitHub release page provides the checksum for GitHub’s tagged source ZIP. If you build the separate source-only distribution using `scripts/package_release.py`, compare that ZIP with the accompanying checksum before extraction. On Linux use `sha256sum -c fire-tools-0.6.1.zip.sha256` from the directory with the ZIP and its companion checksum file. On Windows use `Get-FileHash .\fire-tools-0.6.1.zip -Algorithm SHA256` in PowerShell and compare the result with the digest in `fire-tools-0.6.1.zip.sha256`. After extraction, the internal `SHA256SUMS` lists every shipped source/document file; run `sha256sum -c SHA256SUMS` inside that extracted project folder. Inspect the ZIP's contents and run the offline demo from the extracted folder.

On macOS, run `shasum -a 256 fire-tools-0.6.1.zip` to display the download hash. On macOS and Linux, use an archive utility that preserves executable permissions, such as `unzip`, when running launcher tests. Start Fire Tools with `sh launch.sh` if the archive utility did not preserve permissions.

The checksum verifies that the ZIP matches the checksum you obtained. Obtain both files from a source you trust.

## F-Droid client verification

The official download served F-Droid 2.0.3 (version code 2000053), package `org.fdroid.fdroid`, for Android 7.0 (API 24) or later. Its file SHA-256 was `dac55a0d17b1edf7e7286b48cfbd70c7c52fbb32a00af062c68830a437c47959`. The download URL follows new releases, so a newer version will have a different file hash. [Official APK](https://f-droid.org/F-Droid.apk) · [F-Droid package listing](https://f-droid.org/packages/org.fdroid.fdroid/)

Android Build Tools verified the APK’s v2 and v3 signatures with the single signing certificate F-Droid publishes, SHA-256 `43238d512c1e5eb2d6569f4a3afbf5523418b82e0a3ed1552770abb9a9c9ccab`. The detached OpenPGP signature also verified under F-Droid’s published release key. ClamAV 1.5.5 scanned this file with 3,628,228 signatures and reported zero detections. [F-Droid signing keys](https://f-droid.org/docs/Release_Channels_and_Signing_Keys/) · [How to check a download independently](https://f-droid.org/docs/Verifying_Downloaded_APK/)

## Personal Google APK bundle

On November 28, 2026, all four files in the private Android 11 ARM64 pack matched the whole-file SHA-256 values on the exact APKMirror listings, 298,757,952 bytes in total. Their signed manifests and Google signing identities passed the Android Build Tools 36.0.0 check at API 30, including the signing key rotation for Play services. The same checks passed on the two separate optional Open GApps sync adapters. [Builds, sources and hashes](GOOGLE-APKS.md#files-with-a-local-scan-record)

The repeated scan with ClamAV 1.5.5 and 3,628,228 official signatures returned zero detections on all six files. One legacy Android bytecode check timed out on Play services and Play Store. Results apply to those exact APK files. Physical Fire tablet operation and Google sign-in remain unverified.

## Comparison release 0.5.0

The macOS 15 runner passed the isolated launcher check. Its filesystem did not supply the stable directory handles Fire Tools requires for device changes and recovery journals. Windows and Linux are the supported tablet-management hosts. [Native macOS diagnostic](https://github.com/dev1niscool/fire-tools/actions/runs/46084012866)

The [Hayden Fire-Tools review](HAYDEN-REVIEW.md) identifies the exact source and release artifacts examined. All 343 application tests and six handbook tests passed locally. Two Linux Tk runtimes exercised the rendered desktop. The folder installer was also checked with real Android Build Tools and a simulated tablet. A reference split APK and its multi-file APKM were refused. All six signed Google component APKs passed the dedicated installer’s staged verification and simulated installed-byte checks. The [release notes](https://github.com/dev1niscool/fire-tools/releases/tag/v0.5.0) record the published source ZIP checksum, scan and verification results.

## Code review release 0.4.1

The review covered APK inspection, device selection, shared-storage uploads, package and settings undo, and the optional Android helper. Tests simulated switching tablets during a selection or readback, an equal-length upload with different bytes, and a system app with both an active update and an older factory record. The desktop now clears the active tablet when the selection changes. Uploads read the staged file back over ADB to verify its SHA-256 before moving it into place. This adds one return transfer for each upload.

Tests also covered an active custom launcher whose stock fallback could no longer open, ambiguous Wi-Fi names, and misidentified split APK metadata. Android Build Tools 36 and JDK 21 verified all six reference Google APKs at API 30. The published handbook, updated package filters, and compact desktop workflows were exercised separately.

On Linux with JDK 21, all 324 application tests and six handbook tests passed. Both desktop smoke tests passed on Tk 8.6 and Tk 9.0. Bandit 1.9.4 reported zero medium or high findings in the Python application and build scripts. An Android 14 Robolectric test verified that dismissing the helper notification stops monitoring and keeps the saved value available for Restore. No physical Fire tablet was used.

The release notes give the SHA-256 of the exact published source ZIP and its antivirus scan result. [0.4.1 release and checksum](https://github.com/dev1niscool/fire-tools/releases/tag/v0.4.1)

## APK and driver audit release 0.4.0

All 303 application tests and six handbook tests passed on Linux with JDK 21 available. Both rendered desktop smoke tests passed. The System updates tab was also exercised on Tk 8.6 and 9.0 at 680 × 660. A simulated tablet accepted a reviewed disable request and returned to its saved state on undo. Tests covered all five Android owner modes, including a disabled system default, firmware refusal partway through a batch, a package replaced with a non-system app, and refusal to undo an unrelated app batch from this tab. No physical tablet or firmware update was used.

Bandit reported zero medium or high findings in the Python application and build scripts. The offline Google signature checker accepted all six reference APKs at API 30 and rejected a modified APK and a Framework build on an API below its minimum. It authenticated the Play services signing-key rotation without connecting to ADB. The Windows driver checks used extracted files on Linux. Current Windows driver acceptance remains untested.

The [APK catalog audit](APK-AUDIT.md) records the selected releases, signer checks and simulated installation. The [Windows archive inventory](V46-INVENTORY.md) distinguishes embedded files from separately fetched software. The [driver audit](https://dev1niscool.github.io/fire-tools/drivers.html#audit) gives the Amazon files examined and the limits for the original XDA attachment. The tagged source ZIP’s SHA-256 and verification results are on the [0.4.0 release](https://github.com/dev1niscool/fire-tools/releases/tag/v0.4.0).

## REA audit release 0.3.3

On Linux with JDK 21, all 285 application tests, five handbook checks and both rendered desktop smoke scripts passed. They covered selection, preview and confirmation when a Wi-Fi address changes hands, same-tablet recovery across USB and Wi-Fi, owner-scoped Google status and package inspection. A read-only ADB fixture also exercised the CLI with a disabled Play Store and an updated system app. Tests used simulated tablet responses. Physical installation, account sign-in and ad visibility remain unverified.

The [comparison with Fire Toolbox v46](REA-AUDIT.md) identifies the reviewed original by SHA-256 and gives the REA commands and method references. GitHub’s Windows and Linux [source checks](https://github.com/dev1niscool/fire-tools/actions/runs/46074238406) passed on Python 3.11 and 3.13. At the implementation commit, ClamAV 1.5.5 loaded 3,628,228 official signatures and reported zero detections or warnings on the [repository ZIP](https://github.com/dev1niscool/fire-tools/archive/bde8cc83f5dc84155fc2da8f6b470f1775405d45.zip) (SHA-256 `5680787dd05ec5757cd1934ca3c2478e74da0120749196e376b6e038d06fc871`). All 109 files matched Git. The separate source-only ZIP built from the same commit also had zero detections or warnings (SHA-256 `a172f8ce6b99a09716e83ddd10172089368051b1b6350cfdd3880c8481892351`). All 285 application tests passed from the extracted source-only ZIP.

For the user-facing tagged GitHub source ZIP, compare its SHA-256 with the checksum on the [0.3.3 release](https://github.com/dev1niscool/fire-tools/releases/tag/v0.3.3).

### Original Windows download

We rehashed both previously downloaded v46 mirror copies. The Google Drive and MEGA archives had the same SHA-256, `6425d9bb6e1ae231d6bf14865790bd8846075795ac334b6d9f05b5f53cbd47af`. Their Windows executables both matched `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079`. REA inspected that executable as data.

ClamAV 1.5.5 and 3,628,228 official signatures returned zero malware detections on the ZIP and on the executable scanned separately. With limit alerts enabled, 200,000 nested files, 32 archive levels, 512 MiB per inner file and 2 GiB per target, the earlier nested-file warning did not recur. One legacy Android bytecode check exceeded its 60-second allowance on each scan. The outcome covers these specific downloads. Future updater payloads and behavior on a physical tablet were outside the scan. [Mirror provenance](PARITY-RESEARCH.md#xda-setup-and-download-provenance) · [Original updater observations](REA-NOTES.md)

## Fire Toolbox debloat preset checks (0.3.2, 2026-11-27)

The 0.3.2 desktop release passed 260 local tests with a JDK and both rendered GUI smoke tests. We compared all 106 files in the published GitHub ZIP with the tested checkout. ClamAV 1.5.5 loaded 3,628,228 official signatures and reported zero detections or warnings for that ZIP (SHA-256 `e28e13f1682660830411e7adc8704803da757064cffa435a73e7af7da0249630`) and the source archive from the release builder (SHA-256 `0d54c96423359c6d325d35e415a1040fa8232f052cc254fbe25220dba67413c2`). [Scanned GitHub download](https://github.com/dev1niscool/fire-tools/archive/43eaeac695623313fc5ba8afbd6c3a1751854633.zip) · [Hosted Windows and Linux checks](https://github.com/dev1niscool/fire-tools/actions/runs/46072924367)

We compared the ordered package IDs in both copies of the v46 worker's Standard and Complete arrays with the published Fire Tools catalog. All 22 Standard and 35 Complete entries matched in order. With every listed app installed and enabled on a simulated tablet, Standard requested 22 owner disables and Complete requested 34, skipping protected Device Setup. [Preset comparison and source methods](REA-NOTES.md#debloating-amazon-apps)

The CLI and rendered desktop checks exercised offline comparison, preview, cancel, apply, Restore Everything and saved undo. In a mixed inventory, Restore Everything re-enabled a previously disabled Calendar and left owner-removed, protected and unrelated packages alone. Undo returned Calendar to its saved disabled state. Interrupted batches created by the older 0.3.1 planner resumed under 0.3.2 and retained their original undo targets. These checks used simulated ADB responses. Package protection and results on a physical Fire tablet depend on firmware.

## Desktop and tablet safety audit (0.3.1, 2026-11-27)

ClamAV 1.5.5 scanned two copies of Fire Tools 0.3.1 with 3,628,228 official signatures and reported zero detections or warnings. The ZIP downloaded back from GitHub matched all 86 tracked files at commit `312709c` byte for byte. The source ZIP from the project's release builder had SHA-256 `3255c56f94c5fcdcbb62ca2a42248f53c0c16b4011f14b88e7dfad34d35177fe`. [Audited source](https://github.com/dev1niscool/fire-tools/tree/312709c2bc93df00500232a5c8aa02e43cd46b4e)

The Linux suite passed all 245 tests and both rendered GUI checks. Hosted checks passed on Windows and Ubuntu with Python 3.11 and 3.13. Each Windows job skipped 16 POSIX-specific tests. [GitHub Actions results](https://github.com/dev1niscool/fire-tools/actions/runs/46057334928)

| What was checked | Result |
| --- | --- |
| Desktop startup, application imports, and child processes | Review found no hidden downloads, telemetry, credential collection or PC startup service. The runtime uses Python’s standard library. Source launchers start an already installed Python in isolated mode. ADB, the SDK tools and the Java installation are separate executables selected by the user. |
| Static analysis | Bandit 1.9.4 scanned all 18 Python application and build-script files. It reported zero high or medium issues. Review of its eight low findings traced seven to subprocess imports and explicit tool calls, and one to a variable containing the name of a password environment variable. |
| Local APK check | The CLI matched all six previously scanned files by SHA-256. The GUI identified a real Account Manager file with no tablet connected or Android tools configured. An unknown hash has no scan verdict. |
| Google installer | All six actual APKs passed Google signature verification, staging and installed-byte readback using a simulated tablet. The installer checks the package ID and signer of core apps already installed when adding sync adapters. A sync provider must be a system app before Fire Tools enables it. |
| Optional ads helper | An offline build using Android Build Tools 36 and JDK 21 produced a v3-signed APK with SHA-256 `549e619e8110685b395a471a382ca43ccfd2800481e5fb02c001a11b6900c0e0`. ClamAV 1.5.5 reported zero detections with main 63, daily 28194 and bytecode 339, with no scanner warnings. The compiled APK contained the project’s Java classes, no native libraries and no internet permission. The on-tablet helper holds a secure-settings permission and can resume its visible service at boot when enabled. Its desktop controls verify the installed file and user-supplied signer before opening it. Each locally signed build has its own hash. |
| Packaging | The source distribution includes the reviewed source paths, documentation, tests and demo image. The helper APK, private signing key, SDK tools and external Google APKs are excluded. GitHub Actions uses read-only repository permissions and pins its actions to specific commits. |

The [Google APK guide](GOOGLE-APKS.md#files-with-a-local-scan-record) links the exact files used in testing. Of the six APKMirror listings in its alternate table, Account Manager and Framework match locally scanned files. The other four listings were checked for package, signer and published file hashes. We could not retrieve those exact four APKs from the download pages for a local malware scan. An external tool or an APK update obtained later needs its own checks. Physical-tablet execution and Google account sign-in remain untested.

We repeated the Play services and Play Store scans with archive-limit alerts enabled. Play services exceeded the default file-count limit. Raising the limit to 200,000 let ClamAV examine 755.98 MiB of expanded content with no archive-limit alert. Both APKs returned zero malware detections. One legacy Android check timed out on both files even with four minutes allowed for that check. Fire Tools shows this limitation when a selected file matches either hash.

## Fire Toolbox v46 workflow checks (0.3, 2026-11-27)

* **Desktop checks.** All 233 tests passed on the local Linux host with JDK 21, including after extracting the source archive. Both GUI smoke tests passed. [GitHub Actions on the implementation commit](https://github.com/dev1niscool/fire-tools/actions/runs/46055332880) passed on Windows and Ubuntu with Python 3.11 and 3.13.
* **Play installation.** Fire Tools inspected six actual standalone APKs with Android Build Tools 36 and JDK 21 for API 30 on ARM64. The four core files matched the v46 catalog selections by SHA-256. The Calendar and Contacts samples were distinct Google-signed Open GApps files. A simulated ADB device received the six staged and reverified inputs in the reviewed order. Both sync providers were enabled and read back in the simulation. The v46 Play services file passed its v3 signing-key rotation check and was rejected for a 32-bit-only target. The [source guide](GOOGLE-APKS.md) identifies the exact files and marks the newer listing examples separately.
* **Ad controls.** Simulated device tests covered a missing setting, default and explicit Special Offers package modes, firmware refusal after the first write, restart and retry, and undo in the presence of an older saved change. A rendered GUI test performed the paired change and undo. Ad visibility still requires observation on the tablet.
* **Debloat.** Static comparison matched the 22 Standard and 35 Complete preset identifiers. All three custom lists shipped in v46 could be read as data. Tests exercise package protections, restore-list direction and undo after retrying an interrupted batch.
* **Firmware.** Tablet operations in these checks used simulated device responses. Installation, account sign-in, actual ad suppression and persistence through a Fire OS update have not been tested on a physical tablet.

### Antivirus check for the exact downloads

On November 27, 2026, ClamAV 1.5.5 reported zero detections for the four original Google APKs selected by Toolbox v46 for Android 11 and the two Google-signed Open GApps sync adapters used in the six-file test. It also reported zero detections for the Fire Tools 0.3 source archive built at commit `2cfedd0` (ZIP SHA-256 `42cf1f59efe4624cbe2a46772de3d4cfad9e290efa2952c69af8657a672630b5`). The scanner loaded official main 63, daily 28194 and bytecode 339 databases.

One legacy Android bytecode check timed out on Play services and Play Store. The scanner completed its other checks and reported those two files as OK. The [Google APK guide](GOOGLE-APKS.md#files-selected-by-fire-toolbox-46-for-android-11) gives the exact file hashes and distinguishes newer alternatives checked only against their download listings. These results apply to the scanned bytes. The package-signature, signer-lineage and compatibility checks run again on the APKs you actually choose.

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
