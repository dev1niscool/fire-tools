# Fire Toolbox v46 Google APK audit

On November 27, 2026 we compared the Google downloads selected by the Windows version of Fire Toolbox v46 with the checks in Fire Tools. Four APKMirror listings have the same whole-file SHA-256 as the four core files in the v46 Android 11 distribution. Fire Toolbox’s embedded catalog names Codeberg as its source for these archives. We inspected the catalog copies. A local file matching one of these hashes contains the same bytes, wherever it was obtained. [Exact APKMirror listings and file hashes](https://dev1niscool.github.io/fire-tools/apkmirror.html#v46) · [Standalone archive inventory](V46-INVENTORY.md)

## What the original selected

Both supplied mirror ZIPs had SHA-256 `6425d9bb6e1ae231d6bf14865790bd8846075795ac334b6d9f05b5f53cbd47af` and contained a README and the same 98,195,968-byte managed executable, SHA-256 `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079`. We extracted it as data. REA 6.10.1’s managed provider read `PlayServices.InstallGServices` (method `0x060000da`) and `ManageGoogle`. The first method uses the Android major version and the first ABI reported by the tablet. It stages a separate Play Store package after the services bundle, then processes any selected sync adapters. [REA](https://github.com/morluto/rea) · [Install workflow evidence](REA-NOTES.md#installing-google-components)

The following names and versions come from the package manifests inside six checksum-matched services archives from the catalog. APK signatures were checked with Android Build Tools 36 for API 19, 22, 25, 28 or 30 as appropriate. Historical versions serve as reference specimens. [Catalog archive source](https://codeberg.org/JSens1998/GAppsInstaller)

| Android / catalog variant | Account Manager | Services Framework | Play services version and variant | Services archive SHA-256 |
| --- | --- | --- | --- | --- |
| 4 / 32-bit | 3.2.1-203673 | 4.4.2-1289630 | 23.30.13 (000300) | `4848c8c86b835799e255e865c593d5b4418602660e54fce1d932d6826c90a041` |
| 5 / both labels | 5.1-1743759 | 5.1-1743759 | 24.28.35 (020300) | `d567d593188a463c54b9762260c136e6baeb5d4d4d0f9ab446fc876e0052310f` |
| 7 / 32-bit | 7.1.2 | 7.1.2 | 25.20.37 (040300) | `aff4da8a65596ef4f9af8fa56a3916d2e24473d1cffa39016fef66cad9434504` |
| 7 / 64-bit | 7.1.2 | 7.1.2 | 25.20.37 (040400) | `e08d5f1c021a7df4ed090451343695a4a466391b594857173d4e35f1f81f8941` |
| 9 / both labels | 7.1.2 | 9-6957767 | 23.24.14 (100400) | `bfec8b19d091f85fb19c8cdee6452b02b02c566f6f2be82568878b6dd2f1a540` |
| 11 / both labels | 7.1.2 | 10-6494331 | 25.20.37 (150400) | `7fda53ec69acfe7079d49f510bc8b58630449d6f4010b439bc1242b2d950e7bb` |

The separate Store archive has SHA-256 `a9dd7e20b7ed6ab77055f662d2673c6466313ccd789d41bbb4d168856f014e8f` and contains Play Store 36.3.12-21 (minimum API 21). Fire Tools requires API 23 or higher for device changes. Its verification accepted both Android 7 core sets for the matching ARM architectures at API 25. The Android 9 and 11 archives each contain ARM64-primary Play services. Fire Tools accepted the API 28 and API 30 sets on ARM64 and refused them for a 32-bit-only tablet. Check the ABIs in **Connection** when choosing APKs. The additional legacy archives received signature and metadata inspection only. The documented malware scans apply to the six named reference APKs. [File-level scan record](GOOGLE-APKS.md#files-with-a-local-scan-record)

For Android 11, the original Contacts path selects `ConSync10.apk` from an archive with SHA-256 `377c6c068c770e998068d31b1b84f511f42a4190d8076c337aa1711376be5480`. Its manifest reports Calendar Sync 2021.41.2. The separate Calendar attachment on XDA returned HTTP 403, so its bytes remain unverified. Fire Tools accepts each adapter by its signed package ID. For the six-file test we used Google-signed Calendar Sync 2021.23.3 and Contacts Sync 11 from a pinned Open GApps revision. [Adapter links and digests](GOOGLE-APKS.md#files-selected-by-fire-toolbox-46-for-android-11)

## What was exercised

- **Original behavior.** REA inspected the unexecuted executable, and we compared its member selection with the manifests in the checksum-matched downloads. Its ordinary fresh install requests runtime permissions. Fire Tools leaves those permissions for the owner to grant on the tablet.
- **Real files, simulated tablet.** Using six real APKs, official Android Build Tools and a simulated owner-profile HD 10 on Fire OS 8.3.3.8, Fire Tools verified and ordered the inputs, verified the staged copies, and checked all six simulated installed-file readbacks. A second adapter-only preview reverified the simulated existing Google core. Play services’ rotated certificate verified at API 30 with a v3 lineage rooted in the pinned Google key. Android installation, Google login, sync and device certification on physical hardware were outside this exercise.
- **APKMirror.** The distributor describes checking update signatures against previous releases and comparing unfamiliar publishers with independent records. We checked the four exact listing hashes. ClamAV returned zero detections on their matching files and the two separately sourced adapters. A legacy Android bytecode check timed out on Play services and the Store. These results do not assess every file hosted by APKMirror or a later version. [APKMirror FAQ](https://www.apkmirror.com/faq/) · [Scan scope](TESTING.md#antivirus-check-for-the-exact-downloads)

To repeat the original member inspection, point `toolbox` at the extracted executable with the SHA-256 above. The full REA evidence ID for this run was `ev_a966a0a53a59714d4ddc870f4849676d8284c3e1f0ddea58a9dc5521b505dba5`.

```sh
npx --yes rea-agents@6.10.1 inspect-managed-members "$toolbox" \
  --type FireToolbox.PlayServices --type FireToolbox.ManageGoogle \
  --detail summary --evidence_output google.json --json
```

The catalog’s archive hash covers the entire downloaded archive. After extraction, use `aapt dump badging FILE.apk` to read each manifest. Use `apksigner verify --min-sdk-version 30 --max-sdk-version 30 --verbose --print-certs FILE.apk` for an API 30 tablet. Match the whole APK’s SHA-256 separately with the exact download listing. Fire Tools’ **Google Play** verifier applies its pinned publisher policy and checks signer rotation. [Google APK guide](GOOGLE-APKS.md) · [Google’s apksigner reference](https://developer.android.com/tools/apksigner)

For a standalone integrity check in the Fire Tools CLI, set the three variables below to the official local tool paths. This checks Google’s signer for the selected API and displays the APK’s hash record without contacting ADB. The audit also confirmed that a Framework APK requiring API 29 was rejected at API 25.

```sh
python -m open_fire_toolkit --aapt "$aapt" --apksigner-jar "$signer_jar" --java "$java" \
  check-apks --verify-google --sdk 30 file.apk
```
