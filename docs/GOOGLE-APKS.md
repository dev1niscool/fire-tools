# Google APKs for a Fire HD 10

On a Fire HD 10, open **Connection → Scan devices**, then select the tablet and choose **Use selected tablet**. Note its model, Android API level and supported ABIs (processor architectures). Amazon lists the 2023 13th-generation Fire HD 10 as `KFTUWI`, with Fire OS 8, Android 11 (API 30) and 32-bit and 64-bit app support. The examples below use that model. For any other model, choose variants for the API and ABIs reported by your tablet. Amazon’s 2026 **Alexa Tablet** 8, 11 and 12 Pro already include Google Play. [Fire HD 10 specifications](https://developer.amazon.com/docs/device-specs/ft-device-specifications-firehd-models?v=firehd10_2023) · [Alexa Tablet announcement](https://www.aboutamazon.com/news/devices/new-amazon-alexa-tablets-alexa-plus)

## Files with a local scan record

These are the six exact builds examined in the project audit. Before enabling USB debugging, open **Google Play → Choose APKs → Check scan records** to compare your downloads by SHA-256. The CLI offers the same check. A match identifies the bytes examined on November 27, 2026. Version changes, including security updates, produce a different hash. [Scan scope and results](TESTING.md)

| Google component | Scanned build |
| --- | --- |
| Google Account Manager (legacy login) | [7.1.2, API 23+, noarch](https://www.apkmirror.com/apk/google-inc/google-account-manager/google-account-manager-7-1-2-release/google-account-manager--7-1-2-android-apk-download/) |
| Google Services Framework | [10-6494331, API 29+, noarch](https://www.apkmirror.com/apk/google-inc/google-services-framework/google-services-framework-10-6494331-release/google-services-framework-10-6494331-android-apk-download/) |
| Google Play services | [25.20.37](https://www.apkmirror.com/apk/google-inc/google-play-services/google-play-services-25-20-37-release/google-play-services-25-20-37-150400-766884605-android-apk-download/) |
| Google Play Store | [36.3.12-21](https://www.apkmirror.com/apk/google-inc/google-play-store/google-play-store-36-3-12-release/google-play-store-36-3-12-21-0-pr-542033711-2-android-apk-download/) |
| Google Calendar Sync (optional) | [2021.23.3](https://gitlab.opengapps.org/opengapps/all/-/blob/b458223777512c97639cb6bb54bfad93047406d7/app/com.google.android.syncadapters.calendar/30/nodpi/2017005136.apk) |
| Google Contacts Sync (optional) | [11](https://gitlab.opengapps.org/opengapps/all/-/blob/b458223777512c97639cb6bb54bfad93047406d7/app/com.google.android.syncadapters.contacts/30/nodpi/30.apk) |

## Other download options and device requirements

For a fresh setup following the Fire Toolbox Android 11 workflow, select **Google Account Manager**, **Google Services Framework**, **Google Play services** and **Google Play Store**. Fire Tools also accepts a three-file plan with the legacy Account Manager omitted. Calendar and Contacts Sync are optional for people who want to sync that data.

The links go to individual **APKMirror** release pages labeled **Google LLC**. APKMirror is an independent distributor that documents how it checks upload signatures. Google’s official Play services listing is also available to devices that already have Google Play. On each APKMirror page, choose **Download APK**. A release can have several files under the same version number, including bundles, alternate signing certificates and variants for other device types. Use the exact variant in the link if you want to compare its file hash below. [APKMirror verification and variant FAQ](https://www.apkmirror.com/faq/) · [Official Google Play services listing](https://play.google.com/store/apps/details?id=com.google.android.gms)

| Component | Android package | Standalone APK example for API 30 |
| --- | --- | --- |
| Google Account Manager (legacy login) | `com.google.android.gsf.login` | [7.1.2, API 23+, noarch](https://www.apkmirror.com/apk/google-inc/google-account-manager/google-account-manager-7-1-2-release/google-account-manager--7-1-2-android-apk-download/) |
| Google Services Framework | `com.google.android.gsf` | [10-6494331, API 29+, noarch](https://www.apkmirror.com/apk/google-inc/google-services-framework/google-services-framework-10-6494331-release/google-services-framework-10-6494331-android-apk-download/) |
| Google Play services | `com.google.android.gms` | [26.46.32 (100400), API 28+, arm64-v8a and armeabi-v7a](https://www.apkmirror.com/apk/google-inc/google-play-services/google-play-services-26-46-32-release/google-play-services-26-46-32-100400-1025220680-3-android-apk-download/) |
| Google Play Store | `com.android.vending` | [54.4.11-29, API 29+, multi-architecture](https://www.apkmirror.com/apk/google-inc/google-play-store/google-play-store-54-4-11-release/google-play-store-54-4-11-29-0-pr-1025789771-4-android-apk-download/) |
| Google Calendar Sync (optional) | `com.google.android.syncadapters.calendar` | [2026.03.0-857911644-release, API 30+, noarch](https://www.apkmirror.com/apk/google-inc/google-calendar-sync/google-calendar-sync-2026-03-0-857911644-release-release/google-calendar-sync-2026-03-0-857911644-release-2-android-apk-download/) |
| Google Contacts Sync (optional) | `com.google.android.syncadapters.contacts` | [11, API 30+, noarch](https://www.apkmirror.com/apk/google-inc/google-contacts-sync/google-contacts-sync-11-release/google-contacts-sync-11-android-apk-download/) |

The Framework example above matches the file Fire Toolbox selected for Android 11. For a different build, follow guidance for the device’s Fire OS and check the minimum API. A separate standalone [Framework 11 variant](https://www.apkmirror.com/apk/google-inc/google-services-framework/google-services-framework-11-release/google-services-framework-11-android-apk-download/) lists API 30 and the same signing key. Its compatibility with Fire OS remains untested. For Play services and Play Store, choose a stable phone/tablet APK whose minimum API is at most the tablet’s API and whose native libraries include one of its ABIs. `noarch` applies across processor types and `nodpi` applies across display densities. Fire Tools handles standalone `.apk` files. Leave `.apkm`, `.xapk`, split sets, and TV, Wear or Automotive variants out of the selection. Account Manager 7.1.2 dates to 2017. Its minimum API indicates install eligibility. Sign-in also depends on the tablet and current Google services.

## Verify before installing

1. In the **Google Play** tab, select the local files and review the plan. Check the tablet identity and package IDs against the table above. Fire Tools uses Google’s `apksigner` to verify the signature on each local APK, then checks the signer against its Google key policy. For these examples, every linked page lists the full certificate SHA-256 `f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`. AndroidX identifies this fingerprint as Google’s general first-party key. If verification fails, stop and recheck the file, package and variant. [AndroidX certificate reference](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8) · [Google’s apksigner documentation](https://developer.android.com/tools/apksigner)
2. Compare each **APK SHA-256** in the plan with **APK file hashes** on the exact version page. The file hash identifies those specific bytes and changes between releases. The examples below are the hashes the six pages published when checked on November 27, 2026. The source check covered the six listing pages. The host verification below used a mixture of exact reference files and separate sync examples. A signature confirms the signing identity. Compatibility, sign-in and sync on a physical Fire tablet remain untested. [Verification results](TESTING.md)
3. Confirm the plan, then restart the tablet and open Play Store on the tablet to sign in. Fire OS sideloading is outside Amazon’s supported Google Mobile Services configuration. If Play Store reports a certification problem, check **Play Store → profile icon → Settings → About → Play Protect certification**. Updating Fire OS does not establish compatibility for a particular APK set. [Amazon’s Fire OS guidance](https://developer.amazon.com/docs/app-porting/port-existing-app) · [Google’s certification guidance](https://support.google.com/android/answer/7165974)

<details>
<summary>File SHA-256 for the six exact examples above</summary>

| Component | APK file SHA-256 |
| --- | --- |
| Account Manager | `3324ee2f67d23848ae3d9086f20ada10f2cb0dbb6d202067b918cc4fb4d167be` |
| Services Framework | `32156365bcff60f2a0576abe1f15ef7e2b705aea9536bfcbd6fef784d131ccb5` |
| Play services | `5f8abb23f2d1a63778981aa9e89d608922491cacbf1aaca4dee87d6d72f265e3` |
| Play Store | `931b6c6dd00938fc84daf574e1c1a76f5e6b440f22ec3eafcb31bc3bea664106` |
| Calendar Sync | `85ef8ec4a5d3ca43a681046b98e9683b628c2f679a141a675a0f27c75757316b` |
| Contacts Sync | `4af1f2b93744d5730c6e44b82d1d6dbbcab03531091669bd75e3c0636b4e38ef` |

</details>

## Files selected by Fire Toolbox 46 for Android 11

The Account Manager and Framework files in the table above match the SHA-256 digests of those two APKs in the v46 Android 11 catalog archive. We also matched the other two core APKs in that catalog to individual APKMirror records. These older releases document the original selection. The Play services and Store examples above are newer standalone builds. [Static inspection of the reference](REA-NOTES.md)

| Component | Original Android 11 selection | SHA-256 of the inspected APK |
| --- | --- | --- |
| Play services | [25.20.37 (150400), API 30+](https://www.apkmirror.com/apk/google-inc/google-play-services/google-play-services-25-20-37-release/google-play-services-25-20-37-150400-766884605-android-apk-download/) | `1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07` |
| Play Store | [36.3.12-21, API 21+](https://www.apkmirror.com/apk/google-inc/google-play-store/google-play-store-36-3-12-release/google-play-store-36-3-12-21-0-pr-542033711-2-android-apk-download/) | `03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa` |

The original Play services APK carries a signing-key rotation. The toolkit accepts its successor key `7ce83c1b71f3d572fed04c8d40c5cb10ff75e6d87d9df6fbd53f0468c2905053` for `com.google.android.gms` when the signed APK proves the rotation from the pinned Google key. For contacts, use the listing whose package is `com.google.android.syncadapters.contacts`. The v46 catalog’s file named `ConSync10.apk` actually declares `com.google.android.syncadapters.calendar`. Fire Tools determines which component it has from the signed APK manifest. [Inspection notes](REA-NOTES.md)

For a host-side check with six real files, we verified and ordered these four core APKs plus the two Google-signed API 30 adapters below, retrieved from a fixed revision of the independent Open GApps repository. Both adapters declare the expected package and pass the signature check. The newer Calendar Sync and alternate Contacts Sync upload in the first table have their own file hashes.

| Host-tested adapter | Open GApps source file | APK file SHA-256 |
| --- | --- | --- |
| Calendar Sync 2021.23.3-389584493-release | [Google Calendar Sync APK record](https://gitlab.opengapps.org/opengapps/all/-/blob/b458223777512c97639cb6bb54bfad93047406d7/app/com.google.android.syncadapters.calendar/30/nodpi/2017005136.apk) | `87fb81b621d060c9779f0942ea379f7cad4f7b551b4d9f1d651a8980f3a6f749` |
| Contacts Sync 11 | [Google Contacts Sync APK record](https://gitlab.opengapps.org/opengapps/all/-/blob/b458223777512c97639cb6bb54bfad93047406d7/app/com.google.android.syncadapters.contacts/30/nodpi/30.apk) | `e6c7f541dba8c334ff416ea6e63df6c6b2a5991db54ac99b5c97d0f2b62068b3` |
