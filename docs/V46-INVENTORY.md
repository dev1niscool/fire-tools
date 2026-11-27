# What ships in the Windows Fire Toolbox v46 download

We unpacked both retained mirror downloads on November 27, 2026. Each contained a README and the same Windows executable. Its embedded tools archive contains **11 APKs**. Google Account Manager, Google Services Framework, Google Play services and Play Store are separate downloads selected by the original program. [XDA release post](https://xdaforums.com/t/windows-linux-tool-fire-toolbox-v46-0.3889604/#post-78664542) · [Google Drive mirror](https://drive.google.com/file/d/1TFPVXdBFwqJqS41WUP29PrvBa0fvCV4B/view) · [MEGA mirror](https://mega.nz/file/3V0iFKQD#8r-Ak5le0SFpOTM6f8izTamz28cZjhBWy6p3lUR3VWg)

## Files identified

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Either mirror ZIP | 68,741,902 | `6425d9bb6e1ae231d6bf14865790bd8846075795ac334b6d9f05b5f53cbd47af` |
| Fire Toolbox V46.0.exe | 98,195,968 | `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079` |
| README.txt | 2,485 | `67d7d09079966477124a6b478a072cfdb762cbcc09d79b8edd61af5f247bf873` |
| Embedded `bin` ZIP | 38,180,558 | `b3397c994635b39a8876695911cf1291eb56b5c1acaa19fdc2dfb239b9a14643` |

We used REA 6.10.1 to inspect the managed assembly without loading it. REA counted 611 type definitions and 10,405 method definitions. Its resource table contains 55 form resource sets and one shared resource set. All 56 extracted resource digests matched REA’s record. The shared set’s SHA-256 was `caca2019f9a45a9e2aa2eb11c4219dcd2ad656f33915dd8ffd095ac748268087`. Across them we counted 143 bitmaps, 51 icons, 21 strings and three byte arrays. The arrays contain the tools ZIP, a 7-Zip executable and a Newtonsoft.Json library. The tools ZIP has 159 files and 52 directory entries. It includes six Windows executables and four DLLs, images, sounds, package lists, three debloat lists and automation files. Its ADB host executable and companion DLLs are distinct from the separately fetched Windows USB driver. The embedded ZIP lists no INF, CAT or SYS driver files. [REA source](https://github.com/morluto/rea) · [55-form feature comparison and reproduction commands](REA-AUDIT.md)

## APKs embedded in the original executable

Android Build Tools 36.0.0 read the manifest package ID and version from all 11 files. All passed `apksigner verify` for Android API 30. This establishes that the APK signatures verified for that platform. We did not independently authenticate each publisher, install the APKs or exercise their behavior. For example, the package inside `GAssist.apk` identifies a third-party assistant helper. The four core Google installer inputs are covered by the [Google APK comparison](GOOGLE-APKS.md#files-selected-by-fire-toolbox-46-for-android-11).

| Embedded filename | Manifest package ID | Manifest version | File SHA-256 |
| --- | --- | --- | --- |
| `AmazonDebugger.apk` | `com.amazon.unifiedsharefacebook` | 5.0.8.0-UnifiedShareFacebook-Debug_500001800 | `118620409c10c7444bcbf1fea8e146b41d4a63b08d7e34f73658e560c0210ab9` |
| `AnySoftKeyboard.apk` | `com.menny.android.anysoftkeyboard` | 1.10.1109 | `10b868ee840bf2b27a398be35a68c8761845036a6c5189b81052a3c8ec2af9c4` |
| `Automate.apk` | `com.llamalab.automate` | 1.51.1 | `5782cf0fa6db321a3f0de1bc6d1ce6eaea2ecf9c25e7d4b3f20a4d1eb39941fb` |
| `FireLauncher.apk` | `com.amazon.firelauncher` | 1.0.1004.0_319710 | `412991fc2f142c13242e8a909caa94ef2ef8fc57070b4ab1aea05999c2310e24` |
| `GAssist.apk` | `com.hybridevelopers.assistant` | 1.0.4 | `acfe2535a1e2f73de074fe72e0409a25a9bdaa4eb1d2ea8277b753b741395546` |
| `LauncherHijack.apk` | `com.baronkiko.launcherhijacl` | 4.0.3 | `976dffad515c11be05c69f0554cb2fce9d0285d14e65e4b1cadbf9299d2e2bf7` |
| `NovaLauncher.apk` | `com.teslacoilsw.launcher` | 6.2.12 | `af460530037bff61af7e42e6fe680d0ad83d012addf9c789eef23e110e5917fd` |
| `ParentalControlHide.apk` | `me.raffy909.parentalcontrolhide` | 1.0 | `f763ff0c95712c498c17081f8c77c76175f74817c94288f5a009cebddb5929b3` |
| `SettingsPerm.apk` | `com.llamalab.automate.ext.settings` | 1.0.3 | `62ca18a2aec20a0687d7de739aed7d791e6b02436e01619a86b6c7fb69415aa0` |
| `StoragePerm.apk` | `com.llamalab.automate.ext.storage` | 1.0 | `1b0d96cbf4ab236e224d8c7f141bb467ce338c5790788dc41af9e4d6a9e13342` |
| `Wallchanger.apk` | `com.wall.changer` | 1.5 | `ffe873c970472714290c22a99e9c301145fe38f88509e9ce373a763bc3edac48` |

ClamAV 1.5.5 scanned these 11 extracted APKs individually with 3,628,228 official signatures. It reported 11 files scanned, zero detections and no archive-limit alerts. One legacy Android bytecode check exceeded its 60-second allowance. These results cover the exact hashes above.

## What the catalogs can download

These are entries present in the original executable. Catalogs overlap, and their contents can change after release. A URL in a catalog establishes a possible source. It cannot establish which file a person later received or installed.

| Original resource | Contents |
| --- | --- |
| `Downloads` | 24 named entries covering Google packages, the Windows ADB driver, Aurora Store, launchers, keyboards, RethinkDNS, Netflix and Disney+. The two nested groups produce 40 leaf entries in total. The nine entries under `google_app` have empty URL and checksum fields in this catalog. |
| `FossApps` | 13 entries for 12 package IDs. The entries cover App Lock, App Manager, Aurora Store, Droid-ify, F-Droid and its legacy build, FreeTube Android, LibreTube, Material Files, NewPipe, PipePipe, SkyTube and SmartTube. The listed download hosts are GitHub, F-Droid and Aurora’s website. |
| `CustomKeyboards` | 10 named keyboards. Fire Keyboard has no download URL. Seven entries point to GitHub, and two point to the Internet Archive. |
| `SystemUpdates` | 33 system **app** update records, including Amazon System WebView, Kindle, Silk and Special Offers. All 33 download URLs point to Google Drive. Fire OS firmware updates are a separate operation. |

The original Play services catalog includes selections labeled Android 4, 5, 7, 9 and 11, with some 32-bit and 64-bit selections sharing the same archive. For the HD 10’s Android 11 path, the embedded links for the Google service archive and Play Store point to Codeberg. The Android 11 comparison identifies the four exact core APKs whose file hashes also matched APKMirror listings. Its optional Contacts download contained a Calendar package. Fire Tools verifies the package declared by each selected APK and the permitted Google signer before offering installation. [Android 11 file and signing records](GOOGLE-APKS.md) · [Original workflow inspection](REA-NOTES.md)

The original’s keyboard, streaming and launcher catalogs also reference GitHub, XDA, Google Drive, F-Droid and the Internet Archive. Fire Tools ships its own Python and optional Android helper source. Users supply their platform tools and APKs separately. No driver or APK from this Windows executable is included in the Fire Tools source distribution. [Fire Tools distribution inventory](../release-files.txt) · [Source and trust boundaries](../SECURITY.md)

The archive and its executable returned zero detections in the recorded ClamAV 1.5.5 scans. A legacy Android check timed out on each scan. The findings cover the supplied Windows distribution, its embedded files and its catalog records. Later downloads and hardware-dependent behavior require separate checks. [Exact original scan coverage](TESTING.md#original-windows-download)
