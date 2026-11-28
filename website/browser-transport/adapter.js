import { Adb, AdbDaemonTransport } from "@yume-chan/adb";
import { readSharedFile } from "./shared-file.js";
import { AdbDaemonWebUsbDeviceManager } from "@yume-chan/adb-daemon-webusb";

const MIB = 1024 * 1024;
const MAX_APK = 256 * MIB;
const claimed = new WeakSet();

// Tango passes shell protocol commands as a shell string. Quote every argument,
// including empty values and apostrophes, before it crosses that boundary.
export function shellArgs(args) {
    if (!Array.isArray(args) || !args.length || args.some(arg => typeof arg !== "string" || /[\x00-\x1f\x7f]/.test(arg)))
        throw new Error("Invalid tablet command arguments.");
    const command = args.map(arg => "'" + arg.replaceAll("'", "'\\''") + "'").join(" ");
    if (new TextEncoder().encode(command).length > 4096)
        throw new Error("Tablet command is too long.");
    return command;
}

function abortable(promise, signal) {
    return new Promise((resolve, reject) => {
        const stop = () => reject(signal.reason);
        signal.addEventListener("abort", stop, {once: true});
        if (signal.aborted) stop();
        Promise.resolve(promise).then(resolve, reject).finally(() => signal.removeEventListener("abort", stop));
    });
}

function deadline(ms, message) {
    const control = new AbortController();
    const timer = setTimeout(() => control.abort(new Error(message)), ms);
    return {signal: control.signal, clear: () => clearTimeout(timer)};
}

// The private key exists only while this individual connection authenticates.
// No IndexedDB, origin-wide key cache, cookie or network request is involved.
function ephemeralKeyStore() {
    let key;
    let disposed = false;
    return {
        async generateKey() {
            const pair = await crypto.subtle.generateKey({
                name: "RSASSA-PKCS1-v1_5", hash: "SHA-256", modulusLength: 2048,
                publicExponent: Uint8Array.of(1, 0, 1)
            }, true, ["sign", "verify"]);
            const buffer = new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
            if (disposed) {
                buffer.fill(0);
                throw new Error("USB authorization has ended.");
            }
            key = {name: "Fire Tools (this connection)", buffer};
            return key;
        },
        *iterateKeys() { if (key) yield key; },
        forget() { disposed = true; key?.buffer.fill(0); key = undefined; }
    };
}

async function readText(stream) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let size = 0, text = "";
    try {
        for (;;) {
            const {done, value} = await reader.read();
            if (done) return text + decoder.decode();
            size += value.byteLength;
            if (size > MIB) throw new Error("Tablet command output exceeds the 1 MiB limit.");
            text += decoder.decode(value, {stream: true});
        }
    } finally {
        reader.releaseLock();
    }
}

export async function runShell(adb, args, input) {
    const proc = await adb.subprocess.shellProtocol.spawn([shellArgs(args)]);
    try {
        // Android reads exactly -S bytes for a streamed installation. Closing
        // stdin afterwards races successful package processes that already exited.
        const feed = input ? input.stream().pipeTo(proc.stdin, {preventClose: true}) : undefined;
        const [out, err, code] = await Promise.all([
            readText(proc.stdout), readText(proc.stderr), proc.exited, feed
        ]);
        if (code !== 0) {
            const diagnostic = (err.trim() || out.trim()).slice(0, 500);
            throw new Error("Tablet command exited with " + code + (diagnostic ? ". " + diagnostic : "."));
        }
        return out.trim();
    } catch (error) {
        void Promise.resolve(proc.kill()).catch(() => {});
        throw error;
    }
}

function validSize(size) {
    return Number.isSafeInteger(size) && size > 0 && size <= MAX_APK;
}

export async function readHash(stream, limit) {
    if (!validSize(limit)) throw new Error("Invalid installed APK size limit.");
    const buffer = new Uint8Array(limit);
    let size = 0;
    const reader = stream.getReader();
    try {
        for (;;) {
            const {value, done} = await reader.read();
            if (done) break;
            if (value.byteLength > limit - size) throw new Error("Installed APK exceeds the reviewed size.");
            buffer.set(value, size);
            size += value.byteLength;
        }
    } finally {
        reader.releaseLock();
    }
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", buffer.subarray(0, size)));
    return {size, sha256: Array.from(digest, b => b.toString(16).padStart(2, "0")).join("")};
}

