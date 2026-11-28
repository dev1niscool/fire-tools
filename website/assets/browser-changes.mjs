// The browser exposes only these fixed actions. Each package preset is checked
// against open_fire_toolkit.package_catalog by the handbook's regression tests.
const APPS = [
  ["com.amazon.dee.app", "Amazon Alexa", "complete"],
  ["com.amazon.venezia", "Amazon Appstore", "complete"],
  ["com.amazon.ags.app", "Amazon Games", "standard"],
  ["com.amazon.geo.client.maps", "Amazon Maps", "standard"],
  ["com.amazon.mp3", "Amazon Music", "standard"],
  ["com.amazon.kindle", "Amazon Newsstand (Kindle)", "standard"],
  ["com.amazon.avod", "Amazon Prime Video", "standard"],
  ["com.amazon.alexa.youtube.app", "Amazon YouTube", "standard"],
  ["com.audible.application.kindle", "Audible", "standard"],
  ["com.android.calculator2", "Calculator", "complete"],
  ["com.android.calendar", "Calendar", "complete"],
  ["com.android.camera2", "Camera", "complete"],
  ["com.android.deskclock", "Clock", "complete"],
  ["com.android.contacts", "Contacts", "complete"],
  ["com.amazon.zico", "Docs", "complete"],
  ["com.amazon.smartgenie", "Device Dashboard", "standard"],
  ["com.amazon.kindle.otter.oobe", "Device Setup", "complete", "protected"],
  ["com.android.email", "Email", "complete"],
  ["com.amazon.tahoe", "FreeTime (Amazon Kids)", "complete"],
  ["com.goodreads.kindle", "Goodreads", "standard"],
  ["com.amazon.csapp", "Help", "standard"],
  ["com.amazon.imdb.tv.mobile.app", "IMDb TV", "complete"],
  ["com.amazon.webapp", "Kindle Store", "standard"],
  ["com.amazon.ods.kindleconnect", "Mayday Sharing", "standard"],
  ["org.mopria.printplugin", "Mopria Print Service", "standard"],
  ["com.android.music", "Music", "standard"],
  ["com.amazon.kindle.personal_video", "My Videos", "standard"],
  ["com.amazon.iris", "News", "standard"],
  ["com.amazon.photos.importer", "Photo Importer", "standard"],
  ["com.amazon.photos", "Prime Photos (Amazon Photos)", "standard"],
  ["com.amazon.windowshop", "Shop Amazon", "standard"],
  ["com.amazon.cloud9", "Silk Browser", "complete"],
  ["com.kingsoft.office.amz", "WPS Office", "standard"],
  ["com.washingtonpost.rainbow", "Washington Post", "standard"],
  ["com.amazon.weather", "Weather", "standard"],
];
const UPDATERS = [
  ["com.amazon.device.software.ota", "Fire OS updater"],
  ["com.amazon.device.software.ota.override", "Fire OS updater override"],
];
const OFFERS = [["com.amazon.kindle.kso", "Special Offers"]];
const packageGroups = {debloat: APPS, updates: UPDATERS, offers: OFFERS};
const ADS = "LOCKSCREEN_AD_ENABLED";
const ANIMATIONS = ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"];
const DNS = ["private_dns_specifier", "private_dns_mode"];
const dnsPresets = [
  ["cloudflare", "Cloudflare", "one.one.one.one", "Provides unfiltered DNS."],
  ["cloudflare-family", "Cloudflare for Families", "family.cloudflare-dns.com", "Filters malware and adult domains."],
  ["quad9", "Quad9", "dns.quad9.net", "Filters known malicious domains."],
  ["adguard", "AdGuard DNS", "dns.adguard-dns.com", "Filters advertising and tracking domains."],
  ["adguard-family", "AdGuard Family", "family.adguard-dns.com", "Filters ads, trackers and adult domains and enables Safe Search where supported."],
  ["mullvad-adblock", "Mullvad Adblock", "adblock.dns.mullvad.net", "Filters advertising and tracking domains."],
];
const MODE_VERBS = ["default-state", "enable", "disable", "disable-user", "disable-until-used"];
const groups = {
  debloat: APPS.filter(row => !row[3]).map(row => row[0]),
  updates: UPDATERS.map(row => row[0]), offers: OFFERS.map(row => row[0]), ads: [ADS], animations: ANIMATIONS, dns: DNS,
};
const groupLabels = {debloat:"Amazon apps", ads:"Lock-screen ads", offers:"Lock-screen ads", animations:"Animation speed",
  updates:"Firmware updates", dns:"Private DNS"};
