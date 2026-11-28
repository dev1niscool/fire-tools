import test from "node:test";
import assert from "node:assert/strict";
import { bindDevice, withDeviceLock } from "../assets/browser-session.mjs";

function connection() {
  const properties = {
    "ro.product.manufacturer": "Amazon", "ro.product.model": "KFTUWI",
    "ro.build.version.sdk": "30", "ro.build.mktg.fireos": "8.3.3.8",
    "ro.product.cpu.abilist": "arm64-v8a,armeabi-v7a", "ro.serialno": "ABC123example",
  };
  const state = { properties, user: "0", writes: [], extra: "" };
  let dropped;
  const raw = {
    serial: "ABC123example", disconnected: new Promise(resolve => { dropped = resolve; }),
    async shell(args) {
      if (args[0] === "getprop") return Object.entries(properties).map(([k,v]) => `[${k}]: [${v}]`).join("\n") + state.extra;
      if (args[0] === "am") return state.user;
      state.writes.push(args);
      return "ok";
    },
    async install() { state.writes.push("install"); },
    close() { dropped(); }, hashRemote() { return {size: 1, sha256: "a".repeat(64)}; },
  };
  return {state, raw};
}

const openLocks = { request: async (key, options, callback) => callback({name: key}) };
const change = ["settings", "--user", "0", "put", "global", "window_animation_scale", "0.5"];

test("reads a physical Fire identity and binds all writes to a live, exclusively locked tablet", async () => {
  const {raw, state} = connection();
  const session = await bindDevice(raw, openLocks);
  assert.equal(session.serial, raw.serial);
  assert.equal(session.device.user, 0);
  assert.equal(session.device.fireOS, "8.3.3.8");
  assert.match(session.device.identityKey, /^[0-9a-f]{64}$/);
  assert.deepEqual(session.device.abis, ["arm64-v8a","armeabi-v7a"]);
  await assert.rejects(session.shell(change), /review|lock/i);
  await assert.rejects(session.install(new Blob()), /review|lock/i);
  await withDeviceLock(session, async () => {
    await session.shell(change);
    state.user = "10";
    await assert.rejects(session.install(new Blob()), /changed|profile/i);
  });
  assert.deepEqual(state.writes, [change]);
});

test("cannot inherit a preview across USB disconnect, firmware, or hardware changes", async () => {
  for (const what of ["closed","firmware","hardware"]) {
    const {raw, state} = connection();
    const session = await bindDevice(raw, openLocks);
    if (what === "closed") await session.close();
    else if (what === "firmware") state.properties["ro.build.mktg.fireos"] = "8.3.3.9";
    else state.properties["ro.serialno"] = "XYZ987example";
    await assert.rejects(withDeviceLock(session, () => session.shell(change)), /changed|connect/i);
    assert.deepEqual(state.writes, []);
  }
});

test("declines writes for child profiles, low SDK, absent cross-tab lock and concurrent work", async () => {
  for (const reason of ["child", "sdk", "locks", "busy"]) {
    const {raw,state} = connection();
    if (reason === "child") state.user = "10";
    if (reason === "sdk") state.properties["ro.build.version.sdk"] = "22";
    const locks = reason === "locks" ? null : reason === "busy"
      ? {request: (_key, _options, cb) => cb(null)} : openLocks;
    const session = await bindDevice(raw, locks);
    await assert.rejects(withDeviceLock(session, () => session.install(new Blob())));
    assert.deepEqual(state.writes, []);
  }
});

test("refuses ambiguous identities before offering a usable session", async () => {
  for (const reason of ["duplicate","other vendor","user"]) {
    const {raw,state} = connection();
    if (reason === "duplicate") state.extra = "\n[ro.product.model]: [other]";
    if (reason === "other vendor") state.properties["ro.product.manufacturer"] = "Other";
    if (reason === "user") state.user = "unknown";
    await assert.rejects(bindDevice(raw, openLocks));
  }
});

test("a tablet lock does not grant unrelated package or settings writes", async () => {
  const {raw,state} = connection();
  const session = await bindDevice(raw, openLocks);
  await withDeviceLock(session, async () => {
    for (const args of [
      ["pm", "disable-user", "--user", "0", "com.android.settings"],
      ["pm", "enable", "--user", "0", "com.android.providers.calendar", "extra"],
      ["settings", "--user", "0", "put", "global", "unrelated_key", "1"],
      ["settings", "--user", "0", "put", "global", "window_animation_scale", "oops"],
    ]) await assert.rejects(session.shell(args), /outside/);
    await session.shell(["settings", "--user", "0", "put", "global", "private_dns_specifier", ""]);
    await session.shell(["pm", "enable", "--user", "0", "com.android.providers.contacts"]);
  });
  assert.equal(state.writes.length, 2);
});
