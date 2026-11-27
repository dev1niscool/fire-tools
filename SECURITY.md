# Security and local state

Run the toolkit from extracted source with a Python interpreter you trust. Supply official Google Platform-Tools and Build Tools and a trusted Java runtime. The toolkit executes those selected paths locally. A malicious replacement executable or JAR could run with your computer account's permissions.

The toolkit has no telemetry, auto-updater or automatic downloads. Its network-related actions consist of ADB requests to the local ADB server and opening fixed vendor links on request. Your external tools, browser and installed Google apps may make their own network requests.

Changes require an explicit tablet serial and confirmation. The service checks the selected tablet's manufacturer, model, Android API level and active Android user before making a change. ADB debugging authorization applies to your computer. Revoke that authorization from the tablet when you are finished if it is no longer needed.

Google Play installation verifies all selected APKs with Google's `apksigner.jar` and the pinned Google first-party Android production certificate. The package allowlist, archive and compatibility checks and staged-file rechecks constrain what the installer accepts. A valid signature identifies the signer. It cannot establish that an APK is suitable for your tablet or that its code is safe to run. [AndroidX certificate reference](https://android.googlesource.com/platform/frameworks/support/+/7be3a623dfcf461ff6e2004799ac2e652c8d23a8)

## Undo state and operation lock

| Platform | State directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\open-fire-toolkit` with the user's home directory as fallback |
| Linux | `$XDG_STATE_HOME/open-fire-toolkit` or `~/.local/state/open-fire-toolkit` |

`state.json` stores the saved lock-screen setting, associated with a hash of the tablet serial and its reported model. Preserve this file while a restore may still be needed. The toolkit does not collect account passwords or Google credentials.

`operation.lock` prevents concurrent writes by toolkit processes sharing that directory. If a forced exit leaves it behind, close every instance of the toolkit and confirm any in-flight device operation has finished before removing only `operation.lock`. Reconnect and review the tablet's current state before retrying. Preserve `state.json` if it becomes unreadable.
