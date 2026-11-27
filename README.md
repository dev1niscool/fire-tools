# Open Fire Toolkit

An independent, open-source desktop and command-line toolkit for Amazon Fire tablets. It verifies and installs locally supplied Google Play APKs, previews a reversible lock-screen setting change, and provides device diagnostics, optional-app controls and a normal restart.

This release is designed for Fire tablets running Android API 23 or later. Device changes require the primary adult (owner) profile. Compatibility on a physical tablet, including the Fire HD 10, remains unverified.

## Try the offline demo

Extract the source ZIP. From the extracted directory, run the command for your platform. The demo uses a fictional tablet and sample APK names. It needs no tablet, Android tools, or APK files.

| Windows | Linux |
| --- | --- |
| `launch-windows.cmd gui --demo` | `./launch-linux.sh gui --demo` |

In PowerShell, prefix the Windows launcher with `.\`. You can also run `python -m open_fire_toolkit gui --demo` using your Python 3.11+ interpreter. On Linux the interpreter is typically named `python3`. Start the regular interface by running the launcher with no arguments.

![Open Fire Toolkit offline demo](docs/images/demo.png)

## Set up a real tablet

1. Install Python 3.11 or later. For the GUI use a Python installation with Tk support. The official Windows installer includes an optional Tcl/Tk component. On Debian or Ubuntu, install `python3-tk` for the distribution's Python. The CLI does not require Tk. [Python downloads](https://www.python.org/downloads/)
2. Download Google's SDK Platform-Tools and extract the entire archive. For Google Play, also install Android SDK Build Tools using the SDK Manager in Android Studio or Google's SDK command-line tools. Use a JDK compatible with your chosen tools. JDK 17 or newer is a practical starting point. The Build Tools 36.0.0 verifier launched with OpenJDK 21 in a local smoke check. Android Studio's bundled runtime is also an option. The toolkit leaves tool and APK downloads to you. [Platform-Tools](https://developer.android.com/tools/releases/platform-tools) · [SDK Manager](https://developer.android.com/studio/command-line/sdkmanager) · [Build Tools](https://developer.android.com/tools/releases/build-tools)
3. On the tablet, open **Settings → Device Options → About Fire Tablet**, tap **Serial Number** seven times, then enable USB debugging under **Developer Options**. Names can vary with Fire OS. Connect a USB data cable, unlock the tablet and approve the debugging prompt for your computer.
4. In **Connection**, supply the full ADB executable path, choose **Scan devices**, select your tablet, and choose **Use selected tablet**. The view shows its Android API level and supported ABIs. If it reports `unauthorized`, check the prompt on the unlocked tablet. If nothing appears, try a data-capable cable and check your operating system's ADB driver or USB permissions. [Android USB setup](https://developer.android.com/studio/run/device)

| GUI field | Windows example | Linux example |
| --- | --- | --- |
| ADB | `C:\Android\platform-tools\adb.exe` | `/home/you/Android/Sdk/platform-tools/adb` |
| AAPT | `C:\Android\Sdk\build-tools\36.0.0\aapt.exe` | `/home/you/Android/Sdk/build-tools/36.0.0/aapt` |
| APK signer | `C:\Android\Sdk\build-tools\36.0.0\lib\apksigner.jar` | `/home/you/Android/Sdk/build-tools/36.0.0/lib/apksigner.jar` |
| Java | `%JAVA_HOME%\bin\java.exe` | `$JAVA_HOME/bin/java` |

Substitute your installed SDK version and browse to the actual Java executable in the GUI. To check that your Java can load the signer, run `java -jar /path/to/lib/apksigner.jar version` with the Java executable you plan to select. If using Android Studio's runtime, its Java executable is in the installation's `jbr/bin` directory. ADB alone covers diagnostics, ads, apps and reboot. Google Play verification needs all four paths. [apksigner documentation](https://developer.android.com/tools/apksigner)

## Install Google Play

Obtain standalone APKs you are legally entitled to use from a source you trust. APKMirror's listings show Android version and architecture for each variant. Choose a single **APK** variant for each package and skip split APKs, APK bundles and formats such as `.apkm` and `.xapk`. Match the tablet's Android API level and at least one supported ABI when an APK contains native libraries.

| APK | Package | Install order |
| --- | --- | --- |
| [Google Account Manager](https://www.apkmirror.com/apk/google-inc/google-account-manager/) | `com.google.android.gsf.login` | First if supplied |
| [Google Services Framework](https://www.apkmirror.com/apk/google-inc/google-services-framework/) | `com.google.android.gsf` | Required |
| [Google Play services](https://www.apkmirror.com/apk/google-inc/google-play-services/) | `com.google.android.gms` | Required |
| [Google Play Store](https://www.apkmirror.com/apk/google-inc/google-play-store/) | `com.android.vending` | Required |

1. On the **Google Play** tab, choose the files and review the install plan. The toolkit checks APK structure, package IDs, minimum Android API level, ABI compatibility and signatures. It verifies that every reported signer matches the pinned Google certificate. Signer verification establishes signing identity. APK behavior and compatibility with Fire OS still depend on the selected release. [AndroidX certificate reference](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8)
2. Confirm the plan for the displayed tablet. The toolkit rechecks the tablet and verifies the privately staged copies before installation. Installation targets Android user 0 and uses Android’s replace mode to preserve existing app data when updating a package. Installation stops at the first failure and reports completed packages. Earlier successful installs remain in place.
3. After a successful install, use **Review reboot** in **Connection** if you want the toolkit to restart the tablet. Then open Play Store on the tablet and sign in there. Amazon does not officially support Google Play on Fire OS. Some apps, sign-in flows, or notifications may fail.

## Lock-screen ads and optional apps

For official Special Offers removal, open **Lock-screen ads** and choose **Open Amazon device settings**. Select your Fire tablet and follow Amazon's paid removal process where available. [Amazon device settings](https://www.amazon.com/mycd)

The experimental option writes `LOCKSCREEN_AD_ENABLED=0` once. The firmware may ignore the value or reset it. The toolkit saves the prior value locally before writing and can restore it, including deleting the setting if it was originally absent. This feature has no persistent automation. Keep the local undo file until you have finished experimenting. [Security and local state](SECURITY.md)

The **Apps** tab reads the current state of a small set of optional Amazon apps. Select one and review a disable or enable plan. Disabling leaves the package and its data on the tablet.

## CLI examples

The examples use Linux paths. On Windows, use `py -3 -m open_fire_toolkit` and quoted Windows paths. Put tool options before the subcommand. Replace `TABLET_SERIAL` with the exact serial from `devices`.

```bash
python3 -m open_fire_toolkit --help
python3 -m open_fire_toolkit --adb /path/to/adb devices
python3 -m open_fire_toolkit --adb /path/to/adb info --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb ads --serial TABLET_SERIAL --restore
python3 -m open_fire_toolkit --adb /path/to/adb apps --serial TABLET_SERIAL --disabled-only
python3 -m open_fire_toolkit --adb /path/to/adb reboot --serial TABLET_SERIAL
python3 -m open_fire_toolkit --adb /path/to/adb --aapt /path/to/aapt \
  --apksigner-jar /path/to/lib/apksigner.jar --java /path/to/bin/java \
  play --serial TABLET_SERIAL framework.apk play-services.apk play-store.apk
```

The change commands above preview their actions. To apply an action you reviewed, repeat the command with `--yes` after its subcommand. To preview disabling an allowed app, use `apps --serial TABLET_SERIAL --disable com.amazon.mp3`. Use `--enable` to re-enable it.

## Project notes

The source distribution uses the Python standard library and has no runtime PyPI dependencies. See [security and local state](SECURITY.md), [testing](docs/TESTING.md), [REA behavior research](docs/REA-NOTES.md) and the [MIT license](LICENSE).
