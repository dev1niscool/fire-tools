import { connectDevice, readInventory, withDeviceLock } from "./browser-device.mjs";
import { inspectApks, previewGoogle, savePack, loadPack } from "./browser-apks.mjs";
import { forgetPack } from "./browser-apk-library.mjs";
import { changeActions, previewChange } from "./browser-changes.mjs";
import { readReport, createInventoryExport, previewSharedFile } from "./browser-report.mjs";

const get = id => document.getElementById("web-" + id);
const tabs = ["google", "changes", "device"].map(name => get("tab-" + name));
const supportsUsb = window.isSecureContext && typeof navigator.usb?.requestDevice === "function";
let session = null;
let task = null;
let review = null;
let stagedFile = null;
let loadedPack = null;

function selectedApks() {
  return loadedPack || Array.from(get("google-files").files);
}

function listText(element, items) {
  const entries = items.map(text => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  });
  element.replaceChildren(...entries);
}

function log(text) {
  const item = document.createElement("li");
  item.textContent = text;
  get("log").append(item);
  while (get("log").children.length > 80) get("log").firstElementChild.remove();
  get("activity").hidden = false;
}

function message(text, trigger, isError = false) {
  const node = get("message");
  (trigger.closest(".web-buttons") || trigger).after(node);
  node.textContent = text;
  node.dataset.error = String(isError);
  log(text);
}

function refresh() {
  const connecting = task?.mode === "connect";
  const busy = Boolean(task);
  const writable = Boolean(session?.canWrite && navigator.locks);
  const selected = selectedApks().length > 0;
  get("connect").hidden = Boolean(session) || connecting;
  get("connect").disabled = busy || !supportsUsb;
  get("disconnect").hidden = !session && !connecting;
  get("disconnect").disabled = busy && !connecting;
  get("disconnect").textContent = connecting ? "Cancel connection" : "Disconnect";
  get("state").dataset.state = session ? "connected" : connecting ? "connecting" : "disconnected";
  get("state").textContent = session ? "Connected" : connecting ? "Connecting" : "Disconnected";
  for (const tab of tabs) tab.disabled = busy;
  get("action").disabled = busy;
  get("google-files").disabled = busy;
  get("pack-selection").hidden = !loadedPack;
  get("pack-save").disabled = busy || get("google-files").files.length !== 4 || !window.crypto?.subtle;
  get("pack-load").disabled = busy || !window.crypto?.subtle;
  get("pack-forget").disabled = busy;
  get("inspect").disabled = busy || !selected || !window.crypto?.subtle;
  get("google-review").disabled = busy || !selected || !writable;
  for (const id of ["change-review", "inventory", "read-report", "export"]) {
    get(id).disabled = busy || !session;
  }
  get("folder").disabled = busy;
  get("path").disabled = busy;
  get("file-read").disabled = busy || !session || !get("path").value.trim();
  get("file-save").disabled = busy || !session || !stagedFile;
  get("confirm").disabled = busy || !writable || !review?.plan.apply;
  get("cancel").disabled = busy;
}

function clearReview() {
  review = null;
  get("review").hidden = true;
  get("preview-details").replaceChildren();
  get("preview-warnings").replaceChildren();
}

function updateIdentity() {
  const identity = get("identity");
  identity.replaceChildren();
  identity.hidden = !session;
  get("permission").hidden = !session;
  if (!session) return;
  const device = session.device;
  const fields = [
    ["Tablet", [device.manufacturer, device.model].filter(Boolean).join(" ")],
    ["Serial", device.serial], ["Fire OS", device.fireOS], ["Android SDK", device.sdk],
    ["Architectures", device.abis.join(", ")], ["Active user", device.user]
  ];
  for (const [label, value] of fields) {
    const term = document.createElement("dt");
    term.textContent = label;
    const data = document.createElement("dd");
    data.textContent = String(value ?? "") || "Unknown";
    identity.append(term, data);
  }
  get("permission").textContent = session.canWrite && navigator.locks
    ? "Connected for previews. Each tablet change requires your confirmation."
    : "Read-only connection. " + (session.writeLimit || "This browser cannot lock the tablet for changes.");
}

function forgetSession() {
  session = null;
  clearFile();
  clearReview();
  get("device-results").hidden = true;
  get("report").textContent = "";
  updateIdentity();
}

function lostSession(target) {
  if (target !== session) return;
  const applying = task?.mode === "apply";
  if (task?.mode !== "pack") task = null;
  forgetSession();
  refresh();
  message(applying ? "USB disconnected during a change. Some steps may have completed. Reconnect this tablet and review its state."
    : "The USB session ended. Reconnect the tablet to continue.", get("connect"), applying);
}

