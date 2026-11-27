# Open Fire Toolkit design

## Intent and scope
Independent, inspectable replacement for the user's principal Fire Toolbox workflows: Google Play installation and lock-screen ad management on a recent Amazon Fire HD 10. Provide a desktop GUI and CLI, useful read-only device diagnostics, conservative app disable/restore and reboot. This is a focused remake, not full Fire Toolbox feature parity. Never advertise virus-free certification or hardware-tested status without evidence.

User has explicitly delegated decisions and opted out of questions while asleep. Design choices below are the builder's decisions. Use Superpowers and REA as requested. REA investigates original behavior only; do not copy original implementation, resources, APKs, or executables into the replacement.

## Approaches
1. Repackage original .NET program: rejected; keeps its opaque dependencies and updater trust.
2. Fork another debloater: rejected; larger inherited surface and uncertain licensing/provenance of bundled files.
3. Independent Python 3.11+ standard-library desktop/CLI app: selected. Easy to inspect, no runtime PyPI dependencies, portable source. Requires Python, Google platform-tools, and for APK verification Google build-tools plus Java. Tool binaries are explicitly supplied by the user, never silently downloaded.

## Security and behavior
- No telemetry, auto-updater, web server, eval, shell=True, root, firmware flashing, OTA blocking, certificate installation, or bundled executables/APKs.
- Always explicit ADB device serial; refuse unauthorized/offline/ambiguous connections, non-Amazon devices and non-owner Android user for writes.
- Host subprocesses are argument arrays with bounded timeouts; remote shell tokens are quoted. Validate serials/package names. Do not inherit remote ADB server overrides.
- Mutations require a preview and explicit confirmation. Check tablet identity again immediately before mutations. Never auto-run queued actions after reconnect.
- Google Play uses local APKs. Verify ZIP structure, aapt package metadata, min SDK and supported native ABIs; cryptographically verify signatures using Google's apksigner JAR invoked directly with Java. Pin Google's known Android signing certificate SHA256; require all present signers to match. Package names alone are not authenticity proof.
- Required Play packages: com.google.android.gsf, com.google.android.gms, com.android.vending. Optional com.google.android.gsf.login installs first. Reject duplicate packages, split APKs, unknown Google set entries, unsupported min SDK/ABI, invalid signature, signer mismatch. Verify all APKs before installing any. Stage immutable private copies and re-hash before each install. No downgrade flag and no blanket runtime permission grants.
- APK install is not atomic. Stop on first failure and report installed packages; never auto-uninstall preexisting Google components. User restart offered separately.
- Ad management: explain official one-time paid removal and open only a fixed Amazon URL on user click. Experimental one-shot setting change LOCKSCREEN_AD_ENABLED=0 with previous value persisted before write; restore exact previous setting or delete if absent. Do not erase Special Offers app data or promise ad removal. Modern Fire OS may ignore/reset it. No copied Automate app/flow or exploit.
- App management: allow disabling only a small explicit optional Amazon app allowlist, never launcher, Settings, keyboard, OTA/security, account or package installer. Enable only allowlisted apps. Show current state. No bulk debloat.
- Persist local undo state in user data directory, atomic replace and private permissions where supported. Bind records to serial hash. Keep original value across repeated suppress operations; refuse unknown restore state. No storing passwords or Google credentials.
- Main app never contacts a network service directly. Fixed browser links only on explicit clicks. ADB and Google apps have their own network behavior.

## UI
Tkinter/ttk notebook: Connection, Google Play, Lock-screen ads, Apps. Header connection state. Setup fields for adb, aapt, apksigner.jar and java with browse controls. Scan list, explicit connect, firmware details. APK picker and verified preview. Background workers queue results to Tk thread, only one operation at a time, disable mutation controls while busy. Errors are actionable; logs visible. Demo mode is clearly labeled and cannot execute device commands. CLI defaults to read-only previews; --yes required for writes.

## Validation and delivery
Unittest suite with adversarial inputs and fake external process boundary; no real tablet available. Real subprocess fixture tests, CLI smoke, Tk GUI smoke in virtual display if available, independent security review, source/ZIP manifest checks. Source-only reproducible ZIP with SHA256SUMS, launchers and honest setup instructions. No publishing/push or device mutation during build.
