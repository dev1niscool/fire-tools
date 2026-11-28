// Only these global settings and the owner package inventory enter the download.
const animationSettings = ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"];

function publicDevice({manufacturer, model, fireOS, sdk, abis, user}) {
  return {manufacturer, model, fireOS, sdk, abis, user};
}

function requireOwner(session) {
  if (session.device.user !== 0) {
    throw new Error("Select the primary adult profile (owner user 0) to read the app inventory.");
  }
}

function batteryPercent(text) {
  const level = /^\s*level:\s*(\d+)\s*$/m.exec(text);
  const scale = /^\s*scale:\s*(\d+)\s*$/m.exec(text);
  if (!level || !scale) return null;
  const value = Number(level[1]);
  const maximum = Number(scale[1]);
  if (!Number.isSafeInteger(maximum) || maximum <= 0 || value > maximum) return null;
  return Math.round(100 * value / maximum);
}

function dataStorage(text) {
  // Header spelling varies across Android releases. Read the row mounted on /data.
  const row = /(?:^|[ \t])(\d+)[ \t]+\d+[ \t]+(\d+)[ \t]+\d+%[ \t]+\/data[ \t]*\r?$/m.exec(text);
  if (!row) return null;
  const totalKiB = Number(row[1]);
  const availableKiB = Number(row[2]);
  if (!Number.isSafeInteger(totalKiB) || totalKiB < 1 || availableKiB > totalKiB) return null;
  return {totalKiB, availableKiB};
}

async function diagnostics(session) {
  // Some builds deny these diagnostics. The caller still verifies the device
  // identity after collection so disconnection cannot yield a partial export.
  const battery = await session.shell(["dumpsys", "battery"]).catch(() => "");
  const storage = await session.shell(["df", "-k", "/data"]).catch(() => "");
  return {batteryPercent: batteryPercent(battery), dataStorage: dataStorage(storage)};
}

export async function readReport(session) {
  await session.assertIdentity();
  const info = publicDevice(session.device);
  const data = await diagnostics(session);
  await session.assertIdentity();
  const storage = data.dataStorage;
  const gib = kib => Number((kib / (1024 ** 2)).toFixed(1)) + " GiB";
  return [
    "Tablet: " + info.manufacturer + " " + info.model,
    "Fire OS: " + (info.fireOS || "unavailable"),
    "Android API: " + info.sdk,
    "App architectures: " + (info.abis.join(", ") || "unavailable"),
    "Active Android user: " + info.user + (info.user === 0 ? " (owner)" : ""),
    "Battery: " + (data.batteryPercent === null ? "unavailable" : data.batteryPercent + "%"),
    "Data storage: " + (storage ? gib(storage.availableKiB) + " available of " + gib(storage.totalKiB) : "unavailable"),
  ].join("\n");
}

function packageNames(text) {
  const names = new Set();
  for (const line of text.trim().split(/\r?\n/)) {
    if (!line) continue;
    const match = /^package:([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$/.exec(line);
    if (!match) throw new Error("The tablet returned an unreadable package list. Refresh and try again.");
    names.add(match[1]);
  }
  return names;
}

async function ownerPackages(session) {
  const list = ["pm", "list", "packages", "--user", "0"];
  const installed = packageNames(await session.shell(list));
  const disabled = packageNames(await session.shell([...list, "-d"]));
  if (!installed.size || [...disabled].some(name => !installed.has(name))) {
    throw new Error("The owner package lists are empty or inconsistent. Read the inventory again.");
  }
  return [...installed].sort().map(name => ({package: name, state: disabled.has(name) ? "disabled" : "enabled"}));
}

export async function readInstalledPackages(session) {
  await session.assertIdentity();
  requireOwner(session);
  const packages = await ownerPackages(session);
  await session.assertIdentity();
  return packages;
}

async function selectedSettings(session) {
  const keys = session.device.sdk >= 28 ? [...animationSettings, "private_dns_mode"] : animationSettings;
  const settings = {};
  for (const key of keys) {
    const value = (await session.shell(["settings", "--user", "0", "get", "global", key])).trim();
    if (value === "null") {
      settings[key] = null;
      continue;
    }
    const valid = key === "private_dns_mode"
      ? ["", "off", "opportunistic", "hostname"].includes(value)
      : value.length <= 32 && /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value) && Number.isFinite(Number(value));
    if (!valid) throw new Error("The tablet returned an unreadable setting for " + key + ".");
    settings[key] = value;
  }
  return settings;
}

export async function createInventoryExport(session) {
  await session.assertIdentity();
  requireOwner(session);
  const report = {
    format: "fire-tools.browser-inventory.v1",
    capturedAt: new Date().toISOString(),
    device: publicDevice(session.device),
    diagnostics: await diagnostics(session),
    settings: await selectedSettings(session),
    packages: await ownerPackages(session),
  };
  await session.assertIdentity();
  return JSON.stringify(report, null, 2) + "\n";
}

export async function previewSharedFile(session, folder, relativePath) {
  requireOwner(session);
  if (!["Download", "DCIM", "Pictures"].includes(folder) || typeof relativePath !== "string" ||
      !relativePath || relativePath.length > 1024 || /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\\]/u.test(relativePath) ||
      relativePath.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error("Enter a file path relative to Download, DCIM or Pictures.");
  }
  const limit = 32 * 1024 * 1024;
  const bytes = await session.readSharedFile("/storage/emulated/0/" + folder + "/" + relativePath, limit);
  if (!(bytes instanceof Uint8Array) || bytes.length > limit) throw new Error("Unexpected shared file transfer.");
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const sha256 = Array.from(digest, value => value.toString(16).padStart(2, "0")).join("");
  return {
    filename: relativePath.split("/").at(-1), size: bytes.length, sha256,
    blob: new Blob([bytes], {type: "application/octet-stream"}),
  };
}
