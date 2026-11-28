import { addStoredPack, readStoredPack, withPackLock } from "./browser-apk-library.mjs";

// These are whole-file identities from the project's SDK signer, manifest and
// antivirus review. No APK or remotely supplied verification catalog is used.
const account = "com.google.android.gsf.login";
const core = ["com.google.android.gsf", "com.google.android.gms", "com.android.vending"];
const providers = new Map([
  ["com.google.android.syncadapters.calendar", "com.android.providers.calendar"],
  ["com.google.android.syncadapters.contacts", "com.android.providers.contacts"],
]);
const records = [
  [account, "Google Account Manager 7.1.2", 25, 23, [], 6552461,
    "3324ee2f67d23848ae3d9086f20ada10f2cb0dbb6d202067b918cc4fb4d167be"],
  [core[0], "Google Services Framework 10-6494331", 29, 29, [], 4296499,
    "32156365bcff60f2a0576abe1f15ef7e2b705aea9536bfcbd6fef784d131ccb5"],
  [core[1], "Google Play services 25.20.37", 252037022, 30, ["arm64-v8a"], 228440903,
    "1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07"],
  [core[2], "Google Play Store 36.3.12-21", 83631210, 21, ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"], 59468089,
    "03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa"],
  ["com.google.android.syncadapters.calendar", "Google Calendar Sync 2021.23.3", 2017005136, 30, [], 2450495,
    "87fb81b621d060c9779f0942ea379f7cad4f7b551b4d9f1d651a8980f3a6f749"],
  ["com.google.android.syncadapters.contacts", "Google Contacts Sync 11", 30, 30, [], 2763377,
    "e6c7f541dba8c334ff416ea6e63df6c6b2a5991db54ac99b5c97d0f2b62068b3"],
].map(([id, name, code, minSdk, abis, size, sha256]) => ({
  package: id, name, code, minSdk, abis: Object.freeze(abis), size, sha256,
  partialScan: id === core[1] || id === core[2],
}));

async function inspect(files, stage) {
  if (files.length < 1 || files.length > records.length) throw Error("Choose one to six audited standalone APKs.");
  const matches = new Map();
  for (const file of files) {
    const record = records.find(row => row.size === file.size);
    if (!record) throw Error(file.name + " does not match the size of an audited Google APK.");
    const bytes = await file.arrayBuffer();
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    const digest = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
    if (bytes.byteLength !== record.size || digest !== record.sha256) {
      throw Error(file.name + " does not match the audited Google APK bytes.");
    }
    if (matches.has(record.package)) throw Error("Duplicate component: " + record.package);
    const match = {...record, filename: file.name};
    // Retain the private array that was actually hashed. Creating another large
    // Blob can exhaust the private Chrome profile's memory-backed Blob storage.
    if (stage) match.bytes = new Uint8Array(bytes);
    matches.set(record.package, match);
  }
  return records.filter(row => matches.has(row.package)).map(row => matches.get(row.package));
}

export async function inspectApks(files) {
  return inspect(Array.from(files), false);
}

// The reusable personal pack contains the four APKMirror reference variants.
// The same verifier still handles optional individually selected sync adapters.
async function verifyPersonalPack(files, stage = false) {
  const primary = records.filter(row => row.package === account || core.includes(row.package));
  if (!Array.isArray(files) || files.length !== primary.length || !primary.every(row =>
    files.some(file => file instanceof File && file.size === row.size))) {
    throw Error("Choose the four audited APKs: Account Manager, Services Framework, Play services and Play Store.");
  }
  return inspect(files, stage);
}

async function checkedStoredPack(files, signal) {
  if (files === undefined) throw Error("No saved APK set. Choose the four files on your computer first.");
  if (!Array.isArray(files)) throw Error("The saved APK set is damaged. Forget it and choose the four files again.");
  try { await verifyPersonalPack(files); }
  catch (error) {
    throw Error("The saved APK set failed verification. Forget it and choose the four files again. " + error.message);
  }
  signal?.throwIfAborted();
  return files;
}

