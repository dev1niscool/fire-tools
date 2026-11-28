(() => {
  "use strict";

  // Stock families documented in the handbook's model and firmware tables.
  const models = [
    { id: "hd10-2023", label: "Fire HD 10 (2023, 13th generation)", families: [8] },
    { id: "hd10-2021", label: "Fire HD 10 / HD 10 Plus (2021, 11th generation)", families: [7] },
    { id: "hd10-2019", label: "Fire HD 10 (2019, 9th generation)", families: [7] },
    { id: "hd10-2017", label: "Fire HD 10 (2017, 7th generation)", families: [5] },
    { id: "max11-2023", label: "Fire Max 11 (2023, 13th generation)", families: [8] },
    { id: "hd8-2024", label: "Fire HD 8 (2024, 12th generation)", families: [8] },
    { id: "hd8-2022", label: "Fire HD 8 / HD 8 Plus (2022, 12th generation)", families: [8] },
    { id: "hd8-2020", label: "Fire HD 8 / HD 8 Plus (2020, 10th generation)", families: [7] },
    { id: "hd8-2018", label: "Fire HD 8 (2018, 8th generation)", families: [6, 7] },
    { id: "hd8-2017", label: "Fire HD 8 (2017, 7th generation)", families: [5] },
    { id: "fire7-2022", label: "Fire 7 (2022, 12th generation)", families: [8] },
    { id: "fire7-2019", label: "Fire 7 (2019, 9th generation)", families: [6, 7] },
    { id: "fire7-2017", label: "Fire 7 (2017, 7th generation)", families: [5] },
    { id: "legacy", label: "Fire or Kindle Fire tablet from 2016 or earlier", families: [1, 2, 3, 4, 5] },
    { id: "unknown", label: "Other model or not sure", families: [] },
  ];

  const goals = [
    { id: "play", label: "Install Google Play", description: "Get the Play Store and its required Google components." },
    { id: "debloat", label: "Debloat Amazon apps", description: "Review preinstalled apps and disable the ones you choose." },
    { id: "ads", label: "Remove lock-screen ads", description: "Check Amazon’s removal option and Fire OS limits." },
    { id: "updates", label: "Manage firmware updates", description: "Inspect the updater and review what can be disabled." },
    { id: "animations", label: "Speed up animations", description: "Shorten menus and transitions on the tablet." },
    { id: "backup", label: "Back up settings", description: "Save a copy of settings and the installed-app list." },
    { id: "sideload", label: "Install other APKs", description: "Review and install a folder of standalone Android apps." },
    { id: "dns", label: "Set up Private DNS", description: "Choose an encrypted DNS provider on Android 9 or newer." },
  ];

  const apiLevels = { 6: 25, 7: 28, 8: 30 };
  const link = (label, href) => ({ label, href });
  const section = (id, title, intro, steps, check, links) => ({ id, title, intro, steps, check, links });

  function restrictionNotice(parts, firmware) {
    const [major, minor, patch, build] = parts;
    const boundary = major === 8 ? [3, 3, 8] : [3, 2, 2];
    if (major !== 7 && major !== 8) return "";
    if (parts.length < 4) return "Read the full build in System Updates to check restrictions on protected packages. ";
    const digits = [minor, patch, build];
    for (let i = 0; i < boundary.length; i++) {
      if (digits[i] === undefined || digits[i] < boundary[i]) return "";
      if (digits[i] > boundary[i]) break;
    }
    return "Toolbox v46 flags Fire OS " + firmware + " for restrictions on protected packages. ";
  }

  const computer = section("computer", "Open Fire Tools on your computer",
    "Use a Windows or Linux computer and a USB data cable for tablet changes. The macOS launcher supports offline tools.",
    ["Download the Fire Tools source ZIP from the project release. Compare its SHA-256 with the release notes and extract it.",
      "Install Python 3.11 or newer with Tcl/Tk. On Debian or Ubuntu, the Tk package is python3-tk.",
      "Open a terminal in the extracted folder. On Windows PowerShell run .\\launch-windows.cmd. On Linux run sh launch.sh.",
      "Download and extract Google’s SDK Platform-Tools. In Fire Tools → Connection → ADB, browse to adb.exe (Windows) or adb (Linux)."],
    "The regular Fire Tools window is open and the ADB field points to the extracted executable.",
    [link("Download the source ZIP", "https://github.com/dev1niscool/fire-tools/archive/refs/tags/v0.6.0.zip"),
      link("Published checksum", "https://github.com/dev1niscool/fire-tools/releases/tag/v0.6.0"),
      link("How to check the hash", "https://github.com/dev1niscool/fire-tools/blob/v0.6.0/docs/TESTING.md#release-archive"),
      link("Download Python", "https://www.python.org/downloads/"),
      link("Download Platform-Tools", "https://developer.android.com/tools/releases/platform-tools"),
      link("Launcher instructions", "setup.html#desktop")]);

  const usb = section("usb", "Allow your computer to connect",
    "Start on the unlocked tablet in the primary adult profile.",
    ["Open Settings → Device Options → About Fire Tablet and tap Serial Number seven times.",
      "Return to Device Options → Developer Options. Turn on Developer Options and USB debugging (also called Enable ADB).",
      "Connect the USB data cable. On the computer, choose Connection → Scan devices. Approve the debugging prompt for your own computer on the tablet."],
    "After scanning again, your tablet’s row says “device”. If it says “unauthorized”, unlock the tablet and check the prompt.",
    [link("USB setup", "setup.html#usb"), link("Missing tablet or driver", "drivers.html")]);

  function connect(model, firmware, api) {
    return section("connect", "Select the tablet you’re holding",
      "Your choices point to " + model.label + " with Fire OS " + firmware + ". Check what the tablet actually reports.",
      ["In Connection, highlight your tablet’s serial and choose Use selected tablet.",
        "Read the model, Fire OS, Android SDK and ABIs (supported processor types). Write down the SDK and ABI list for this session.",
        "Check for User 0 and SDK " + api + ". If the model, version or SDK differs, go back and correct your choices before changing anything."],
      "The selected device matches your tablet and its owner profile. Desktop changes require SDK 23 or above.",
      [link("Model and SDK table", "compatibility.html#model-table"), link("Check firmware limits", "firmware.html#build-limits")]);
  }

  const apkTools = section("apk-tools", "Set up APK verification",
    "Fire Tools uses Google’s Android tools on your computer to check each app before installation.",
    ["Install Android Studio if needed. In its SDK Manager → SDK Tools, install Android SDK Build-Tools. Locate its installed version folder.",
      "In Fire Tools → Connection, set AAPT to aapt.exe or aapt in that folder. Set APK signer to lib/apksigner.jar in the same folder.",
      "Set Java to the java.exe or java executable in a compatible JDK. Android Studio’s bundled runtime is an option."],
    "The ADB, AAPT, APK signer and Java fields all point to local files.",
    [link("See tool paths", "setup.html#android-tools"), link("Download Android Studio", "https://developer.android.com/studio")]);

  function playFiles(model, api) {
    const reference = model.id === "hd10-2023" && api === 30;
    const choose = reference
      ? "In Connection, confirm SDK 30 and arm64-v8a before using the 2023 HD 10 download links below. If either differs, choose variants for the values actually reported."
      : "In Connection, confirm API " + api + " and note the ABI list. Choose builds whose minimum Android version fits this API and whose architecture is listed (or universal).";
    const links = reference
      ? [link("Download the audited HD 10 builds", "google-play.html#choose-files")]
      : [link("Google LLC app listings", "https://www.apkmirror.com/apk/google-inc/"),
        link("Variant and signing guidance", "https://github.com/dev1niscool/fire-tools/blob/v0.6.0/docs/GOOGLE-APKS.md#other-download-options-and-device-requirements")];
    links.push(link("Understand the scan records", "apkmirror.html#check-files"));
    return section("play-files", "Choose the Google APKs",
      reference ? "The reference downloads were checked for the Android 11, ARM64 Fire HD 10. Installation and sign-in on a physical tablet remain unverified."
        : "The audited Android 11 HD 10 set is model-specific. Select separate standalone APKs for your tablet.",
      [choose, "Save Google Services Framework, Google Play services and Google Play Store on your computer. The four-file setup also includes Google Account Manager. Calendar and Contacts Sync are optional.",
        "Choose Download APK for each file. Fire Tools accepts standalone .apk files. Leave .apkm and .xapk bundles out.",
        "In Google Play → Choose APKs, select the files. Choose Check scan records. A match identifies an audited file. For other builds, compare the SHA-256 with that exact listing."],
      "You have the core files for the reported SDK and architecture, ready for Google signature verification.", links);
  }

  const play = section("play", "Install and open Google Play",
    "Use the Google Play tab for the Google components you selected.",
    ["Choose Verify and review. Fire Tools checks package names, compatibility and Google signing certificates.",
      "Check the tablet serial, components and install order in the preview. Choose Confirm and run if they match.",
      "Read the result and choose Component status. If an install stops, check which components already succeeded before retrying.",
      "Open Play Store on the tablet and try signing in there. If you restart, unlock it, scan again and choose Use selected tablet before continuing."],
    "The core components show as installed and enabled, and Play Store opens on the tablet. The sign-in screen is a separate on-device check.",
    [link("Installation and sign-in checks", "google-play.html#verify-install")]);

  const backup = section("backup", "Save your settings and app list",
    "Do this before the other changes in your guide. This backup covers supported settings and package states.",
    ["Open Tools → Backup and restore → Back up settings and package inventory.",
      "Enter the full path of a new folder on the computer. Choose Review, check the destination and tablet, then Confirm and run.",
      "Open the resulting folder and look for settings.json and packages.json. For photos or downloads, use Copy shared-storage folder separately."],
    "Keep the new folder on your computer. Restore supported configuration backup uses this folder.",
    [link("Backup and restore instructions", "tools.html#backup")]);

  function debloat(restricted) {
    return section("debloat", "Review and disable Amazon apps",
      restricted + "Disabling an app keeps its data. The preset preview shows the apps present on your tablet.",
      ["Open Apps → Compare debloat presets. Standard includes Kindle books and Prime Video. Complete also includes Silk and the Appstore.",
        "Open Debloat Amazon apps. Choose Standard or Complete and Automatic (follow list type). For just a few apps, use Tools → Disable selected apps instead.",
        "Choose Review. Check every app, including skipped and protected entries. Cancel if the list includes something you need. Otherwise choose Confirm and run.",
        "Open Apps → Package inventory, choose disabled and select Read. Undo saved package changes can reverse the last batch before another package batch replaces its record."],
      "The apps you chose show as disabled. Check the apps you kept before starting another package change.",
      [link("Compare the presets", "apps.html#debloat"), link("Restore apps", "apps.html#restore")]);
  }

  function accountAds(restricted) {
    return section("ads", "Remove offers through Amazon",
      restricted + "Amazon offers paid removal on eligible tablets through your account. This path needs no USB cable.",
      ["Open Manage Your Devices and select this Fire tablet.",
        "Look for Special Offers → Remove offers. Check the one-time price Amazon displays. If the option is missing, check Amazon’s instructions for your account.",
        "Only if you accept the charge, choose End Offers and Pay the Fee. Connect the tablet to Wi-Fi, then lock and wake it to check the screen."],
      "Check the lock screen itself to see whether the offers are gone.",
      [link("Manage Your Devices", "https://www.amazon.com/hz/mycd/digital-console/alldevices"),
        link("Amazon’s removal instructions", "https://digprjsurvey.amazon.com/csad/help/node/GJHYWUURJ5A6YMBU")]);
  }

  function adsDesktop(restricted) {
    return section("ads-desktop", "Try the Fire Tools ad setting",
      restricted + "This free method is experimental. Fire OS may ignore or reset the change.",
      ["In Fire Tools → Lock-screen ads, choose Review setting change. Check the tablet and saved prior setting.",
        "Choose Confirm and run. Lock and wake the tablet. A successful settings write alone does not show whether ads disappeared.",
        "To undo the change, choose Review restore and confirm on the same computer and tablet."],
      "You have checked the lock screen itself. If ads remain, you can restore the setting. Amazon also offers paid removal on eligible tablets.",
      [link("Ad controls and undo", "ads.html#desktop-controls"), link("Amazon’s separate option", "ads.html#amazon")]);
  }

  function updates(restricted) {
    return section("updates", "Inspect the firmware updater",
      restricted + "Disabling updater packages may delay security fixes. You can stop after reading their states.",
      ["Open System updates → Read updater states. Look for enabled system updater packages. If none qualify, leave them as they are.",
        "If you want to try disabling updates, select the enabled updater rows. Choose Review disable, verify the changes, then Confirm and run.",
        "Choose Read updater states again. Already-downloaded updates or other update routes may still run.",
        "To undo, use Review last package undo while the updater changes are still the last saved batch. To enable an individual row, use Review enable."],
      "Record the state of each updater. A disabled row confirms only that package’s state for the owner.",
      [link("Updater limits and instructions", "updates.html#disable"), link("Allow updates again", "updates.html#restore")]);
  }

  const animations = section("animations", "Shorten the tablet’s animations",
    "You can do this on the tablet. USB debugging can stay off.",
    ["Open Settings → Device Options → Developer Options. If it is hidden, open About Fire Tablet, tap Serial Number seven times and return to Device Options.",
      "Find Window animation scale, Transition animation scale and Animator duration scale. Write down their current values.",
      "Set each available scale to 0.5×. Go Home and open Settings again to try it. Restore the values you wrote down whenever you want."],
    "Menus and transitions feel quicker. If your firmware hides these settings, leave them as they are.",
    [link("Animation settings and restore", "animations.html#on-tablet")]);

  const sideload = section("sideload", "Install other standalone APKs",
    "Use this tool for apps you choose from publishers you trust.",
    ["Put the standalone .apk files in a dedicated folder on your computer. Leave bundles and subfolders out.",
      "Open Tools → Install a folder of APKs and choose the folder. If you know the publisher’s trusted signer fingerprint, enter it to require a match.",
      "Choose Review. Compare each filename, package ID and signing certificate with your source before you choose Confirm and run."],
    "Read the result for each APK. Fire Tools checks the installed bytes, and Android asks for runtime permissions when the app needs them.",
    [link("Folder installation guide", "apps.html#install-folder")]);

  const dns = section("dns", "Choose a Private DNS provider",
    "A DNS provider looks up domain names for the tablet. The provider you select can see those names.",
    ["Open Tools → Network → Configure private DNS. Choose a provider, or use hostname with a DNS-over-TLS hostname you trust.",
      "Choose Review. Check the exact hostname and filtering behavior, then Confirm and run if they match what you want.",
      "Open a website on the tablet. If it stops loading, use Network → Restore private DNS configuration to recover the saved settings."],
    "The tablet can open websites after the change.",
    [link("Providers and restore instructions", "tools.html#private-dns")]);

  const dnsLimit = section("dns-limit", "Check the Private DNS requirement",
    "This tablet’s Fire OS 6 is based on Android 7.1 (API 25). The desktop Private DNS option needs Android 9 (API 28) or newer.",
    ["Check your installed version in Settings → Device Options → System Updates.",
      "If it is still Fire OS 6, skip Private DNS for this tablet. If your installed version differs, edit your tutorial choices."],
    "Use the API for the operating system currently installed on the tablet.",
    [link("Fire OS versions", "firmware.html#build-limits"), link("Private DNS requirements", "tools.html#private-dns")]);

  function eligibility(model, major, firmware) {
    const legacy = model && model.families.includes(5) && (!firmware || model.families.includes(major));
    const intro = legacy
      ? "This generation runs an Android version below API 23, the minimum for Fire Tools tablet changes."
      : "The handbook cannot confirm this model and installed Fire OS combination. Verify them before choosing APKs or changing packages.";
    return section("eligibility", legacy ? "Check your tablet’s limits" : "Confirm your tablet details", intro,
      ["On the tablet, open Settings → Device Options → About Fire Tablet and note the model and generation. Open System Updates to read the installed Fire OS version.",
        "Compare those details with the model table. If either entry was wrong or missing, edit your tutorial choices.",
        legacy ? "Use the on-tablet or Amazon account options in your guide if available. Desktop installation and debloat require a newer Android API."
          : "For an unlisted combination, use the USB setup guide to read SDK and ABIs in Connection. Stop before desktop changes until you can confirm your device’s requirements."],
      legacy ? "Only the selected options that work independently of Fire Tools are shown next."
        : "The guide offers on-tablet and account options separately while desktop eligibility is unresolved.",
      [link("Model and API table", "compatibility.html#model-table"), link("Firmware lookup", "firmware.html#model-builds"),
        link("Read device information", "setup.html#usb")]);
  }

  const finish = section("finish", "Finish on your tablet",
    "Check the results of your selected tasks before disconnecting.",
    ["Look at the Fire Tools activity log for skipped or failed actions. Keep any undo files on this computer.",
      "Disconnect the cable. In Settings → Device Options → Developer Options, turn USB debugging off when you’re done."],
    "You have checked the results and know where to find saved recovery information.",
    [link("Find your undo files", "resources.html#undo-files")]);

  function build({ model: modelId, firmware = "", goals: goalIds = [], adsMethod = "amazon" }) {
    const model = models.find(item => item.id === modelId);
    const selected = new Set(goalIds);
    const parts = typeof firmware === "string" && /^\d{1,3}(?:\.\d{1,3}){1,3}$/.test(firmware)
      ? firmware.split(".").map(Number) : [];
    const major = parts[0];
    const api = apiLevels[major];
    const compatible = Boolean(api && model && model.families.includes(major));
    const useAdsTool = selected.has("ads") && adsMethod === "tool";
    const needsComputer = useAdsTool || ["backup", "play", "debloat", "updates", "sideload"].some(id => selected.has(id));
    const wantsDesktop = needsComputer || selected.has("dns");
    const desktop = compatible && (needsComputer || (selected.has("dns") && api >= 28));
    const restricted = compatible ? restrictionNotice(parts, firmware) : "";
    const route = [];
    if (!compatible && wantsDesktop) {
      const limits = eligibility(model, major, firmware);
      if (useAdsTool) limits.links.push(link("Optional Amazon account method", "ads.html#amazon"));
      route.push(limits);
    }
    if (desktop) {
      route.push(selected.has("updates")
        ? { ...computer, intro: computer.intro + " If you want to delay an update, your tablet can stay off Wi-Fi during USB setup while your computer downloads the tools." }
        : computer);
      // Changing a tool path in the desktop clears the selected tablet.
      if (selected.has("play") || selected.has("sideload")) route.push(apkTools);
      route.push(usb, connect(model, firmware, api));
      if (selected.has("backup")) route.push(backup);
      if (selected.has("updates")) route.push(updates(restricted));
      if (selected.has("play")) route.push(playFiles(model, api), play);
      if (selected.has("sideload")) route.push(sideload);
      if (selected.has("debloat")) route.push(debloat(restricted));
      if (useAdsTool) route.push(adsDesktop(restricted));
      if (selected.has("dns") && api >= 28) route.push(dns);
    }
    if (compatible && selected.has("dns") && api < 28) route.push(dnsLimit);
    if (selected.has("ads") && !useAdsTool) route.push(accountAds(restricted));
    if (selected.has("animations")) route.push(animations);
    if (desktop) route.push(finish);
    return route;
  }

  globalThis.FireTutorialRoute = { models: models.map(({id, label}) => ({id, label})), goals, build };
})();
