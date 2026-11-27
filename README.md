# Fire Tools

An independent, MIT-licensed desktop and command-line toolkit for Amazon Fire tablets. Install Google Play, manage lock-screen ads, compare debloat presets, and back up settings and files. Version 0.4.0 adds offline Google APK signature checks and a System updates tab. [What the REA review found in Fire Toolbox v46](docs/REA-AUDIT.md)

[Read the Fire tablet field guide](https://dev1niscool.github.io/fire-tools/) for setup, model compatibility and step-by-step tool guides.

This release is designed for Fire tablets running Android API 23 or later. Device changes require the primary adult (owner) profile. Compatibility on a physical tablet, including the Fire HD 10, remains unverified.

## Checking your download

Fire Tools runs from Python source on your computer. Extract the folder containing the launchers. The optional Android helper ships as Java source, and Google apps are separate downloads. Compare your ZIP with the published SHA-256. [Download Fire Tools 0.4.0](https://github.com/dev1niscool/fire-tools/archive/refs/tags/v0.4.0.zip) · [Release notes and ZIP checksum](https://github.com/dev1niscool/fire-tools/releases/tag/v0.4.0) · [Verification record](https://github.com/dev1niscool/fire-tools/blob/main/docs/TESTING.md#apk-and-driver-audit-release-040)

**Before connecting the tablet**, open **Google Play → Choose APKs → Check scan records**. This reads the files locally and shows whether their SHA-256 hashes match files examined in the project audit. The command-line equivalent is `./launch-linux.sh check-apks file.apk` or `.\launch-windows.cmd check-apks "C:\Downloads\file.apk"` in PowerShell. For Google components, use the **Google Play** tab. It checks Google’s signing identity and verifies the installed bytes. The general **sideload** tool also accepts apps from other publishers. [Links to the six scanned builds](docs/GOOGLE-APKS.md#files-with-a-local-scan-record) · [Audit and scan results](docs/TESTING.md)

After setting the AAPT, APK signer and Java paths, choose **Verify Google signatures...** and enter the Android API level reported for your tablet. This also works before connecting a device. [APKMirror audit](https://dev1niscool.github.io/fire-tools/apkmirror.html)

## Common workflows

| Goal | Where to find it | What it does |
| --- | --- | --- |
| Install Google Play | **Google Play** | Verifies locally selected Google components against the pinned Google signing certificate, checks compatibility and installs them in dependency order. |
| Manage firmware updates | **System updates** | Read updater package states, review a disable request and restore changes. A disabled package can delay security patches. Fire OS controls which changes take effect. [Step-by-step guide](https://dev1niscool.github.io/fire-tools/updates.html) |
| Debloat Amazon apps | **Apps → Debloat Amazon apps** | Choose Standard (Recommended), Complete or a custom list. Review the installed targets and skipped packages before disabling or removing apps for the owner. |
| Disable lock-screen ads | **Lock-screen ads** | Temporary setting, Special Offers package disable/restore, or optional [source-built helper](companion/README.md). All depend on firmware; no mode guarantees that ads disappear. |

Removing a system package for the owner does not erase its read-only system image. Restoring it uses the existing package image; a removed third-party app may need its original APK. Debloat previews disclose skipped packages and potential dependencies. Do not select an app you still need.

## More tools

The searchable **Tools** tab exposes installed-app inventory, batch app controls, verified standalone APK sideloading, system-app update/rollback, launcher and keyboard selection, permissions, app operations, settings editing and undo, privacy/display/sound options, configuration backups, APK extraction, file copy, screenshots, recording, logs, profiles, power and connection utilities.

The command line uses the same catalog:

```sh
python -m open_fire_toolkit tools
python -m open_fire_toolkit tools --feature debloat
python -m open_fire_toolkit --demo tool google-status --serial DEMO_FIRE_HD10
python -m open_fire_toolkit --demo tool package-info --serial DEMO_FIRE_HD10 --param package=com.amazon.kindle
python -m open_fire_toolkit tool debloat-presets
python -m open_fire_toolkit --demo tool debloat --serial DEMO_FIRE_HD10 --param profile=recommended
python -m open_fire_toolkit tool source-catalog
```

For a real tablet, put the tool paths before `tool`, include `--serial` from `devices`, and provide the listed `--param key=value` arguments. Mutations default to preview. Review the preview and repeat the command with its printed `--yes --confirm-token TOKEN` arguments. Each token binds the tablet, inputs, targets and state shown by that plan. Source links and Wi-Fi endpoint connection do not require a selected tablet; connecting does not automatically select it.

Some v46 workflows still differ. For example, Fire Tools extracts installed split APKs and accepts standalone APKs for installation. Google APK selection is manual. [REA comparison and remaining differences](docs/REA-AUDIT.md) · [Feature coverage](docs/FEATURES.md) · [Verification](docs/TESTING.md)

## Try the offline demo

Extract the source ZIP. From the extracted directory, run the command for your platform. The demo uses a fictional tablet and sample APK names. It needs no tablet, Android tools, or APK files.

| Windows | Linux |
| --- | --- |
| `launch-windows.cmd gui --demo` | `sh launch-linux.sh gui --demo` |

In PowerShell, prefix the Windows launcher with `.\`. You can also run `python -m open_fire_toolkit gui --demo` using your Python 3.11+ interpreter. On Linux the interpreter is typically named `python3`. Start the regular interface by running the launcher with no arguments.

![Open Fire Toolkit offline demo](docs/images/demo.png)

## Set up a real tablet

1. Install Python 3.11 or later. For the GUI use a Python installation with Tk support. The official Windows installer includes an optional Tcl/Tk component. On Debian or Ubuntu, install `python3-tk` for the distribution's Python. The CLI does not require Tk. [Python downloads](https://www.python.org/downloads/)
2. Download Google's SDK Platform-Tools and extract the entire archive. For Google Play, also install Android SDK Build Tools using the SDK Manager in Android Studio or Google's SDK command-line tools. Use a JDK compatible with your chosen tools. JDK 17 or newer is a practical starting point. The Build Tools 36.0.0 verifier launched with OpenJDK 21 in a local smoke check. Android Studio's bundled runtime is also an option. The toolkit leaves tool and APK downloads to you. [Platform-Tools](https://developer.android.com/tools/releases/platform-tools) · [SDK Manager](https://developer.android.com/studio/command-line/sdkmanager) · [Build Tools](https://developer.android.com/tools/releases/build-tools)
3. On the tablet, open **Settings → Device Options → About Fire Tablet**, tap **Serial Number** seven times, then enable USB debugging under **Developer Options**. Names can vary with Fire OS. Connect a USB data cable, unlock the tablet and approve your computer’s RSA fingerprint in the debugging prompt.
4. In **Connection**, supply the full ADB executable path, choose **Scan devices**, select your tablet, and choose **Use selected tablet**. The view shows its Android API level and supported ABIs. If it reports `unauthorized`, check the prompt on the unlocked tablet. If nothing appears, try a data-capable cable and check your operating system's ADB driver or USB permissions. [USB driver setup and audit](https://dev1niscool.github.io/fire-tools/drivers.html) · [Android USB setup](https://developer.android.com/studio/run/device)

| GUI field | Windows example | Linux example |
| --- | --- | --- |
| ADB | `C:\Android\platform-tools\adb.exe` | `/home/you/Android/Sdk/platform-tools/adb` |
| AAPT | `C:\Android\Sdk\build-tools\36.0.0\aapt.exe` | `/home/you/Android/Sdk/build-tools/36.0.0/aapt` |
| APK signer | `C:\Android\Sdk\build-tools\36.0.0\lib\apksigner.jar` | `/home/you/Android/Sdk/build-tools/36.0.0/lib/apksigner.jar` |
| Java | `%JAVA_HOME%\bin\java.exe` | `$JAVA_HOME/bin/java` |

Substitute your installed SDK version and browse to the actual Java executable in the GUI. To check that your Java can load the signer, run `java -jar /path/to/lib/apksigner.jar version` with the Java executable you plan to select. If using Android Studio's runtime, its Java executable is in the installation's `jbr/bin` directory. ADB alone covers diagnostics, ads, apps and reboot. Google Play verification needs all four paths. [apksigner documentation](https://developer.android.com/tools/apksigner)

## Install Google Play

Start with the **[Google APK download and verification guide](docs/GOOGLE-APKS.md)**. It links individual standalone APKs for the 2023 Fire HD 10 (Fire OS 8, Android 11) and gives each listing’s package ID, Android requirement and published file SHA-256. You can also look up the links in **Tools → FOSS and app source directory**, even before connecting a tablet. Match the API and processor architectures shown in **Connection**.

| Select for installation | Google components |
| --- | --- |
| Core files | Google Services Framework, Google Play services, Google Play Store |
| Additional login component used by the v46 Android 11 bundle | Google Account Manager |
| Optional account sync | Google Calendar Sync, Google Contacts Sync |

1. On the **Google Play** tab, choose the files and review the install plan. The toolkit checks APK structure, package IDs, minimum Android API level, ABI compatibility and signatures. It verifies Google’s signing certificate for the selected Android API. For Play services it also recognizes the verified signing-key rotation found in v46’s Android 11 package. Signer verification establishes signing identity. APK behavior and compatibility with Fire OS still depend on the selected release. [AndroidX certificate reference](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8)
2. Confirm the plan for the displayed tablet. The toolkit rechecks the tablet and verifies the privately staged copies before installation. Installation targets Android user 0 and uses Android’s replace mode to preserve existing app data when updating a package. Installation stops at the first failure and reports completed packages. Earlier successful installs remain in place.
3. Choose **Google Play → Component status** to see which of the six packages are installed and enabled for the owner. The installer also reports if an updated package is still disabled.
4. After a successful install, use **Review reboot** in **Connection** if you want the toolkit to restart the tablet. Then open Play Store on the tablet and sign in there. Amazon does not officially support Google Play on Fire OS. Some apps, sign-in flows, or notifications may fail.

## Lock-screen ads and optional apps

For official Special Offers removal, open **Lock-screen ads** and choose **Open Amazon device settings**. Select your Fire tablet and follow Amazon's paid removal process where available. [Amazon device settings](https://www.amazon.com/mycd)

The basic experimental option writes `LOCKSCREEN_AD_ENABLED=0` once. The firmware may ignore the value or reset it. The toolkit saves the prior value locally before writing and can restore it, including deleting the setting if it was originally absent. Keep the local undo file until you have finished experimenting. [Security and local state](SECURITY.md)

Package mode disables or enables `com.amazon.kindle.kso` and confirms its package state. Firmware may protect it. The optional **Fire Tools Ads Helper** is original Java source, built locally with official Android tools. It needs Android API 24 or later and an explicit secure-settings permission grant. Its visible foreground service reapplies the setting and can stop or restore the original value. Build, verify and install it using the [helper guide](companion/README.md); use the printed signer fingerprint in the desktop helper setup. The helper's setting readback still does not establish actual ad visibility.

To try the v46 package method, open **Lock-screen ads → Suppress with setting and package**. Fire Tools saves both originals, writes the global setting and disables Special Offers for the owner. **Undo setting and package** restores its exact prior package mode and setting, including an originally absent setting. A refused package change can leave the setting changed. Use the same undo after a partial result. If the helper is monitoring the setting, stop or restore it on the tablet first.

For the **Fire HD 10 (13th generation)**, Amazon’s downloadable update page listed **Fire OS 8.3.3.8** on November 27, 2026. Fire Toolbox v46 treats Fire OS 8 builds above 8.3.3.7 as restricted and uses a fallback. On that firmware the package method may be refused and the setting may reset. The official Special Offers removal option is the reliable choice where available. Installing Google APKs is a separate operation. Store sign-in and ad visibility on this firmware still need a physical tablet test. [Amazon software updates](https://digprjsurvey.amazon.com/csad/help/node/G2JXLC4L34GX73TE) · [v46 behavior and XDA sources](docs/PARITY-RESEARCH.md#xda-setup-and-download-provenance) · [REA findings](docs/REA-NOTES.md#suppressing-and-restoring-lock-screen-offers)

## Debloat Amazon apps

Open **Apps → Compare debloat presets** to see every app name and package ID offline. **Standard Debloat (Recommended)** lists 22 packages, including Kindle books, Prime Video, Amazon Music, Amazon Photos and the Mopria Print Service. **Complete Debloat** adds 13, including Silk, Amazon Appstore, Camera, Email and Device Setup. Fire Tools protects Device Setup, so Complete can change at most 34 packages. [All 13 additions and the original v46 evidence](docs/REA-NOTES.md#debloating-amazon-apps)

Select an app in **Apps** and choose **App details** to read its owner state, package type and available version and SDK fields. For any other package ID, use **Tools → Inspect an app**.

In **Apps → Debloat Amazon apps**, choose a preset and select **Review**. Fire Tools uses ordinary ADB on the primary adult profile. Check the installed targets, skipped packages and proposed action before confirming. The default action disables built-in preset apps and keeps their data. To keep an app on the list, use **Tools → Disable selected apps** to pick individual packages. For a custom Toolbox `.debloat` file, **auto** follows `ListType=debloat` (disable) or `ListType=restore` (enable). The CLI accepts `profile=recommended` and `profile=standard` for the same preset. Legacy lists remain available as `standard-v0.2` and `complete-v0.2`.

* **Undo saved package changes** under **Apps** returns each changed package to its saved state from the last batch on that tablet, including an interrupted batch. Use this to keep an app you had already disabled.
* **Restore Everything** under **Apps** previews the installed, disabled members of the Complete preset that Fire Tools can enable. It works without a saved batch and can enable apps you disabled separately. Its CLI preview is `python -m open_fire_toolkit --adb /path/to/adb tool debloat-restore --serial TABLET_SERIAL`.

## CLI examples

The examples use Linux paths. On Windows, use `py -3 -m open_fire_toolkit` and quoted Windows paths. Put tool options before the subcommand. Replace `TABLET_SERIAL` with the exact serial from `devices`.

```bash
python3 -m open_fire_toolkit --help
python3 -m open_fire_toolkit --adb /path/to/adb devices
python3 -m open_fire_toolkit --adb /path/to/adb info --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL --restore
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL --with-package
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL --with-package --restore
python3 -m open_fire_toolkit --adb /path/to/adb apps --serial TABLET_SERIAL --disabled-only
python3 -m open_fire_toolkit --adb /path/to/adb reboot --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb --aapt /path/to/aapt \
  --apksigner-jar /path/to/lib/apksigner.jar --java /path/to/bin/java \
  play --serial TABLET_SERIAL framework.apk play-services.apk play-store.apk
```

The change commands above preview their actions. To apply an action you reviewed, repeat the command with `--yes --confirm-token TOKEN` after its subcommand, using the token printed by that preview. If any reviewed input changes, run a fresh preview. To preview disabling an allowed app, use `apps --serial TABLET_SERIAL --disable com.amazon.mp3`. Use `--enable` to re-enable it.

## Project notes

The source distribution uses the Python standard library and has no runtime PyPI dependencies. See [security and local state](SECURITY.md), [testing](docs/TESTING.md), [REA behavior research](docs/REA-NOTES.md) and the [MIT license](LICENSE).
