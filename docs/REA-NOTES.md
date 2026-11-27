# REA behavior research

The analysis used [REA by morluto](https://github.com/morluto/rea), as requested, through its published `rea-agents` CLI.

The reference was Fire Toolbox 46.0, a managed Windows assembly targeting .NET Framework 4.8. The inspected file's SHA-256 is `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079`. The static inspection used `rea-agents@6.10.1` with provider `rea-dotnet-static` version 1. The original executable remained unexecuted.

The targeted review found no clear signs of password theft or hidden Windows startup behavior. The original updater obtains its download address and expected checksum from the same remotely maintained manifest. Later downloads fall outside this review. In a fresh ClamAV scan with expanded archive limits, both the original ZIP and the enclosed executable returned zero malware detections. One legacy Android check timed out on each. [Original mirror hashes](PARITY-RESEARCH.md#xda-setup-and-download-provenance) · [Scan coverage and limits](TESTING.md#original-windows-download)

| Static inspection | Evidence ID |
| --- | --- |
| Managed artifact metadata | `ev_aa0087f806608fa4e2f437017103b75307ae62a3d1dd7e8e813166424a1ccb2e` |
| `FireToolbox.PlayServices` and `FireToolbox.RemoveAds` member inspection | `ev_d149bd46546e1af69b6168a97edad59e2dae5631c3e81a464905a5d42b80aa36` |
| `FireToolbox.Utils` member inspection | `ev_d75a75c7191de63779456ee5500f730214d6de23b7860b6c15de650b4b2a7a48` |

The [follow-up REA audit](REA-AUDIT.md) covers the original form inventory, device-locked backups, app inspection and Google setup.

## Observations

- `FireToolbox.PlayServices.InstallGServices` (MethodDef `0x060000da`) constructs an Android-version-specific staging path and orders Google Account Manager, Google Services Framework, Google Play services and Google Play Store. It passes APKs to a helper one by one and checks the result. The inspected workflow also has additional sync adapter paths and a Store launch path.
- `FireToolbox.Utils.InstallAPK` (MethodDef `0x06001dc7`) checks package presence and has several ADB package install paths. Helper support for install flags establishes the helper's capabilities. The flags selected by callers depend on the branch.
- `FireToolbox.RemoveAds.ToggleAds` (MethodDef `0x0600155c`) includes writes to the Android global setting `LOCKSCREEN_AD_ENABLED`. Some branches reference the Special Offers package. A message describes the fallback setting change as temporary and likely to revert.

The observations informed package ordering and the experimental settings workflow. The toolkit implementation is original Python under the MIT license. The initial 0.1 release used local APK inputs with signature verification and a single reversible ad-setting write. Version 0.2 adds the workflows documented in [FEATURES.md](FEATURES.md), including package-based ad controls and the independent source-built helper. Reference binaries, bundled assets, APKs, and raw REA outputs are outside the toolkit distribution. Static inspection establishes the behavior present in the inspected assembly. Hardware compatibility and ad persistence require separate device tests.

The production signing certificate pinned for the Google APKs has SHA-256 `f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`. [AndroidX source](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8) · [Independent apksigner transcript](https://github.com/spytrap-org/spytrap-adb/issues/34)

## Reproducing the v46 workflow comparison

The follow-up inspection selected all four relevant forms in one REA query. Set `toolbox` to the Windows executable with the SHA-256 above and choose a new evidence file. The full evidence record from this run is `ev_99a179be63afd5bad8ba9e2c03e9eae0deec1eca16d9cf135430440da823df76` (provider `rea-dotnet-static` v1). Method tokens below identify rows in this assembly. Supplemental static CIL inspection resolved branch destinations and array sizes. Archive inspection and Android Build Tools supplied the APK observations.

```sh
npx -y rea-agents@6.10.1 inspect-managed-members "$toolbox" \
  --type FireToolbox.PlayServices --type FireToolbox.ManageGoogle \
  --type FireToolbox.RemoveAds --type FireToolbox.ManageAmazon \
  --detail summary --evidence_output "$PWD/workflows-v46.json" --json
```

### Installing Google components

`PlayServices.InstallGServices` (`0x060000da`) selects a services bundle using the Android major release and the tablet’s first reported ABI. It looks up the separate Store download, stages the files and issues an install request per APK. Its Google path reserves the first four positions for Account Manager, Services Framework, Play services and Play Store. The Calendar and Contacts checkboxes append optional adapters. Their branches also request that Android enable the corresponding calendar or contacts content provider. The method inspects install output, requests battery exemptions for Google packages, launches the Store and offers a reboot. `ManageGoogle.InstallAdditional_DoWork` (`0x060009ef`) handles additional components later.

The call to `Utils.InstallAPK` passes the tablet user ID. For a fresh installation on its ordinary modern path, v46 requests Android’s grant-runtime-permissions install flag. When a package already exists, the helper also has an install-existing branch for the selected user. Fire Tools targets the adult owner, verifies the local APK and uses Android’s replacement install to preserve existing app data. Its default leaves the app’s runtime permission prompts under the owner’s control.

For Android 11 the catalog embedded in v46 points both architecture labels to the same services archive. The archive records below were downloaded from the catalog’s Codeberg repository and matched the corresponding embedded SHA-256 checksums. These are historical inputs that make the original install path reproducible. Use the README’s package listings to choose a release for your tablet. [Reference archive repository](https://codeberg.org/JSens1998/GAppsInstaller) · [Fire Tools setup](../README.md#install-google-play)

| Catalog input | Verified archive SHA-256 |
| --- | --- |
| Android 11 services | `7fda53ec69acfe7079d49f510bc8b58630449d6f4010b439bc1242b2d950e7bb` |
| Play Store | `a9dd7e20b7ed6ab77055f662d2673c6466313ccd789d41bbb4d168856f014e8f` |
| Contacts sync variants | `377c6c068c770e998068d31b1b84f511f42a4190d8076c337aa1711376be5480` |

Google Build Tools 36.0.0 `aapt dump badging` and `apksigner verify --verbose --print-certs` identified the following signed members. Minimum API and package identity come from the APK. None of these applications were installed or launched for this inspection.

| Original file | Declared package | Reported version | Minimum API |
| --- | --- | --- | --- |
| `AccountMgr7-X32.apk` | `com.google.android.gsf.login` | 7.1.2 | 23 |
| `ServicesFramework11-X64.apk` | `com.google.android.gsf` | 10-6494331 | 29 |
| `PlayServices11-X64.apk` | `com.google.android.gms` | 25.20.37 (150400-766884605) | 30 |
| `Playstore.apk` | `com.android.vending` | 36.3.12-21 | 21 |
| `ConSync10.apk` | `com.google.android.syncadapters.calendar` | 2021.41.2-406147485-release | 30 |

Two details affect compatibility. The services APK reports `arm64-v8a` as its primary ABI. It contains a smaller set of `armeabi-v7a` libraries that AAPT reports as `alt-native-code`. Its effective signer on API 30 has SHA-256 `7ce83c1b71f3d572fed04c8d40c5cb10ff75e6d87d9df6fbd53f0468c2905053`. Android’s verifier accepted its v3 signature with the SDK range restricted to 30. Reading that APK’s signing lineage with `apksigner lineage --in FILE --print-certs` shows the Google production key pinned above as the first signer and this rotated key as the second. The other four inspected members report the pinned key as their APK signer.

The original Android 11 Contacts branch selects the file named `ConSync10.apk`. The actual file in the checksum-matched archive declares **Calendar Sync**. Installing that file cannot supply the Contacts adapter package. Choose adapters by their declared package IDs. The catalog's separate XDA Calendar download returned HTTP 403 during inspection, so its content remains unverified.

### Suppressing and restoring lock-screen offers

`RemoveAds.ToggleAds` (`0x0600155c`) uses the global `LOCKSCREEN_AD_ENABLED` setting (0 to suppress, 1 to re-enable) and a device-dependent package operation on `com.amazon.kindle.kso`. The restoration branch selects the matching enable/unhide command. Ordinary package branches also contain package-data clears and permission changes. The method warns that a failed package disable can leave only temporary suppression. A separate branch for restricted firmware uses an on-tablet Automate flow. Its restore prompt asks the owner to stop the flow before restoring the setting. Supplemental inspection of `MainMenu.CheckOSVer` found that v46 routes Fire OS 8 version numbers above 8.3.3.7 to the restricted path. This describes v46’s decision for that release family. Ad visibility and persistence on later firmware require a device test.

Fire Tools provides the ordinary setting and package controls and an independent foreground helper. Setting undo restores the recorded original value, including its absence. Stop or restore the helper before undoing a desktop change so a running monitor cannot reapply the setting. Clearing package data and granting unrelated permissions are outside these ad actions. [Lock-screen ads](../README.md#lock-screen-ads-and-optional-apps)

### Debloating Amazon apps

The XDA opening post identifies the Windows v46 archive, and its FAQ documents firmware protections. REA 6.10.1 inspected the `FireToolbox.ManageAmazon` type in that executable (static evidence `ev_c6af80f50b6194fe50b620e4d489ac5b0f32c391ff68233d3f990579ed16964c`). The preset names and package membership below come from the selector and worker in that build. [Archived XDA thread](https://web.archive.org/web/20261108011721/https://xdaforums.com/t/windows-linux-tool-fire-toolbox-v46-0.3889604/)

The Windows v46 selector calls the options **Standard Debloat (Recommended)** and **Complete Debloat**. The text shown by `ManageAmazon.ComboBox1_SelectedIndexChanged` (`0x06000808`) mentions IMDb TV under Standard, and Fire Keyboard and Fire Launcher under Complete. The worker that actually chooses package IDs, `ManageAmazon.AutoDisHide_DoWork` (`0x060007f6`), puts IMDb TV in Complete only and omits both the keyboard and launcher from both presets. Fire Tools follows the worker’s package IDs. [Fire Tools package catalog](../open_fire_toolkit/package_catalog.py)

**Standard** has 22 entries. It covers Kindle books and the Kindle Store, Prime Video and Personal Videos, Amazon Music and Music, Photos and its importer, Amazon Shopping, Maps, News, Weather, Device Dashboard, Help, Mayday Sharing (Kindle Connect), the Alexa YouTube app, Amazon Games (GameCircle), Audible, Goodreads, WPS Office, Washington Post and Mopria Print Service. For a labeled package-by-package list, run `python -m open_fire_toolkit tool debloat-presets` without a tablet.

**Complete** contains those same 22 plus the 13 below. The default action disables the eligible installed packages for the owner. Keeping Device Setup protected limits Fire Tools to 34 possible changes. The preview identifies which apps your tablet actually has.

| App added by Complete | Android package ID |
| --- | --- |
| Alexa app | `com.amazon.dee.app` |
| Amazon Appstore | `com.amazon.venezia` |
| Amazon Kids (FreeTime) | `com.amazon.tahoe` |
| Calculator | `com.android.calculator2` |
| Calendar | `com.android.calendar` |
| Camera | `com.android.camera2` |
| Clock | `com.android.deskclock` |
| Contacts | `com.android.contacts` |
| Device Setup (protected in Fire Tools) | `com.amazon.kindle.otter.oobe` |
| Documents | `com.amazon.zico` |
| Email | `com.android.email` |
| IMDb TV | `com.amazon.imdb.tv.mobile.app` |
| Silk Browser | `com.amazon.cloud9` |

In v46, **Restore Everything** selects Complete and sets the worker to enable or unhide packages (`ManageAmazon.ComboBox2_TextChanged`, `0x06000807`). This reaches apps disabled before the last debloat. Fire Tools’ **Restore Everything** previews the installed, disabled and unprotected members of Complete for owner user 0. **Undo saved package changes** instead reads the states Fire Tools saved for the last batch on that tablet. It can restore an interrupted batch while preserving apps that were already disabled. [How to use the debloater](../README.md#debloat-amazon-apps)

`ReadDebloatFile_DoWork` (`0x06000801`) reads the custom list, previews the described packages and chooses disable or enable from its declared list type. `LineContainsSpecial` (`0x06000803`) separates metadata and notes from package entries, and `CustomDebloat_DoWork` (`0x06000804`) applies the selected operation. The three distributed example lists use one package ID per line and a `ListType=debloat` directive. In two examples the directive is the **last** line. Caret-prefixed descriptions, hash comments, plus-prefixed display text, empty lines, trailing spaces and Windows or Unix newlines are relevant when importing an existing list. A restore list requests re-enabling the named packages. Fire Tools also records prior package states for undo. [Feature coverage](FEATURES.md)