const action = (family, id, label, description) => ({group: groupLabels[family], family, id, label, description});
export const changeActions = [
  action("debloat", "debloat-standard", "Standard debloat", "Preview the 22-app recommended preset, including Kindle books and Prime Video."),
  action("debloat", "debloat-complete", "Complete debloat", "Preview the larger preset, including Silk, Camera and the Amazon Appstore."),
  action("debloat", "debloat-undo", "Restore debloated apps", "Restore the owner states saved by this browser."),
  action("ads", "ads-disable", "Try the lock-screen ad setting", "Try the temporary setting, then check the actual lock screen."),
  action("ads", "ads-undo", "Restore the ad setting", "Return the saved setting to its original value."),
  action("offers", "offers-disable", "Try disabling Special Offers", "Try disabling the installed Special Offers system package for the primary profile without a fee."),
  action("offers", "offers-undo", "Restore the Special Offers package", "Restore the exact primary-profile package mode saved in this browser."),
  action("animations", "animations-fast", "Faster animations (0.5×)", "Change the window, transition and animator scales."),
  action("animations", "animations-standard", "Standard animations (1×)", "Set all three animation scales to standard speed."),
  action("animations", "animations-undo", "Restore animation speeds", "Restore the three scales to their original values."),
  action("updates", "updates-status", "Check updater packages", "Read the two known updater packages for the primary profile."),
  action("updates", "updates-disable", "Try disabling system updates", "Disable eligible updater packages after reviewing their states."),
  action("updates", "updates-undo", "Restore updater packages", "Return changed updater packages to their saved owner states."),
  ...dnsPresets.map(([id, label, hostname, description]) =>
    action("dns", "dns-" + id, "Use " + label + " Private DNS", hostname + " · " + description)),
  action("dns", "dns-auto", "Set Private DNS to Automatic", "Use Android’s automatic resolver selection."),
  action("dns", "dns-undo", "Restore Private DNS", "Restore the saved resolver mode and hostname."),
];

