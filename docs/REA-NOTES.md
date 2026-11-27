# REA behavior research

The reference was Fire Toolbox 46.0, a managed Windows assembly targeting .NET Framework 4.8. The inspected file's SHA-256 is `34be37dff0c3bf40cb34155896e92b70d9dfdff5cb969c780cade88f13f74079`. The static inspection used `rea-agents@6.10.1` with provider `rea-dotnet-static` version 1. The original executable remained unexecuted.

| Static inspection | Evidence ID |
| --- | --- |
| Managed artifact metadata | `ev_aa0087f806608fa4e2f437017103b75307ae62a3d1dd7e8e813166424a1ccb2e` |
| `FireToolbox.PlayServices` and `FireToolbox.RemoveAds` member inspection | `ev_d149bd46546e1af69b6168a97edad59e2dae5631c3e81a464905a5d42b80aa36` |
| `FireToolbox.Utils` member inspection | `ev_d75a75c7191de63779456ee5500f730214d6de23b7860b6c15de650b4b2a7a48` |

## Observations

- `FireToolbox.PlayServices.InstallGServices` (MethodDef `0x060000da`) constructs an Android-version-specific staging path and orders Google Account Manager, Google Services Framework, Google Play services and Google Play Store. It passes APKs to a helper one by one and checks the result. The inspected workflow also has additional sync adapter paths and a Store launch path.
- `FireToolbox.Utils.InstallAPK` (MethodDef `0x06001dc7`) checks package presence and has several ADB package install paths. Helper support for install flags establishes the helper's capabilities. The flags selected by callers depend on the branch.
- `FireToolbox.RemoveAds.ToggleAds` (MethodDef `0x0600155c`) includes writes to the Android global setting `LOCKSCREEN_AD_ENABLED`. Some branches reference the Special Offers package. A message describes the fallback setting change as temporary and likely to revert.

The observations informed package ordering and the experimental settings workflow. The toolkit implementation is original Python under the MIT license. It uses local APK inputs with signature verification and a single reversible setting write. Reference binaries, bundled assets, APKs, and raw REA outputs are outside the toolkit distribution. Static inspection establishes the behavior present in the inspected assembly. Hardware compatibility and ad persistence require separate device tests.

The production signing certificate pinned for the Google APKs has SHA-256 `f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`. [AndroidX source](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8) · [Independent apksigner transcript](https://github.com/spytrap-org/spytrap-adb/issues/34)
