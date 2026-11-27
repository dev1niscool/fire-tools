# Feature coverage for Fire Tools 0.4.1

This release implements the workflows below in original source. Automated tests exercise their commands, validation and failure handling through simulated tablets; desktop smoke tests exercise their forms and confirmation. No physical Fire tablet has been attached, so **implemented does not mean verified on your firmware**.

The latest [REA comparison](REA-AUDIT.md) traces individual v46 options to their original forms and methods. The [original inventory](PARITY-RESEARCH.md) documents the initial baseline.

## Main feature status

| Area | Implemented | Limits |
| --- | --- | --- |
| Google Play | Offline file hash and Google signer checks for a selected API level, owner-profile component status and verified local installer for the three core Google components, Account Manager and optional Calendar/Contacts sync; generic account/settings and app-management tools; battery exemption | User obtains APKs. No automatic firmware-specific version selection or account credentials handled on the computer. |
| Amazon debloat | Offline comparison of v46 Standard (Recommended) and Complete, owner ADB preview and apply, Restore Everything, saved batch undo, custom Toolbox lists and legacy v0.2 lists | Complete adds 13 apps to Standard’s 22. Fire Tools protects Device Setup, leaving at most 34 eligible targets. Fire OS can refuse changes. [Package comparison](REA-NOTES.md#debloating-amazon-apps) |
| Ads | Setting and Special Offers together with exact undo, setting-only and package-only controls; independent source-built foreground helper | All experimental. Helper requires API 24+, a verified local signing identity, secure-settings grant and visible notification. No ad-visibility or update-persistence guarantee. |
| Apps | Package ID lookup with owner state, version and SDK details, inventory filters, batch operations, clear data, force stop, launch, permission/app-op controls, standalone APK sideload/update, system update rollback | No split APKM/XAPK installation. Guided package management protects infrastructure; expert shell remains powerful. |
| Launcher and keyboard | Select installed HOME/IME, verify replacement before stock launcher disable, restore Fire launcher, widget binding, keys/taps | No original launcher downgrade, Launcher Hijack or exploit-specific workaround reproduction. Firmware can reject defaults. |
| Settings and privacy | Database list/get/change/delete/undo; supported backup/import; display, animation, rotation, timeout, privacy and selected sounds | No guarantee hidden Amazon settings are honored or that telemetry is eliminated. Restore deliberately validates supported portable keys. |
| Lockscreen, wallpaper, parental controls | Explicit tablet Settings entry points; related settings editor | Some actions are shortcuts requiring on-tablet selection. They do not reproduce the original wallpaper/provisioning/parental-hiding companions or bypass authentication. |
| Backups and files | Configuration/package snapshots, supported restore, APK extraction including all splits, shared storage backup, file copy, mkdir/rename/delete | No full firmware/private-app-data image. Restoring a snapshot records the previous states of supported optional apps for `packages-undo`. APK files are separate. |
| Screen and diagnostics | PNG capture, timed silent MP4 recording, task list, battery/memory/storage diagnostics, recent logs, bounded device commands | No screenshot editor, interactive shell history/aliases or continuous log viewer. DRM content can be blank. |
| System updates | Dedicated desktop tab to inspect the two known OTA IDs for owner user 0, review system-package disable/enable and undo the last updater-only batch | Fire OS can protect an updater or use other update routes. Readback verifies package state. [Update guide](https://dev1niscool.github.io/fire-tools/updates.html) |
| Connectivity and network | Host-only connect/disconnect, hardware-checked Wi-Fi changes bound to a live ADB transport, selected-device TCP/USB control, private DNS undo, metering, data saver | No encrypted Android pairing workflow or automatic VPN/certificate setup. Legacy TCP is for trusted private networks. |
| Profiles and power | List/create/switch/remove supported profiles, normal/recovery/bootloader restart, shutdown | Owner/current deletion refused. Device changes and installs use owner user 0; other-profile install management is not reproduced. |
| Optional applications | Upstream source/store directory and verified local sideloading | No original curated automatic FOSS downloads, hybrid Netflix/Disney+ APK modifications or DRM/HD playback promise. |
| Host application | Searchable Tk desktop, command line, offline demo, source helper build, tests and integrity manifests | No original theme catalog, self-updater, driver installer or dependency auto-download. |
| Elevated mode | Ordinary authorized ADB commands | No system-UID exploits, root, firmware flashing, launcher downgrade exploits or signature-check bypass. |

**Full feature-and-option parity is not established.** Menu entries that request a tablet Settings page are labeled accordingly; they are not counted as automated configuration. Every release needs device/Fire OS-specific testing before compatibility can be claimed.

## Complete tool catalog

The original Google Play, temporary-ad-setting and quick-app tabs remain available in addition to this catalog. Use `python -m open_fire_toolkit tools --feature KEY` for current parameters. The GUI uses the same definitions. All non-read tools create a review plan first.

| CLI key | Tool | Group | Parameters |
| --- | --- | --- | --- |
| `packages-inventory` | Browse installed and system apps (read) | Applications | `mode` |
| `package-info` | Inspect an app (read) | Applications | `package` |
| `google-status` | Google Play component status (read) | Google and assistants | None |
| `debloat-presets` | Compare debloat presets (offline) | Amazon apps | None |
| `debloat` | Debloat Amazon apps | Amazon apps | `profile`, `list_file`, `mode` |
| `debloat-restore` | Restore Everything (enable disabled, installed Complete members after preview) | Amazon apps | None |
| `packages-disable` | Disable selected apps | Applications | `packages` |
| `packages-enable` | Enable selected apps | Applications | `packages` |
| `packages-uninstall` | Remove selected apps for owner | Applications | `packages` |
| `packages-restore` | Restore apps removed for owner | Applications | `packages` |
| `packages-undo` | Undo saved package changes | Amazon apps | None |
| `packages-clear-data` | Clear app data | Applications | `packages` |
| `packages-stop` | Force-stop apps | Applications | `packages` |
| `packages-launch` | Launch apps | Applications | `packages` |
| `sideload` | Verify and install local APKs | Applications | `paths`, `signer` |
| `system-update` | Install a system app update | Applications | `packages`, `paths`, `signer` |
| `system-rollback` | Revert system app updates | Applications | `packages` |
| `ads-package-disable` | Disable Special Offers app | Lock-screen ads | None |
| `ads-package-restore` | Enable Special Offers app | Lock-screen ads | None |
| `helper-start` | Set up the on-tablet ad helper | Lock-screen ads | `signer` |
| `helper-stop` | Open helper to stop monitoring | Lock-screen ads | `signer` |
| `helper-restore` | Open helper to restore ad setting | Lock-screen ads | `signer` |
| `ota-status` | Read updater states (read) | System updates | None |
| `ota-undo` | Undo last updater package changes | System updates | None |
| `ota-disable` | Disable update packages | System updates | `packages` |
| `ota-enable` | Enable update packages | System updates | `packages` |
| `launcher-set` | Set an installed home launcher | Launcher and input | `component`, `disable_stock` |
| `launcher-restore` | Restore Fire home launcher | Launcher and input | None |
| `home` | Read current home activity (read) | Launcher and input | None |
| `keyboards` | List installed input methods (read) | Launcher and input | None |
| `keyboard-set` | Select an installed keyboard | Launcher and input | `component` |
| `remote-input` | Send a key or tap | Launcher and input | `kind`, `value` |
| `settings-list` | Read settings database (read) | Settings | `namespace` |
| `settings-get` | Read one setting (read) | Settings | `namespace`, `key` |
| `settings-set` | Change or delete a setting | Settings | `namespace`, `key`, `value` |
| `settings-undo` | Restore a saved setting | Settings | `namespace`, `key` |
| `settings-export` | Export settings snapshot | Backup and restore | `local` |
| `settings-import` | Restore supported settings from snapshot | Backup and restore | `local` |
| `privacy` | Limit usage and advertising settings | Settings | `preset` |
| `navigation` | Navigation and status-bar visibility | Display and sounds | `value` |
| `display` | Screen size and density | Display and sounds | `density`, `size` |
| `timeout` | Screen timeout | Display and sounds | `value` |
| `animation` | Animation speed | Display and sounds | `value` |
| `rotation` | Screen rotation | Display and sounds | `value` |
| `sound` | Notification, alarm or ringtone sound | Display and sounds | `kind`, `value` |
| `wallpaper` | Open tablet wallpaper chooser | Display and sounds | None |
| `lockscreen` | Open tablet security settings | Settings | `mode` |
| `parental-settings` | Open Settings for parental controls | Settings | None |
| `assistant` | Configure installed voice assistant | Google and assistants | `component` |
| `accessibility` | Configure an accessibility service | Settings | `component`, `enable` |
| `users` | List tablet profiles (read) | Profiles | None |
| `user-create` | Create a tablet profile | Profiles | `name` |
| `user-switch` | Switch tablet profile | Profiles | `user_id` |
| `user-remove` | Delete a tablet profile | Profiles | `user_id` |
| `storage-list` | Browse shared storage (read) | Files | `remote` |
| `push` | Copy a file to the tablet | Files | `local`, `remote` |
| `pull` | Copy a file from the tablet | Files | `remote`, `local` |
| `storage-backup` | Copy shared-storage folder | Backup and restore | `remote`, `local` |
| `extract-apk` | Extract installed APK and splits | Backup and restore | `package`, `local` |
| `package-backup` | Export package-state snapshot | Backup and restore | `local` |
| `package-restore` | Restore supported package states | Backup and restore | `local` |
| `backup` | Back up settings and package inventory | Backup and restore | `local` |
| `restore-backup` | Restore supported configuration backup | Backup and restore | `local` |
| `screenshot` | Save a screenshot | Screen and diagnostics | `local` |
| `screenrecord` | Record the screen | Screen and diagnostics | `local`, `seconds` |
| `tasks` | List running processes (read) | Screen and diagnostics | None |
| `logcat` | Read recent device logs (read) | Screen and diagnostics | None |
| `device-stats` | Battery, memory and storage diagnostics (read) | Screen and diagnostics | None |
| `permissions` | Read package details and permissions (read) | Advanced | `package` |
| `grant` | Grant an app permission | Advanced | `package`, `permission` |
| `revoke` | Revoke an app permission | Advanced | `package`, `permission` |
| `appops` | Set an app operation | Advanced | `package`, `op`, `value` |
| `shell` | Run a device shell command | Advanced | `argv` |
| `power` | Restart into system, recovery or bootloader | Power | `mode` |
| `shutdown` | Power off the tablet | Power | None |
| `settings-open` | Open a tablet settings page | Google and assistants | `target`, `package` |
| `battery-exemption` | Change background battery exemption | Google and assistants | `package`, `enabled` |
| `widget-bind` | Allow a launcher to host widgets | Launcher and input | `package`, `enabled` |
| `source-catalog` | FOSS and app source directory (read) | App sources | None |
| `wireless-enable` | Enable legacy Wi-Fi ADB from USB | Connection tools | `port` |
| `wireless-usb` | Return ADB to USB transport | Connection tools | None |
| `wireless-connect` | Connect to an ADB endpoint | Connection tools | `endpoint` |
| `wireless-disconnect` | Disconnect an ADB endpoint | Connection tools | `endpoint` |
| `file-mkdir` | Create a shared-storage folder | Files | `remote` |
| `file-rename` | Rename a shared-storage file or folder | Files | `remote`, `destination` |
| `file-delete` | Delete a shared-storage file | Files | `remote` |
| `network-info` | Read Wi-Fi network metering identifiers (read) | Network | None |
| `private-dns` | Configure private DNS | Network | `mode`, `hostname` |
| `private-dns-undo` | Restore private DNS configuration | Network | None |
| `data-saver` | Toggle background data saver | Network | `enabled` |
| `wifi-metered` | Set a Wi-Fi network metering override | Network | `network_id`, `metered` |