function session(adb, raw, serial) {
    const lifetime = new AbortController();
    let closing;
    function close() {
        if (!closing) {
            lifetime.abort(new Error("The tablet connection closed. Reconnect and review again."));
            closing = Promise.allSettled([
                Promise.resolve().then(() => adb.close()),
                Promise.resolve().then(() => raw.close())
            ]).then(() => { claimed.delete(raw); });
        }
        return closing;
    }
    const disconnected = new Promise(resolve => lifetime.signal.addEventListener("abort", () => resolve(), {once: true}));
    adb.disconnected.then(close, close);

    async function run(ms, operation) {
        lifetime.signal.throwIfAborted();
        const timer = deadline(ms, "The tablet timed out. Reconnect and read its current state before trying again.");
        const signal = AbortSignal.any([lifetime.signal, timer.signal]);
        try {
            return await abortable(operation(), signal);
        } finally {
            if (timer.signal.aborted) void close();
            timer.clear();
        }
    }

    return {
        serial, disconnected, close,
        shell: args => run(30_000, () => runShell(adb, args)),
        async install(file) {
            if (!(file instanceof Blob) || !validSize(file.size))
                throw new Error("Choose a nonempty reviewed APK of at most 256 MiB.");
            const reply = await run(300_000, () => runShell(adb,
                ["cmd", "package", "install", "-r", "--user", "0", "-S", String(file.size)], file));
            if (reply !== "Success")
                throw new Error("Package installation was not confirmed. " + reply.slice(0, 500));
        },
        readSharedFile: (path, maxBytes) => run(120_000, () => readSharedFile(adb, path, maxBytes)),
        async hashRemote(path, maxBytes) {
            if (typeof path !== "string" || !path.startsWith("/data/app/") || path.length > 1024 ||
                !path.endsWith(".apk") || /[\x00-\x1f\x7f]/.test(path) || path.slice(1).split("/").some(p => !p || p === "." || p === ".."))
                throw new Error("Unexpected installed APK path.");
            if (!validSize(maxBytes)) throw new Error("Invalid installed APK size limit.");
            return run(300_000, async () => {
                const sync = await adb.sync();
                try {
                    return await readHash(sync.read(path), maxBytes);
                } finally {
                    await sync.dispose();
                }
            });
        }
    };
}

export async function connectUsb(signal = new AbortController().signal) {
    signal.throwIfAborted();
    const usb = globalThis.navigator?.usb;
    if (!usb || !globalThis.crypto?.subtle || globalThis.isSecureContext === false)
        throw new Error("USB connections require an HTTPS page in desktop Chrome or Edge.");
    if (typeof AbortSignal.any !== "function")
        throw new Error("Update desktop Chrome or Edge before connecting a tablet.");
    const manager = new AdbDaemonWebUsbDeviceManager(usb);
    // This call must start in the user's click event to retain Chrome's USB permission gesture.
    const device = await abortable(manager.requestDevice(), signal);
    if (!device) throw new Error("No tablet selected. Connect with a USB data cable and choose the tablet.");
    signal.throwIfAborted();
    const raw = device.raw;
    const serial = raw.serialNumber;
    if (typeof serial !== "string" || !serial.trim() || serial.length > 256 || /[\x00-\x1f\x7f]/.test(serial))
        throw new Error("The tablet did not supply a usable USB serial number.");
    if (claimed.has(raw)) throw new Error("A connection to this tablet is already open or closing.");
    claimed.add(raw);

    const timer = deadline(90_000, "Connection timed out. Unlock the tablet, check the USB debugging prompt and try again.");
    const stop = AbortSignal.any([signal, timer.signal]);
    const keys = ephemeralKeyStore();
    let transport;
    const opening = (async () => {
        const connection = await device.connect();
        stop.throwIfAborted();
        transport = await AdbDaemonTransport.authenticate({
            serial, connection, credentialStore: keys,
            features: ["shell_v2", "cmd"], initialDelayedAckBytes: 0
        });
        stop.throwIfAborted();
        const adb = new Adb(transport);
        if (!adb.subprocess.shellProtocol)
            throw new Error("This tablet lacks the ADB shell protocol that verifies command results. Use desktop Fire Tools.");
        return adb;
    })();
    try {
        return session(await abortable(opening, stop), raw, serial);
    } catch (error) {
        // Closing USB interrupts an outstanding authentication read. If open()
        // itself is still in flight, close again after it settles. Keep ownership
        // until then so stale cleanup cannot close a subsequent connection.
        const interrupt = Promise.resolve().then(() => raw.close()).catch(() => {});
        void Promise.allSettled([opening, interrupt]).then(async () => {
            await Promise.allSettled([
                Promise.resolve().then(() => transport?.close()),
                Promise.resolve().then(() => raw.close())
            ]);
            claimed.delete(raw);
        });
        if (error?.name === "DeviceBusyError" || error?.name === "NetworkError")
            throw new Error("Chrome could not claim the USB interface. Close other ADB apps, check the USB driver or permissions, and reconnect.", {cause: error});
        throw error;
    } finally {
        timer.clear();
        keys.forget();
    }
}
