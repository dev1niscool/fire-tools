import {isManagedChangeWrite} from "./browser-changes.mjs";

// One session owns one selected USB transport. No operation searches for a replacement.
const guards = new WeakMap();
const propertyNames = new Set([
  "ro.product.manufacturer", "ro.product.model", "ro.build.mktg.fireos", "ro.build.version.fireos",
  "ro.build.version.name", "ro.build.version.release", "ro.build.version.sdk", "ro.product.cpu.abilist",
  "ro.product.cpu.abi", "ro.boot.serialno", "ro.serialno",
]);

const placeholderSerials = new Set(["unknown", "null", "none", "unavailable", "restricted", "default",
  "0123456789abcdef", "1234567890abcdef"]);

function hardwareSerial(value) {
  return /^[a-z\d][a-z\d_-]{0,127}$/i.test(value) &&
    !placeholderSerials.has(value.toLowerCase()) && new Set(value.toLowerCase()).size > 1;
}

async function identify(raw) {
  const props = {};
  const dump = await raw.shell(["getprop"]);
  for (const line of dump.split(/\r?\n/)) {
    const match = /^\[([^\]]+)\]: \[([^\]]*)\]$/.exec(line);
    if (!match || !propertyNames.has(match[1])) continue;
    if (Object.hasOwn(props, match[1])) throw new Error("Ambiguous tablet properties. Reconnect the tablet.");
    props[match[1]] = match[2].trim();
  }
  const manufacturer = props["ro.product.manufacturer"] || "";
  const model = props["ro.product.model"] || "";
  const sdk = props["ro.build.version.sdk"] || "";
  if (manufacturer.toLowerCase() !== "amazon" || !model || !/^[1-9]\d{0,2}$/.test(sdk)) {
    throw new Error("Select an Amazon Fire tablet that reports its model and Android SDK.");
  }
  const user = (await raw.shell(["am", "get-current-user"])).trim();
  if (!/^(0|[1-9]\d{0,8})$/.test(user)) throw new Error("Could not identify the active tablet profile.");
  const serial = raw.serial || "";
  const physical = [props["ro.boot.serialno"], props["ro.serialno"], serial].find(v => v && hardwareSerial(v));
  let identityKey = "";
  if (physical) {
    const data = new TextEncoder().encode(JSON.stringify([manufacturer.toLowerCase(), model, physical]));
    const hash = await crypto.subtle.digest("SHA-256", data);
    identityKey = [...new Uint8Array(hash)].map(n => n.toString(16).padStart(2, "0")).join("");
  }
  return Object.freeze({
    serial, identityKey, model, manufacturer, user: Number(user), sdk: Number(sdk),
    fireOS: props["ro.build.mktg.fireos"] || props["ro.build.version.fireos"] || props["ro.build.version.name"] || "",
    androidRelease: props["ro.build.version.release"] || "",
    abis: Object.freeze((props["ro.product.cpu.abilist"] || props["ro.product.cpu.abi"] || "").split(",").filter(Boolean)),
  });
}

const packageName = /^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$/i;
const syncProviders = new Set(["com.android.providers.calendar", "com.android.providers.contacts"]);

function readsPackages(args) {
  if (args[1] === "path") {
    return args.length === 5 && args[2] === "--user" && args[3] === "0" && packageName.test(args[4]);
  }
  if (args[1] !== "list" || args[2] !== "packages") return false;
  const options = args.slice(3);
  const owner = options.indexOf("--user");
  if (owner < 0 || options[owner + 1] !== "0") return false;
  options.splice(owner, 2);
  return options.every(word => ["-s", "-d", "--show-versioncode"].includes(word) || packageName.test(word));
}

function isRead(args) {
  const [program, verb] = args;
  switch (program) {
    case "pm": return readsPackages(args);
    case "am": return verb === "get-current-user" && args.length === 2;
    case "df": return verb === "-k" && args[2] === "/data" && args.length === 3;
    case "dumpsys":
      return (verb === "battery" && args.length === 2) ||
        (verb === "package" && args.length === 3 && packageName.test(args[2]));
    case "settings":
      if (verb !== "--user" || args[2] !== "0" || args[4] !== "global") return false;
      return (args[3] === "list" && args.length === 5) ||
        (args[3] === "get" && args.length === 6 && /^[a-z_]+$/i.test(args[5]));
    default: return false;
  }
}

function commandKind(args) {
  if (!Array.isArray(args) || !args.length || args.some(a => typeof a !== "string" || /[\x00-\x1f\x7f]/.test(a))) {
    throw new Error("Invalid tablet command.");
  }
  if (isRead(args)) return "read";
  if (isManagedChangeWrite(args)) return "write";
  if (args.length === 5 && args[0] === "pm" && args[1] === "enable" && args[2] === "--user" &&
      args[3] === "0" && syncProviders.has(args[4])) return "write";
  throw new Error("This command is outside the browser tools.");
}

export async function bindDevice(raw, locks = globalThis.navigator?.locks) {
  let connected = true;
  let writing = false;
  const disconnected = Promise.resolve(raw.disconnected).then(() => { connected = false; }, () => { connected = false; });
  function assertConnected() {
    if (!connected) throw new Error("USB disconnected. Reconnect and review the operation again.");
  }
  const device = await identify(raw);
  assertConnected();
  const original = JSON.stringify(device);
  const writeLimit = device.user !== 0 ? "Switch to the primary adult profile, then reconnect." :
    device.sdk < 23 ? "Tablet changes need Android SDK 23 or later." :
    !device.identityKey ? "The tablet needs a stable hardware identifier to save changes." :
    !locks?.request ? "This browser lacks the exclusive lock needed for tablet changes." : "";

  async function assertIdentity() {
    assertConnected();
    if (original !== JSON.stringify(await identify(raw))) {
      throw new Error("The tablet, profile or firmware changed. Reconnect and review again.");
    }
    assertConnected();
  }
  async function beforeWrite() {
    assertConnected();
    if (writeLimit || !writing) throw new Error(writeLimit || "Review the operation and acquire the tablet lock first.");
    await assertIdentity();
  }
  const session = Object.freeze({
    device, serial: device.serial, disconnected, assertIdentity, canWrite: !writeLimit, writeLimit,
    async shell(args) {
      assertConnected();
      if (commandKind(args) === "write") await beforeWrite();
      return raw.shell(args);
    },
    async install(file) { await beforeWrite(); return raw.install(file); },
    async hashRemote(path, maxBytes) { assertConnected(); return raw.hashRemote(path, maxBytes); },
    async readSharedFile(path, maxBytes) {
      if (device.user !== 0) throw new Error("File downloads require the primary adult profile.");
      await assertIdentity();
      const bytes = await raw.readSharedFile(path, maxBytes);
      await assertIdentity();
      return bytes;
    },
    async close() { connected = false; return raw.close(); },
  });
  guards.set(session, async (callback) => {
    assertConnected();
    if (writeLimit) throw new Error(writeLimit);
    if (writing) throw new Error("Another change is already running on this tablet.");
    return locks.request("fire-tools:usb:" + device.identityKey, {mode: "exclusive", ifAvailable: true}, async lock => {
      if (!lock) throw new Error("Another tab is changing this tablet. Wait for it to finish and review again.");
      await assertIdentity();
      writing = true;
      try { return await callback(); }
      finally { writing = false; }
    });
  });
  return session;
}

export function withDeviceLock(session, callback) {
  const guard = guards.get(session);
  if (!guard) throw new Error("Connect your tablet first.");
  return guard(callback);
}