async function run(mode, trigger, startText, work) {
  if (task) return;
  const current = { mode, trigger, abort: ["connect", "pack"].includes(mode) ? new AbortController() : null };
  task = current;
  refresh();
  message(startText, trigger);
  function confirmLeavingDuringWrite(event) {
    if (task !== current) return;
    event.preventDefault();
    event.returnValue = true;
  }
  if (mode === "apply") window.addEventListener("beforeunload", confirmLeavingDuringWrite);
  try {
    await work(current);
  } catch (error) {
    if (task === current) {
      const reason = error?.message || String(error);
      message(mode === "apply" ? reason + " Review the tablet state before trying again." : reason, trigger, true);
    }
  } finally {
    if (mode === "apply") window.removeEventListener("beforeunload", confirmLeavingDuringWrite);
    if (task === current) {
      task = null;
      refresh();
    }
  }
}

get("connect").addEventListener("click", () => run("connect", get("connect"),
  "Choose your Fire tablet in Chrome, then unlock it and approve USB debugging on its screen.", async current => {
    const target = await connectDevice(current.abort.signal);
    if (task !== current || current.abort.signal.aborted) {
      await target.close();
      return;
    }
    session = target;
    target.disconnected.then(() => lostSession(target), () => lostSession(target));
    updateIdentity();
    message("Tablet connected.", get("disconnect"));
  }));

get("disconnect").addEventListener("click", () => {
  if (task?.mode === "connect") {
    task.abort.abort();
    task = null;
    refresh();
    message("Connection canceled. Dismiss Chrome’s chooser if it is still open.", get("connect"));
    return;
  }
  if (!session || task) return;
  const target = session;
  forgetSession();
  run("disconnect", get("connect"), "Closing the USB session…", async current => {
    await target.close();
    if (task === current) message("Disconnected. You can unplug the tablet.", get("connect"));
  });
});

function showTab(tab, focus) {
  clearReview();
  clearFile();
  for (const item of tabs) {
    const visible = item === tab;
    item.setAttribute("aria-selected", String(visible));
    item.tabIndex = visible ? 0 : -1;
    document.getElementById(item.getAttribute("aria-controls")).hidden = !visible;
  }
  if (focus) tab.focus();
  refresh();
}
for (const [index, tab] of tabs.entries()) {
  tab.addEventListener("click", () => { if (!task && tab.getAttribute("aria-selected") !== "true") showTab(tab, false); });
  tab.addEventListener("keydown", event => {
    if (task) return;
    const indices = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0, End: tabs.length - 1};
    if (!Object.hasOwn(indices, event.key)) return;
    event.preventDefault();
    showTab(tabs[indices[event.key]], true);
  });
}

function preview(id, create) {
  const trigger = get(id);
  if (!session || task) return;
  clearReview();
  const target = session;
  run("preview", trigger, "Reading the tablet and preparing your preview…", async current => {
    const plan = await create(target);
    if (task !== current || session !== target) return;
    review = {target, plan, trigger};
    get("review-heading").textContent = plan.title;
    get("review-device").textContent = [target.device.model, target.device.serial, "User " + target.device.user].join(" · ");
    listText(get("preview-details"), plan.details);
    listText(get("preview-warnings"), plan.warnings);
    get("preview-warnings").hidden = !plan.warnings.length;
    get("confirm").hidden = !plan.apply;
    get("cancel").textContent = plan.apply ? "Cancel" : "Close report";
    get("review").hidden = false;
    message(plan.apply ? "Preview ready. Check the target and every proposed change." : "Read complete.", trigger);
    get("review-heading").focus({ preventScroll: true });
    get("review").scrollIntoView({block: "start"});
  });
}

get("cancel").addEventListener("click", () => {
  if (!review || task) return;
  const {trigger, plan} = review;
  clearReview();
  refresh();
  message(plan.apply ? "Preview canceled." : "Report closed.", trigger);
  trigger.focus();
});

get("confirm").addEventListener("click", () => {
  if (!review || !review.plan.apply || session !== review.target || task) return;
  const {target, plan, trigger} = review;
  clearReview();
  trigger.focus();
  run("apply", trigger, "Applying the reviewed operation. Keep this tab open and the tablet connected.", async current => {
    let summary;
    await withDeviceLock(target, async () => {
      if (task !== current || session !== target) throw new Error("Tablet session changed. Create a new preview.");
      summary = await plan.apply(text => { if (task === current) message(String(text), trigger); });
    });
    if (task === current) message(summary || plan.title + " — finished. Check the result on your tablet.", trigger);
  });
});

function resetApkReview() {
  clearReview();
  get("apk-results").hidden = true;
  get("apk-list").replaceChildren();
}
get("google-files").addEventListener("change", () => {
  if (task?.mode === "pack") task.abort.abort();
  loadedPack = null;
  resetApkReview();
  get("message").textContent = "";
  refresh();
});

get("pack-save").addEventListener("click", () => {
  const trigger = get("pack-save");
  const files = Array.from(get("google-files").files);
  loadedPack = null;
  resetApkReview();
  run("pack", trigger, "Verifying and saving the four APKs in this Chrome profile…", async current => {
    const verified = await savePack(files, current.abort.signal);
    if (task !== current) return;
    loadedPack = verified;
    message("Saved four verified APKs in this Chrome profile. They are ready to use.", trigger);
  });
});