export async function savePack(files, signal) {
  return withPackLock("exclusive", async () => {
    const checked = await verifyPersonalPack(files, true);
    const existing = await readStoredPack(signal);
    if (existing !== undefined) return checkedStoredPack(existing, signal);
    // Chrome can persist a disk-backed File as a reference to its original
    // path. Make independent Files from the verified bytes for the first save.
    const snapshots = checked.map(row => new File([row.bytes], row.package + ".apk",
      {type: "application/vnd.android.package-archive", lastModified: 0}));
    await verifyPersonalPack(snapshots);
    await addStoredPack(snapshots, signal);
    return checkedStoredPack(await readStoredPack(signal), signal);
  }, signal);
}

export async function loadPack(signal) {
  return withPackLock("shared", async () => checkedStoredPack(await readStoredPack(signal), signal), signal);
}

function checkDevice(session, device) {
  const sameTablet = session.device ? session.device === device : Boolean(device.serial && device.serial === session.serial);
  if (!sameTablet || !device.model ||
      device.manufacturer?.trim().toLowerCase() !== "amazon" || device.user !== 0 ||
      !Number.isSafeInteger(device.sdk) || device.sdk < 23 || !Array.isArray(device.abis)) {
    throw Error("Select the connected Amazon tablet in its primary adult profile (user 0) before installing.");
  }
}

function compatible(row, device) {
  if (device.sdk < row.minSdk || (row.abis.length && !row.abis.some(abi => device.abis.includes(abi)))) {
    throw Error(row.name + " needs Android API " + row.minSdk + " or later" +
      (row.abis.length ? " and a supported architecture (" + row.abis.join(", ") + ")" : "") +
      ". These audited files do not fit this tablet.");
  }
}

async function inventory(session, flag) {
  const raw = await session.shell(["pm", "list", "packages", flag, "--user", "0"]);
  const versioned = flag === "--show-versioncode";
  const packages = new Map();
  for (const line of raw.trim().split(/\r?\n/).filter(Boolean)) {
    const match = /^package:([A-Za-z0-9_.]+)(?: versionCode:([0-9]+))?$/.exec(line.trim());
    if (!match || versioned !== Boolean(match[2]) || packages.has(match[1])) {
      throw Error("Could not read the owner’s installed package list. Reconnect and review again.");
    }
    packages.set(match[1], match[2] || "");
  }
  if (versioned && !packages.size) throw Error("The tablet returned an empty package inventory.");
  return packages;
}

async function basePath(session, id) {
  const output = await session.shell(["pm", "path", "--user", "0", id]);
  const match = /^package:(\/data\/app\/[A-Za-z0-9_./~+=-]+\.apk)$/.exec(output.trim());
  if (!match || match[1].length > 1024 || match[1].split("/").slice(1).some(part => !part || part === "." || part === "..")) {
    throw Error("Expected one installed APK path under /data/app for " + id + ". Use the desktop verifier for split or system builds.");
  }
  return match[1];
}

async function verifyInstalled(session, row) {
  const path = await basePath(session, row.package);
  const observed = await session.hashRemote(path, row.size);
  if (observed.sha256 !== row.sha256 || observed.size !== row.size) {
    throw Error("Installed bytes differ from the audited file for " + row.package + ".");
  }
  if (await basePath(session, row.package) !== path) throw Error(row.package + " changed during readback. Review again.");
}

