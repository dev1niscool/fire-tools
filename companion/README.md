# Fire Tools Ads Helper

This optional Android app is an experimental way to keep the global `LOCKSCREEN_AD_ENABLED` setting at `0` on a Fire tablet. Fire OS can ignore the value, change how it uses the setting, deny the ADB grant, or stop the service. The app reports setting readback and service state. Actual lock-screen behavior depends on the tablet and firmware.

## Build from source

Install Python 3.11+, a JDK (17 or 21), and the official Android SDK Platform and Build Tools. The default build uses Android Platform 36 and Build Tools 36.0.0. From the toolkit root, run:

```sh
python scripts/build_ads_helper.py --sdk /path/to/android-sdk --java-home /path/to/jdk --output companion/build/fire-tools-ads-helper.apk
```

Use `--android-api` and `--build-tools-version` to select installed versions. The compile platform must be API 28 or newer. The app targets SDK 28 to use the Android 9 foreground service contract on Fire OS. The companion requires Android 7.0 (API 24) or newer because its foreground service relies on Android's public app notification availability check. The desktop toolkit supports API 23 tablets. Android manages the notification channel on Android 8 and newer and the notification consent prompt on Android 13 and newer.

The script builds offline, verifies the signature and APK alignment, and prints the output path, APK SHA-256, and signing certificate SHA-256. It creates a new APK path on a filesystem that supports hard links. The first development build generates a local signing key at `companion/build/ads-helper-development.p12`. Keep it private and retain it for updates signed with the same certificate. A fixed development password makes the file's access controls important. Local signing and build timestamps can change the bytes across builds.

To use your own existing signing keystore, pass `--keystore /path/to/keystore.p12 --key-alias ALIAS`. The Android signing tool prompts for the required passwords. In an unattended build, add `--storepass-env NAME` or `--keypass-env NAME` with the names of environment variables holding the passwords. APKs, signing keys, and SDK dependencies are built or supplied locally.

## Install and enable

With official `adb`, approved USB debugging and the Fire tablet's owner profile, select your tablet serial from `adb devices -l` and substitute it for `SERIAL` below.

```sh
adb -s SERIAL install --user 0 companion/build/fire-tools-ads-helper.apk
adb -s SERIAL shell pm grant --user 0 org.firetools.adshelper android.permission.WRITE_SECURE_SETTINGS
adb -s SERIAL shell am start --user 0 -n org.firetools.adshelper/.MainActivity
```

On the tablet, allow helper notifications if Android asks, then tap **Enable**. The first check saves the original value or records that the setting was absent. While the foreground service runs, it checks the value every four seconds and when the screen turns on. Android can coalesce or delay background work. After a reboot, the service attempts to resume after normal boot completes if you enabled it and the grant is still present. Android or Fire OS may require you to open the app and tap **Enable** again.

**Stop** in the app or its notification turns off the service and preserves the saved setting. **Restore** stops enforcement and restores the saved value or deletes the entry if it was originally absent. Use **Restore** before revoking the grant or uninstalling. Uninstalling or clearing app data erases the saved original value.

```sh
adb -s SERIAL shell pm revoke --user 0 org.firetools.adshelper android.permission.WRITE_SECURE_SETTINGS
adb -s SERIAL shell pm uninstall --user 0 org.firetools.adshelper
```

## Manifest and data

The launcher is `org.firetools.adshelper/.MainActivity`, the sole exported component. It accepts on-device button input for all setting changes. The service and boot receiver are private components. `WRITE_SECURE_SETTINGS` permits writing the setting and requires the separate ADB grant above. `FOREGROUND_SERVICE` permits the service and `RECEIVE_BOOT_COMPLETED` permits an enabled service to resume. `POST_NOTIFICATIONS` lets Android 13 or newer request consent to show the foreground notification. The service checks whether the app's notifications and its channel are enabled before enforcing the setting and stops if it detects a block.

The app saves only its enabled state, last status, and original setting in private Android app storage. Android backup is disabled. The manifest grants no network access, and the app contains no telemetry or credentials.