function validValue(group, key, value) {
  if (!groups[group].includes(key)) return false;
  if (Object.hasOwn(packageGroups, group)) {
    return typeof value === "string" && /^(enabled:[01]|disabled:[0234]|enabled:4)$/.test(value);
  }
  if (value === null) return true;
  if (typeof value !== "string") return false;
  if (group === "ads") return /^-?\d{1,9}$/.test(value);
  if (group === "animations") return /^\d{1,3}(?:\.\d{1,12})?$/.test(value) && Number(value) <= 100;
  if (key === "private_dns_mode") return ["off", "opportunistic", "hostname", ""].includes(value);
  return value === "" || (value.length <= 253 && value.split(".").every(part =>
    /^[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?$/i.test(part)));
}

// Also used at the USB session boundary. A UI or planner mistake must not
// turn a reviewed action into a different package, setting, or Android user.
export function isManagedChangeWrite(args) {
  if (!Array.isArray(args)) return false;
  if (args[0] === "pm") {
    return args.length === 5 && MODE_VERBS.includes(args[1]) && args[2] === "--user" && args[3] === "0" &&
      [groups.debloat, groups.updates, groups.offers].some(names => names.includes(args[4]));
  }
  const [program, flag, user, verb, table, key, value] = args;
  if (program !== "settings" || flag !== "--user" || user !== "0" || table !== "global") return false;
  const group = ["ads", "animations", "dns"].find(name => groups[name].includes(key));
  if (!group) return false;
  if (verb === "delete") return args.length === 6;
  return verb === "put" && args.length === 7 && typeof value === "string" && validValue(group, key, value);
}

function readJournal(storage, key, group) {
  let raw;
  try { raw = storage.getItem(key); }
  catch { throw Error("Allow this site to store undo information before changing the tablet."); }
  if (raw === null) return {raw, records: new Map()};
  try {
    if (raw.length > 24000) throw Error();
    const doc = JSON.parse(raw);
    if (doc.version !== 1 || doc.key !== key || !Array.isArray(doc.rows) || doc.rows.length > groups[group].length) throw Error();
    const records = new Map();
    for (const row of doc.rows) {
      if (!Array.isArray(row) || row.length !== 2 || records.has(row[0]) || !validValue(group, row[0], row[1])) throw Error();
      records.set(row[0], row[1]);
    }
    return {raw, records};
  } catch { throw Error("This tablet’s saved undo record is invalid. The browser has kept it unchanged."); }
}

function assertJournal(storage, key, raw) {
  if (storage.getItem(key) !== raw) throw Error("The browser’s undo record changed. Review the action again.");
}

function saveJournal(storage, key, expected, records) {
  assertJournal(storage, key, expected);
  const raw = records.size ? JSON.stringify({version:1, key, rows:[...records]}) : null;
  try {
    if (raw === null) storage.removeItem(key);
    else storage.setItem(key, raw);
    if (storage.getItem(key) !== raw) throw Error();
  } catch { throw Error("Could not save or update the undo record in this browser. Check site storage, then review again."); }
  return raw;
}

async function checked(session, args) {
  const value = await session.shell(args);
  if (typeof value !== "string" || value.length > 1024 * 1024 ||
      /^(?:Error(?:\s|:)|Failure(?:\s|:)|Security exception|Permission denial|Exception occurred|java\.lang\.SecurityException)/im.test(value)) {
    throw Error("Android rejected the request or returned an unreadable response. Review the tablet’s state.");
  }
  return value.replace(/\r\n/g, "\n");
}

async function listPackages(session, args) {
  const text = await checked(session, ["pm", "list", "packages", "--user", "0", ...args]);
  const names = new Set();
  for (const line of text.split("\n").filter(Boolean)) {
    const match = /^package:([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$/.exec(line);
    if (!match) throw Error("Unexpected package inventory response.");
    names.add(match[1]);
  }
  return names;
}

async function inventory(session, group, name) {
  const filter = name ? [name] : [];
  const installed = await listPackages(session, filter);
  const disabled = await listPackages(session, ["-d", ...filter]);
  if ([...disabled].some(p => !installed.has(p))) throw Error("The package inventory changed. Review again.");
  const system = group !== "debloat" ? await listPackages(session, ["-s", ...filter]) : null;
  return {installed, disabled, system};
}

async function ownerMode(session, name) {
  const dump = await checked(session, ["dumpsys", "package", name]);
  const lines = dump.split("\n").filter(line => line.trim());
  let block = false, active = false, found = false;
  let rows = [];
  if (lines.length && lines.every(line => /^ *User \d+: [^\r\n]*$/.test(line))) {
    rows = lines.map(line => line.trim()).filter(line => line.startsWith("User 0: "));
  } else {
    for (const line of lines) {
      if (!line.startsWith(" ")) {
        block = line.trimEnd() === "Packages:";
        active = false;
      } else if (block && !line.startsWith("    ")) {
        const match = /^  Package \[([^\]]+)\](?: \([0-9a-f]+\))?: *$/i.exec(line);
        active = match?.[1] === name;
        if (active && found) throw Error("Ambiguous active package record for " + name);
        if (active) found = true;
      } else if (active && line.startsWith("    User 0: ")) {
        rows.push(line.trim());
      }
    }
  }
  if (rows.length === 1) {
    const fields = rows[0].split(/ +/);
    const modes = fields.filter(x => x.startsWith("enabled="));
    const installed = fields.filter(x => x.startsWith("installed="));
    if (installed.length === 1 && installed[0] === "installed=true" && modes.length === 1 && /^enabled=[0-4]$/.test(modes[0])) {
      return modes[0].slice(-1);
    }
  }
  throw Error("Cannot confirm the exact primary-profile package state for " + name);
}

async function packageState(session, group, key, inv) {
  if (!inv.installed.has(key)) return {skip:"not installed for owner"};
  if (inv.system && !inv.system.has(key)) return {skip:"not an installed system package"};
  const mode = await ownerMode(session, key);
  const before = (inv.disabled.has(key) ? "disabled:" : "enabled:") + mode;
  if (!validValue(group, key, before)) throw Error("Inconsistent Android package state for " + key);
  return {before};
}

async function globalValues(session, group) {
  const text = await checked(session, ["settings", "--user", "0", "list", "global"]);
  if (!text.trim()) throw Error("The global settings listing was empty; the previous values could not be verified.");
  const values = new Map();
  for (const line of text.split("\n").filter(Boolean)) {
    const split = line.indexOf("=");
    if (split < 1) throw Error("Cannot read the global settings listing reliably.");
    const key = line.slice(0, split);
    if (!groups[group].includes(key)) continue;
    const value = line.slice(split + 1);
    if (values.has(key) || !validValue(group, key, value)) throw Error("Cannot safely read and restore " + key);
    values.set(key, value);
  }
  return values;
}

function formatValue(value) {
  return value === null ? "not set" : value === "" ? '""' : value;
}

function describe(row) {
  const name = row.label === row.key ? row.key : row.label + " (" + row.key + ")";
  if (row.skip) return name + " — skipped: " + row.skip + ".";
  if (row.to === undefined || row.to === row.before) return name + " — " + formatValue(row.before) + ".";
  return name + " — " + formatValue(row.before) + " → " + formatValue(row.to) + ".";
}

async function writeValue(session, isPackage, key, value) {
  if (isPackage) {
    const verb = MODE_VERBS[Number(value.split(":")[1])];
    await checked(session, ["pm", verb, "--user", "0", key]);
  } else {
    const args = value === null ? ["delete", "global", key] : ["put", "global", key, value];
    await checked(session, ["settings", "--user", "0", ...args]);
  }
}

export async function previewChange(session, device, id, storageOverride) {
  const spec = changeActions.find(item => item.id === id);
  if (!spec) throw Error("Unknown browser tool.");
  const {family:group, label:title} = spec;
  const isPackage = Object.hasOwn(packageGroups, group);
  const preset = group === "dns" ? dnsPresets.find(([name]) => id === "dns-" + name) : undefined;
  const isUndo = id.endsWith("-undo");
  const status = id === "updates-status";
  if (!device.model || device.manufacturer?.toLowerCase() !== "amazon") {
    throw Error("Select an identified Amazon Fire tablet.");
  }
  if (!status && (device.user !== 0 || !Number.isInteger(device.sdk) || device.sdk < 23)) {
    throw Error("Use the primary adult profile (User 0) on a tablet with Android SDK 23 or later.");
  }
  if (group === "dns" && device.sdk < 28) throw Error("Private DNS requires Android 9 (SDK 28) or newer.");
  let storage, journal = {raw:null, records:new Map()}, key;
  if (!status) {
    try { storage = storageOverride ?? globalThis.localStorage; }
    catch { throw Error("Allow this site to store undo information before changing the tablet."); }
    // bindDevice hashes the physical serial, manufacturer and model. The
    // WebUSB serial descriptor itself can be absent or change across sessions.
    if (!/^[0-9a-f]{64}$/.test(device.identityKey || "")) {
      throw Error("A stable hardware identifier is required to save undo information.");
    }
    key = "fire-tools.browser.undo.v1." + group + "." + device.identityKey;
    journal = readJournal(storage, key, group);
  }
  if (isUndo && !journal.records.size) {
    return {title, details:["This browser has no saved "+group+" changes for this tablet."], warnings:[], apply:null};
  }

  const rows = [];
  const warnings = [];
  if (isPackage) {
    const data = packageGroups[group];
    const inv = await inventory(session, group);
    for (const [name, label, tier, protection] of data) {
      if (isUndo && !journal.records.has(name)) continue;
      if (id === "debloat-standard" && tier !== "standard") continue;
      const state = protection ? {skip:"protected"} : await packageState(session, group, name, inv);
      const row = {key:name, label, ...state};
      if (!row.skip && !status) {
        if (isUndo) row.to = journal.records.get(name);
        else if (row.before.startsWith("enabled:")) row.to = "disabled:3";
      }
      rows.push(row);
    }
    if (id === "debloat-complete") warnings.push("This can disable Silk, the Amazon Appstore, Alexa, Camera and Email. Cancel if you need an app in the list.");
    if (group === "offers") warnings.push("This fee-free experiment only verifies the package mode. Fire OS may protect the package or continue showing ads. Lock and wake the tablet to check the lock screen.");
    if (group === "updates") warnings.push("Fire OS may protect these packages or deliver updates another way. Disabling them can delay security patches.");
  } else {
    warnings.push("These settings apply to all profiles on the tablet.");
    const snapshot = await globalValues(session, group);
    let keys = [...groups[group]];
    if (id === "dns-auto") keys = ["private_dns_mode"];
    if (group === "dns" && isUndo && journal.records.get("private_dns_mode") !== "hostname") keys.reverse();
    for (const name of keys) {
      if (isUndo && !journal.records.has(name)) continue;
      const before = snapshot.get(name) ?? null;
      let to;
      if (isUndo) to = journal.records.get(name);
      else if (group === "ads") to = "0";
      else if (group === "animations") to = id === "animations-fast" ? "0.5" : "1";
      else if (name === "private_dns_specifier") to = preset[2];
      else to = id === "dns-auto" ? "opportunistic" : "hostname";
      rows.push({key:name, label:name, before, to});
    }
    if (group === "ads" && !isUndo) warnings.push("Fire OS can ignore or reset this setting. Lock and wake the tablet to check whether ads actually disappear.");
    if (preset) warnings.push(preset[3] + " " + preset[1] + " can see the domain names requested through this resolver. Test a website after applying it.");
  }

  const details = rows.map(describe);
  const changes = rows.filter(row => !row.skip && row.to !== undefined && (isUndo || row.to !== row.before));
  if (!changes.length || status) return {title, details, warnings, apply:null};
  warnings.push("Keep this browser profile and its site data for undo. Each accepted change is checked on the tablet.");
  if (isUndo) warnings.push("Rows already at their saved value only clear the corresponding recovery entry.");
  if (isPackage && !isUndo) warnings.push("Packages are disabled for the primary profile. App data is preserved.");
  const readOne = async name => {
    if (!isPackage) return (await globalValues(session, group)).get(name) ?? null;
    const inv = await inventory(session, group, name);
    return (await packageState(session, group, name, inv)).before;
  };
  const apply = async (report = () => {}) => {
    const records = new Map(journal.records);
    let expected = journal.raw;
    const reviewed = new Map(rows.filter(row => !row.skip && row.before !== undefined)
      .map(row => [row.key, row.before]));
    const checkSettings = async () => {
      const values = await globalValues(session, group);
      for (const [name, value] of reviewed) {
        if ((values.get(name) ?? null) !== value) throw Error(name + " changed. Review again before continuing.");
      }
    };
    const checkPackages = async () => {
      const inv = await inventory(session, group);
      for (const row of changes) {
        const state = await packageState(session, group, row.key, inv);
        if (state.before !== reviewed.get(row.key)) throw Error(row.label + " changed. Review again before continuing.");
      }
    };
    const checkBatch = isPackage ? checkPackages : checkSettings;
    assertJournal(storage, key, expected);
    await checkBatch();
    for (const row of changes) {
      assertJournal(storage, key, expected);
      if (isPackage) {
        if (await readOne(row.key) !== row.before) throw Error(row.label + " changed. Review again before continuing.");
      } else {
        // A resolver mode and its hostname must remain the pair that was reviewed.
        await checkSettings();
      }
      if (row.before === row.to) continue;
      if (!isUndo && !records.has(row.key)) {
        records.set(row.key, row.before);
        expected = saveJournal(storage, key, expected, records);
      }
      assertJournal(storage, key, expected);
      report("Requesting change to " + row.label + ". Its previous value is saved.");
      await writeValue(session, isPackage, row.key, row.to);
      if (await readOne(row.key) !== row.to) {
        throw Error("Could not verify " + row.label + " on the tablet. Reconnect and review the saved undo.");
      }
      reviewed.set(row.key, row.to);
      report("Verified " + row.label + " — " + formatValue(row.to));
    }
    await checkBatch();
    await session.assertIdentity();
    assertJournal(storage, key, expected);
    if (isUndo) {
      // Preserve the complete record if a restore fails. Already-restored
      // values are verified without rewriting them on a subsequent attempt.
      for (const row of changes) records.delete(row.key);
      saveJournal(storage, key, expected, records);
    }
    return isUndo ? "Reviewed values restored and verified." : "Reviewed changes verified. Undo is saved in this browser.";
  };
  return {title, details, warnings, apply};
}