async function preparation(session, device, apks) {
  const selected = new Set(apks.map(row => row.package));
  const syncOnly = apks.every(row => providers.has(row.package));
  if (!syncOnly && !core.every(id => selected.has(id))) {
    throw Error("Select Services Framework, Play services and Play Store together. Account Manager and the two sync adapters are optional.");
  }
  for (const apk of apks) compatible(apk, device);
  const installed = await inventory(session, "--show-versioncode");
  const disabled = await inventory(session, "-d");
  const neededProviders = apks.map(row => providers.get(row.package)).filter(Boolean);
  const system = neededProviders.length ? await inventory(session, "-s") : new Map();
  for (const id of neededProviders) {
    if (!system.has(id) || !installed.has(id)) throw Error("The owner profile needs the built-in system provider " + id + ".");
  }

  const dependencies = syncOnly ? [...core] : [];
  if (installed.has(account) && !selected.has(account)) dependencies.push(account);
  for (const id of dependencies) {
    if (!installed.has(id) || disabled.has(id)) throw Error("Install or enable " + id + " before adding these Google components.");
    const row = records.find(record => record.package === id);
    compatible(row, device);
    await verifyInstalled(session, row);
  }

  const actions = [];
  for (const apk of apks) {
    const version = installed.get(apk.package);
    if (version !== undefined && BigInt(version) > BigInt(apk.code)) {
      throw Error("A newer version of " + apk.package + " is installed. This browser installer does not downgrade apps.");
    }
    if (disabled.has(apk.package)) throw Error("Enable " + apk.package + " for the owner before installing.");
    const current = version === String(apk.code);
    if (current) await verifyInstalled(session, apk);
    actions.push({id: apk.package, version: version ?? null, current});
  }
  return {actions, dependencies, enable: neededProviders.filter(id => disabled.has(id))};
}

export async function previewGoogle(session, device, files) {
  checkDevice(session, device);
  const selection = Array.from(files);
  const apks = await inspectApks(selection);
  const reviewed = await preparation(session, device, apks);
  const details = apks.map((apk, i) => {
    const action = reviewed.actions[i];
    const verb = action.current ? "Keep verified" : action.version === null ? "Install" : "Update";
    return verb + " " + apk.name + " (" + apk.package + ") for user 0. SHA-256 " + apk.sha256;
  });
  for (const id of reviewed.dependencies) details.push("Verified the installed dependency " + id + " against its audit record.");
  for (const id of reviewed.enable) details.push("Enable " + id + " for user 0 after verifying the sync adapter.");
  const warnings = ["Installation is sequential. Earlier successful installs remain if a later step fails.",
    "Google Play sign-in and app compatibility must be checked on the tablet."];
  if (apks.some(row => row.partialScan)) warnings.push("One legacy antivirus check timed out on the audited Play services and Play Store files.");
  if (apks.some(row => row.package === core[2]) && !apks.some(row => row.package === account)) {
    warnings.push("The four-file Fire HD 10 reference setup also includes Google Account Manager.");
  }

  return {
    title: "Install verified Google components", details, warnings,
    async apply(report = () => {}) {
      const snapshot = await inspect(selection, true);
      if (snapshot.some((row, i) => row.sha256 !== apks[i].sha256)) throw Error("Selected APKs changed. Review again.");
      const current = await preparation(session, device, snapshot);
      if (JSON.stringify(current) !== JSON.stringify(reviewed)) throw Error("The owner’s package or provider state changed. Review again.");
      for (const [i, apk] of snapshot.entries()) {
        if (reviewed.actions[i].current) {
          report("Verified existing " + apk.package + " for owner user 0.");
          continue;
        }
        const version = (await inventory(session, "--show-versioncode")).get(apk.package) ?? null;
        if (version !== reviewed.actions[i].version) throw Error(apk.package + " changed since review. Check earlier results.");
        report("Installing " + apk.name + "…");
        try {
          await session.install(apk.bytes);
          await verifyInstalled(session, apk);
          const active = await inventory(session, "--show-versioncode");
          if (active.get(apk.package) !== String(apk.code) || (await inventory(session, "-d")).has(apk.package)) {
            throw Error("The expected version is not enabled for owner user 0.");
          }
        } catch (error) {
          throw Error(apk.package + " may already be installed. Check its state before retrying. " + error.message);
        }
        report("Verified installed bytes and owner state for " + apk.package + ".");
      }
      for (const id of reviewed.enable) {
        const system = await inventory(session, "-s");
        const disabled = await inventory(session, "-d");
        if (!system.has(id) || !disabled.has(id)) throw Error("The system provider changed. Review again before enabling " + id + ".");
        await session.shell(["pm", "enable", "--user", "0", id]);
        if (!(await inventory(session, "-s")).has(id) || (await inventory(session, "-d")).has(id)) {
          throw Error("Could not verify the enabled state of " + id + ". Check the installed adapters before retrying.");
        }
        report("Verified enabled system provider " + id + ".");
      }
      report("Open Play Store on the tablet to check sign-in.");
    },
  };
}
