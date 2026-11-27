# Fire Tools feature expansion

User request: cover the closed-source Fire Toolbox functions and options, especially Google Play, lock-screen ads, and Amazon app removal, and upload to their GitHub repository `fire-tools`. Prior instruction delegates decisions and opts out of questions. Preserve existing source and the existing private repository's visibility.

## Approach

Extend the existing Python/Tk service and CLI with independently implemented ADB workflows. Reuse the reviewed explicit-device, owner-profile, confirmation, locking and verified-APK boundaries. Use REA/static metadata to establish behavior, without executing or copying original binaries, APKs, assets or implementation. A source Android helper can provide an optional on-tablet ad-setting monitor, matching the purpose of the original Automate fallback without distributing Automate.

Alternatives considered: merely document missing features (does not fulfill the request); copy/decompile the original application (fails independent auditable implementation); extend the existing source (chosen). Keep detailed feature coverage and limitations in a matrix instead of claiming untested parity.

## Functional coverage

Package workflows: installed/system/third-party/disabled/uninstalled inventory; multi-select disable/enable, owner uninstall with kept data, install-existing restore; standard/complete/custom debloat lists and undo; cache/data clear and force stop; home launcher/component selection and stock launcher restoration; keyboard enable/default selection; Special Offers package disable/restore; OTA package controls; Google component management and standalone signed APK sideload/update. Preserve core Android settings, System UI, package installer, permission controller, provider infrastructure and ADB connectivity.

Device workflows: settings DB editor and export/import; selected system/privacy/lockscreen/navigation controls; parental-control settings visibility; user list/create/switch/remove; shared-storage push/pull/list; installed APK extraction including splits; package/settings backup and shared-storage backup, honest non-root limitations; screenshots and timed recording; logcat/tasks/force stop; explicit shell tokens; reboot/recovery/bootloader/power off; launcher/keyboard and assistant settings; developer/vendor APK source links for FOSS and hybrid applications.

Source helper: optional Android foreground service, explicitly enabled, visible notification, periodically restores the global ad setting; user can stop/restore. No root or firmware bypass. Package installer and secure-settings permission grant must be explicit. No guarantees of ad visibility or persistence; firmware may deny/ignore/reset the setting or stop the service.

GUI and CLI must expose every implemented workflow, with previews before mutations and exact parameters, warnings and confirmed partial results. Offline demo never starts a tool or reads/writes user files. Existing Google Play signature-pinned workflow remains distinct from generic sideloading whose signer is shown and explicitly selected by the user.

## Boundaries and verification

Python 3.11+, standard library runtime; official user-supplied Google tools. Never run target Toolbox code. No background downloads, telemetry or automatic updater. shell=False and remote token quoting. Every write checks selected device/owner profile immediately before execution; batch operations stop on first failure and report prior successes. Capture original states before batch mutation and provide undo. Refuse ambiguous or destructive paths, unexpected responses, stale previews, untrusted imports and accidental destination overwrite. Operations that may erase data state so in preview. No automatic factory reset or firmware flashing.

Tests use fake ADB devices plus real subprocess/ZIP/GUI boundaries. Test supported and refused cases, actual GUI previews, packaging and clean extracted source. No physical tablet is available; all compatibility limits remain explicit. Publish after review and passing checks; user already authorized publication. Integrate existing remote README/history without force-push; preserve private visibility.
