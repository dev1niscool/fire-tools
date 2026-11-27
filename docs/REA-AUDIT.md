# Fire Toolbox 46 option audit

On November 27, 2026 we compared the Windows Fire Toolbox 46.0 executable with Fire Tools 0.3.2 at commit `5a90a0e`. **Full feature parity is unverified.** For example, Fire Tools can export the base APK and splits reported for an installed app. Its installer accepts standalone APKs. Several original options sit inside a tool that appears in both menus. [Fire Tools feature catalog](FEATURES.md) · [Version 0.3.2 source](https://github.com/dev1niscool/fire-tools/tree/5a90a0e)

REA identified 56 embedded resource sets. One is the shared resource collection. Each of the other 55 names matched a managed type with a form initializer. We inspected all 55 initializers for control captions and choices, then checked selected actions in more detail. A visible caption establishes a design option. Whether it appears on a particular tablet, succeeds on its firmware or survives reboot requires a device test. The comparison used static analysis throughout. [Earlier audit and release provenance](PARITY-RESEARCH.md) · [Google Play, ads and debloat evidence](REA-NOTES.md)

## Changes in Fire Tools 0.4.0

The [APK audit](APK-AUDIT.md) identifies the Google packages selected by six original catalog archives and compares the Android 11 files with APKMirror. Fire Tools can now check individual Google APK signatures offline. The [v46 inventory](V46-INVENTORY.md) covers the embedded APKs and downloadable catalogs. The [USB driver guide](https://dev1niscool.github.io/fire-tools/drivers.html#audit) records which driver file was available for inspection. The new [System updates tab](https://dev1niscool.github.io/fire-tools/updates.html) brings updater states, reviewed changes and undo into one workflow.

## Changes in Fire Tools 0.3.3

| What changed | How to use it |
| --- | --- |
| Wi-Fi device identity | Reviewed changes and recovery records use a digest of the serial reported by the tablet. Confirmed Wi-Fi operations bind to a single live ADB transport and stop if it changes. Older saves tied solely to a Wi-Fi address remain on disk and cannot be attributed to a tablet automatically. [Identity and undo details](../SECURITY.md) |
| Google Play status | Open **Google Play → Component status** to see all six packages and their owner-profile states. An install reports if a selected component remains disabled. Open Play Store on the tablet to check actual sign-in. |
| Per-app inspection | Select a row in **Apps → App details** or enter a package ID in **Tools → Inspect an app**. Fire Tools reports owner state, package type, version and available SDK fields. Per-app storage and cache sizes remain open. |

## What the two tools expose

The middle column describes the audited 0.3.2 release. The last column identifies specific v46 options that release did not expose through the equivalent guided workflow. A shell command, a tablet Settings shortcut and an automated operation are different user experiences. The current release catalog tracks subsequent changes. [Current catalog](FEATURES.md)

| Area and v46 evidence group | Fire Tools 0.3.2 | Additional v46 options observed |
| --- | --- | --- |
| Device information and input · `device` | Model, SDK, ABI, device statistics, key codes and coordinate taps | Search build properties, export or copy the device report, send text, show tap positions, tap an element by displayed text. |
| Screen capture, tasks and logs · `device` | Save PNG, record timed MP4, list processes, read up to 500 recent log entries and force-stop a selected package | Edit after capture, show taps while recording, display per-process RAM, stream and save logs with buffer, package, PID or text filtering. |
| App information and updates · `apps`, `package-detail` | Package inventory, raw package details, permissions, local system-app updates and rollback | Formatted per-app information with size fields, a system-app update list with up-to-date apps hidden and one action to roll back updates across system apps to the versions included in Fire OS. |
| Sideloading · `apps`, `package-detail` | Verify and install local standalone APKs for the owner. Export base and split APKs together. | Choose APKM or XAPK archives and request installation of the contained APK splits, select the target user, launch after installation and choose install flags. |
| Google services and assistants · `google`, `google-detail` | Verify local Google APKs, install optional sync adapters, open account settings, grant a battery exemption, configure an installed assistant | Select downloads for the device, offer Aurora as an alternative, launch the Store at the end and separately offer restart, install Play services for a selected user, or run a guided Assistant installation and restore Alexa. |
| Keyboards, launchers and shortcuts · `launcher` | Choose an installed keyboard or HOME component, restore Fire launcher, control widget binding | Show the input-method switcher, restore the stock keyboard, choose a launcher from a catalog, preview and reset left/right lock-screen activity shortcuts independently. |
| Lock screen and sound · `display` | Open wallpaper/security choosers. Configure notification, alarm and ringtone URIs. | Pick separate home and lock-screen images. For system sounds, v46 names Charging, Docked, Undocked, Low Power, Screen On and Screen Off and offers apply-all and reset-all. |
| Display and system UI · `system`, `hosttools` | Screen size/density, animations, rotation, timeout and status/navigation-bar visibility | Reorder quick-settings tiles, swap Back and Recents, choose left/right alignment, assign individual navigation icons, set night mode, toggle the data-saver icon and adjust portrait/landscape overscan. |
| Settings, privacy and network · `system` | System/secure/global settings, a tracking-limit preset, private DNS, Wi-Fi metering, data saver and Settings links | Browse Android properties, Java properties and the Linux environment, randomize advertising and household IDs independently, change the Appstore automatic-update preference, toggle automatic Wi-Fi. |
| Files, backups and shell · `files`, `backup-detail` | Shared file transfers and folder backup, settings/package snapshots and restore, APK extraction and a bounded device shell command | Search files in the device browser, push a directory, manage restore sets saved on the tablet or computer, select backup contents and optionally lock an archive to the device. The v46 shell also exposes session logging. |
| Profiles, wireless and power · `profiles` | Create a named user, switch/remove users, connect/disconnect legacy Wi-Fi ADB, request reboot/recovery/bootloader/shutdown | User-type choices include restricted, guest and ephemeral. Wireless debugging has a separate pairing-code form. Power options include waiting for reconnection. |
| Apps from other sources · `apps` | An upstream source directory and user-supplied, verified local APKs | The FOSS center groups app install/uninstall actions. The streaming-app form displays installed and server versions for Netflix and Disney+. Playback quality and service availability were untested. |
| Host interface · `host`, `hosttools` | Searchable desktop tools, CLI and offline demo | First-run tour, themes, reorderable main menu, notification inbox, downloaded-file cleanup and relocation, Windows driver setup and an updater with a changelog. |
| Amazon apps, ads and updates · `other` | Standard/Complete lists, custom list import, restore and undo, experimental Special Offers controls and separate OTA package controls | The v46 update form also has an automatic background installation preference. Package-list semantics and the limited evidence for ad persistence are documented separately. [Preset and ads analysis](REA-NOTES.md) |

### Checks beyond menu labels

- **Google Play.** `PlayServices.InstallGServices` (`0x060000da`) launches the Store at IL offset `0x12a3` and offers restart at `0x12ba`. `ManageGoogle.AddorRemoveAcct_DoWork` (`0x060009d8`) opens account management on the tablet. A package-install success message provides no evidence of a signed-in account or a functioning Play Store session. See `google-detail`.
- **App inspection and split APKs.** `ManualAppMgmnt.InfoBtn_Click` (`0x06000b16`) combines Android package metadata with cached per-app size information. The file chooser accepts `.apk`, `.xapk` and `.apkm`. `SideloadApps.ReadSplitAPK` (`0x060017e3`) references `manifest.json`, `info.json` and `base.apk`. `installSplitAPK` (`0x060017e4`) reaches a split-install operation at `0x0271`. Compatibility with individual archives and any additional assets remains untested. Fire Tools 0.3.2's `extract-apk` takes files off the tablet, so successful split extraction establishes only export coverage. See `package-detail`.
- **System-app rollback.** `SysAppUpdater.ResetSystemApps` (`0x06001846`) requests removal of system-app updates at `0x01b3`. Its confirmation describes reverting apps to the versions shipped in the most recent Fire OS update. See `package-detail`.
- **Backup identity.** In `SystemBackup.CreateaBackup` (`0x060018fa`) the device-lock path reads the tablet's boot serial at `0x00b4` and saves it at `0x0161`. `RestoreBackup` (`0x060018fb`) reads the boot serial at `0x01d8`, compares at `0x0243` and aborts a mismatch at `0x026b`. The comparison uses the boot serial reported by the tablet even when its connection address changes. See `backup-detail`.

## Reproduce the audit

We rehashed the retained Google Drive and MEGA archives from the author’s Windows v46 download table. Both ZIPs were 68,741,902 bytes and matched SHA-256 `6425d9bb6e1ae231d6bf14865790bd8846075795ac334b6d9f05b5f53cbd47af`. Each contains the same 98,195,968-byte executable. This identifies the archived downloads. Current mirror availability was not tested. [Release and mirror provenance](PARITY-RESEARCH.md#xda-setup-and-download-provenance)

Verify the executable's SHA-256 is `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079`. REA reported a .NET Framework 4.8 assembly, version 46.0.0.0, MVID `2eea4675-77b8-4dae-bbf5-f6c11c3ca7cf`. The analysis used Node 24.22.3 and the `rea-dotnet-static` v1 provider from REA 6.10.1. [REA source](https://github.com/morluto/rea)

From a fresh output directory, set `toolbox` to the executable's absolute path. This Bash example reproduces the artifact and device-form selections. To inspect another group, change the first argument to its group name and use the types in the table in the stated order.

```bash
sha256sum "$toolbox"
npx --yes rea-agents@6.10.1 inspect-managed-artifact "$toolbox" \
  --detail summary --evidence_output artifact.json --json > artifact-summary.json

members() {
  local group=$1
  shift
  local args=() type
  for type in "$@"; do
    args+=(--type "FireToolbox.$type")
  done
  npx --yes rea-agents@6.10.1 inspect-managed-members "$toolbox" "${args[@]}" \
    --detail summary --evidence_output "$group.json" --json > "$group-summary.json"
}
members device DevInfo KeyandInput ScreenCapture TaskManager LogcatStream
```

The bundle's `records[0].evidence_id` identifies the full record. The summary has its own ID. In `records[0].normalized_result`, use `resources` for the artifact inventory, `methods` for the form initializers and method tokens, and `user_strings.literals` to resolve their loaded text. For example, `KeyandInput.InitializeComponent` is `0x060004de`. For the sound-event list, use `CustomSounds..cctor` (`0x06000389`).

| Group | Type selection, with the common `FireToolbox.` prefix omitted | Full record ID from this run |
| --- | --- | --- |
| `artifact` | Whole managed artifact | `ev_aa0087f806608fa4e2f437017103b75307ae62a3d1dd7e8e813166424a1ccb2e` |
| `menu` | MainMenu | `ev_1f4cdf27a42332161efef9174f7ef642754bce30a5819898c7624d4d32791348` |
| `device` | DevInfo KeyandInput ScreenCapture TaskManager LogcatStream | `ev_b8b8d2bf0155ca3355407e158d2cca31a6fe586eb714da97a577781a0f689b04` |
| `apps` | SideloadApps ManualAppMgmnt ManualSelectApps SysAppUpdater FossCenter HybridApps | `ev_868d92e37495c054821c2bcd180f74f401f0d206881980124aa626dc99037dda` |
| `google` | PlayServices ManageGoogle GoogleAssistant | `ev_a03e12cd08ff47f42f80676c600d3d15d9b2741409b572da04adb2976263b96e` |
| `launcher` | CustomKeyboard CustomLauncher CustomNavbar CustomShortcuts | `ev_8c7d54f9df2d3ef45302b783ce3dfcf6e27e320538836491c706dddb4b9fd60b` |
| `display` | CustomSounds ChangeWallpaper PrimeWallpaper WallChanger ManageWalchanger LockscreenMgmt | `ev_5bca61b8ef50a31c26f2ae910705cb3b1b9b541c166ea28ce8bdd16c262a9a8e` |
| `system` | ModifySys PrivacyControls NetworkSelector SetDBModifier | `ev_3fbb2e4253c335c4e4f4632da139273cddcc084b09bceef4a60e2310c333d1c7` |
| `files` | SystemBackup Pull Adbshell | `ev_7d2f98bdcef9503801c13ea205d54a73a197794c93bbd37cdf6dfe5211754a95` |
| `profiles` | UserManagement PowerOptions DisconnectTCP NoDevice | `ev_28d384b2a35f42db17d47da7a8879e65efd482233cd9f5752644ebd21063c8e6` |
| `host` | Settings SetupTour WelcomeTour Startup FirstStart SplashScreen ApplyTheme AboutBox1 | `ev_127b3856c7c5635766e5f18777bd27971274420492c0fa32e261c0ce77c76b9d` |
| `hosttools` | ToolboxUpdater InstallDrivers InstallDebugger QuickStatus NotificationCenter Webview | `ev_9a5cc982bca5ee46ab608e396ec833b84453352a9bd2549edab904705fe8c81a` |
| `other` | CertificateImporter OTANotify ParentalControl RemoveAds ManageAmazon | `ev_4b044113d8b51f27f59c1a9bfe56d08767a33cea56056bccc26a2bbfa739fd94` |
| `package-detail` | SideloadApps APKInstall ManualAppMgmnt SysAppUpdater | `ev_38bf1e38ca4a244e1a986b52e4f9ff72f7db9804f96e8c1dfd9fa1efea96e49c` |
| `google-detail` | ManageGoogle PlayServices | `ev_313eb0e7ef059ede798395297bc10957715d6d64a38bd04be9abc81063fcbe0f` |
| `backup-detail` | SystemBackup MainMenu NoDevice | `ev_051d709d88e6e03a5e5f616e2a4cb2c5c68b6c89b0fdeac6603c6e3a4ec7ed19` |

All twelve form-group records reported complete managed-member coverage within their selected types. REA reported partial user-string coverage for `system` and `host` because of metadata string flags. Dynamic controls, firmware-dependent paths, nested helpers and the separate Linux edition limit what this inventory can establish. A count of forms cannot measure feature parity. No physical tablet was attached.
