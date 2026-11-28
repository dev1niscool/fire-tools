# Browser USB transport

The experimental browser page imports `../assets/adb-transport.js`, a local ES module built from this directory. It needs a browser with WebUSB, Web Crypto, Streams and `AbortSignal.any` (desktop Chrome 116+). Connect from HTTPS. Chrome asks which USB device to use, and Fire OS asks the owner to authorize USB debugging.

The adapter creates an RSA key for each connection and discards its private bytes after the ADB handshake. Leave “Always allow” unchecked on the tablet. The browser shell requires the ADB shell v2 feature so each operation has a separate exit status and error stream. Installation streams the exact number of reviewed bytes to the package manager for owner user 0. Readback pulls the installed APK across the same ADB connection and calculates its SHA-256 in the browser.

## Build and test

From this directory, run the following commands with Node.js 22 or newer and npm.

```sh
npm ci --ignore-scripts --no-fund
npm test
npm run build
git diff --exit-code -- ../assets/adb-transport.js
```

`package-lock.json` pins build and runtime packages with registry integrity digests. Package installation scripts are disabled for this workflow. Building needs the platform esbuild binary installed through optional dependencies. The website can be built or served from the committed module without npm.

The bundle header includes the MIT notices from all bundled packages. esbuild is used on the build host only. The transport uses Tango ADB’s direct device connection, shell v2 and sync services. [Tango ADB](https://tangoadb.dev/) · [Tango ADB source](https://github.com/yume-chan/ya-webadb) · [Chrome WebUSB platform requirements](https://developer.chrome.com/docs/capabilities/build-for-webusb)

## Browser acceptance test

From the repository root, run `python website/tests/webusb/smoke.py` with Playwright and Chromium installed. The test builds the site, simulates a USB tablet at the WebUSB API and exercises the production page, authorization and reversible device changes. Pass `--apk-dir /path/to/your/apks` to also stream the six audited Google APKs and verify the bytes returned by the simulated tablet. The APKs come from your local files. The default test runs during Pages deployment.