get("pack-load").addEventListener("click", () => {
  const trigger = get("pack-load");
  loadedPack = null;
  resetApkReview();
  run("pack", trigger, "Checking the saved APKs against their audited hashes…", async current => {
    const files = await loadPack(current.abort.signal);
    if (task !== current) return;
    get("google-files").value = "";
    loadedPack = files;
    message("Four verified APKs are ready. Connect your tablet and review installation.", trigger);
  });
});

get("pack-forget").addEventListener("click", () => {
  const trigger = get("pack-forget");
  loadedPack = null;
  resetApkReview();
  run("pack", trigger, "Removing the saved APKs from this Chrome profile…", async current => {
    await forgetPack(current.abort.signal);
    if (task === current) message("Saved APKs removed from this Chrome profile.", trigger);
  });
});

get("inspect").addEventListener("click", () => {
  clearReview();
  get("apk-results").hidden = true;
  const trigger = get("inspect");
  run("inspect", trigger, "Checking selected file hashes on this computer…", async current => {
    const files = await inspectApks(selectedApks());
    if (task !== current) return;
    listText(get("apk-list"), files.map(file => file.filename + " — " + file.name + "\n" + file.package +
      "\nSHA-256 " + file.sha256 + (file.partialScan ? "\nA legacy Android scan check timed out for this build." : "")));
    get("apk-results").hidden = false;
    message(files.length + (files.length === 1 ? " file matches" : " files match") + " the audited builds.", trigger);
  });
});
get("google-review").addEventListener("click", () => {
  const files = selectedApks();
  preview("google-review", target => previewGoogle(target, target.device, files));
});

const actions = get("action");
const groups = new Map();
for (const action of changeActions) {
  if (!groups.has(action.group)) {
    const group = document.createElement("optgroup");
    group.label = action.group;
    actions.append(group);
    groups.set(action.group, group);
  }
  groups.get(action.group).append(new Option(action.label, action.id));
}
function describeAction() {
  clearReview();
  get("action-help").textContent = changeActions.find(item => item.id === actions.value)?.description || "";
  refresh();
}
actions.addEventListener("change", describeAction);
get("change-review").addEventListener("click", () => {
  const id = actions.value;
  preview("change-review", target => previewChange(target, target.device, id));
});

function readTablet(id, read, show) {
  if (!session || task) return;
  clearReview();
  const target = session;
  get("device-results").hidden = true;
  run("read", get(id), "Reading tablet information…", async current => {
    const result = await read(target);
    if (task === current && session === target) show(result);
  });
}
function showReport(label, text, trigger) {
  get("result-heading").textContent = label;
  get("report").textContent = text;
  get("device-results").hidden = false;
  message(label + " ready.", trigger);
}
get("read-report").addEventListener("click", () =>
  readTablet("read-report", readReport, text => showReport("Device report", text, get("read-report"))));
get("inventory").addEventListener("click", () =>
  readTablet("inventory", readInventory, names => showReport("Installed apps (" + names.length + ")", names.join("\n"), get("inventory"))));
function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
get("export").addEventListener("click", () =>
  readTablet("export", createInventoryExport, text => {
    download(new Blob([text], {type: "application/json"}), "fire-tools-tablet-snapshot.json");
    message("Snapshot prepared for download.", get("export"));
  }));

function clearFile() {
  stagedFile = null;
  get("file-preview").hidden = true;
  get("file-meta").textContent = "";
}
for (const input of [get("folder"), get("path")]) {
  input.addEventListener("input", () => { clearFile(); refresh(); });
}
get("file-read").addEventListener("click", () => {
  clearFile();
  const folder = get("folder").value;
  const relative = get("path").value;
  readTablet("file-read", target => previewSharedFile(target, folder, relative), file => {
    stagedFile = file;
    get("file-meta").textContent = file.filename + " · " + file.size.toLocaleString() + " bytes\nSHA-256 " + file.sha256;
    get("file-preview").hidden = false;
    message("File ready. Review its name and size before saving.", get("file-read"));
  });
});
get("file-save").addEventListener("click", () => {
  if (task || !session || !stagedFile) return;
  download(stagedFile.blob, stagedFile.filename);
  message("File prepared for download.", get("file-read"));
  clearFile();
  refresh();
});
window.addEventListener("pagehide", () => {
  task?.abort?.abort();
  const target = session;
  task = null;
  forgetSession();
  refresh();
  if (target) void target.close().catch(() => {});
});
if (!supportsUsb) {
  get("connection-help").textContent = "USB access is unavailable here. Open this page directly over HTTPS in desktop Google Chrome to connect a tablet. You can still check local APK files in a browser with secure file hashing.";
}
describeAction();
get("app").hidden = false;
get("fallback").hidden = true;
