import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { inspectApks, previewGoogle } from "../assets/browser-apks.mjs";

const state = {serial: "tablet-1", manufacturer: "Amazon", model: "KFTUWI", sdk: 30, user: 0, abis: ["arm64-v8a"], fireOS: "8.3.3.8"};
const calendar = {name: "com.google.android.syncadapters.calendar", size: 2450495, code: 2017005136, hash: "87fb81b621d060c9779f0942ea379f7cad4f7b551b4d9f1d651a8980f3a6f749"};
const core = {
  "com.google.android.gsf": [29, 4296499, "32156365bcff60f2a0576abe1f15ef7e2b705aea9536bfcbd6fef784d131ccb5"],
  "com.google.android.gms": [252037022, 228440903, "1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07"],
  "com.android.vending": [83631210, 59468089, "03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa"],
};
const provider = "com.android.providers.calendar";

function calendarFixture(t) {
  const file = new File([new Uint8Array(calendar.size)], "user-chosen-name.apk");
  const hashed = t.mock.method(crypto.subtle, "digest", async () => Uint8Array.from(Buffer.from(calendar.hash, "hex")).buffer);
  return {file, hashed};
}
class Tablet {
  constructor() {
    this.serial = state.serial;
    this.packages = new Map([...Object.entries(core), [provider, [1]]]);
    this.disabled = new Set([provider]);
    this.writes = [];
    this.system = new Set([provider]);
    this.paths = {};
  }
  async shell(args) {
    assert.equal(args.includes("--user") && args[args.indexOf("--user") + 1] === "0", true, args.join(" "));
    if (args[1] === "list") {
      let ids = [...this.packages.keys()];
      if (args.includes("-d")) ids = ids.filter(id => this.disabled.has(id));
      if (args.includes("-s")) ids = ids.filter(id => this.system.has(id));
      return ids.map(id => "package:" + id + (args.includes("--show-versioncode") ? " versionCode:" + this.packages.get(id)[0] : "")).join("\n");
    }
    const id = args.at(-1);
    if (args[1] === "path") return this.paths[id] ?? "package:/data/app/" + id + "/base.apk";
    if (args[1] === "enable") {
      this.writes.push(id);
      this.disabled.delete(id);
      return "Package " + id + " new state: enabled";
    }
    throw Error(args.join(" "));
  }
  async hashRemote(path, limit) {
    const record = this.packages.get(path.split("/").at(-2));
    assert.equal(limit, record[1]);
    return {size: record[1], sha256: record[2]};
  }
  async install(bytes) {
    assert.ok(bytes instanceof Uint8Array);
    assert.equal(bytes.byteLength, calendar.size);
    this.writes.push(calendar.name);
    this.packages.set(calendar.name, [calendar.code, calendar.size, calendar.hash]);
  }
}
test("unknown bytes, empty selections and duplicate components cannot become a plan", async t => {
  await assert.rejects(inspectApks([]), /choose|select/i);
  await assert.rejects(inspectApks([new File(["test"], "Google.apk")]), /audit|recogniz|match/i);
  const {file} = calendarFixture(t);
  await assert.rejects(inspectApks([file, file]), /twice|duplicate|more than once/i);
});
test("every pinned file digest is an existing desktop scan record", () => {
  const js = readFileSync(new URL("../assets/browser-apks.mjs", import.meta.url), "utf8");
  const py = readFileSync(new URL("../../open_fire_toolkit/apk_checks.py", import.meta.url), "utf8");
  const fingerprints = new Set(js.match(/[0-9a-f]{64}/g));
  assert.equal(fingerprints.size, 6);
  for (const digest of fingerprints) assert.ok(py.includes("'" + digest + "':"), digest);
});
test("same-size files without a known digest fail inspection", async () => {
  await assert.rejects(inspectApks([new File([new Uint8Array(calendar.size)], "calendar.apk")]), /audit|recogniz|match/i);
});
test("sync-only checks its dependencies and enables only its installed system provider after readback", async t => {
  const {file} = calendarFixture(t);
  const tablet = new Tablet();
  const info = await inspectApks([file]);
  assert.equal(info[0].package, calendar.name);
  assert.equal(info[0].filename, file.name);
  tablet.device = state; // The bound production session exposes its verified device, not its USB serial.
  delete tablet.serial;
  const plan = await previewGoogle(tablet, state, [file]);
  assert.deepEqual(tablet.writes, []);
  assert.match(plan.details.join("\n"), /Enable com.android.providers.calendar/);
  const log = [];
  await plan.apply(msg => log.push(msg));
  assert.deepEqual(tablet.writes, [calendar.name, provider]);
  assert.match(log.join("\n"), /verified/i);
  const retry = await previewGoogle(tablet, state, [file]);
  await retry.apply(() => {});
  assert.deepEqual(tablet.writes, [calendar.name, provider]);
});
test("owner, compatibility, dependency identity, provider and downgrade checks run before writes", async t => {
  const {file} = calendarFixture(t);
  const tablet = new Tablet();
  for (const bad of [{...state, user: 10}, {...state, sdk: 25}, {...state, manufacturer: "Other"}]) {
    await assert.rejects(previewGoogle(tablet, bad, [file]));
  }
  tablet.system.clear();
  await assert.rejects(previewGoogle(tablet, state, [file]), /provider/i);
  tablet.system.add(provider);
  tablet.packages.set(calendar.name, [calendar.code + 1]);
  await assert.rejects(previewGoogle(tablet, state, [file]), /newer|downgrade/i);
  tablet.packages.delete(calendar.name);
  tablet.paths["com.google.android.gms"] = "package:/data/app/../etc/base.apk";
  await assert.rejects(previewGoogle(tablet, state, [file]), /path|APK/i);
  assert.deepEqual(tablet.writes, []);
});
test("stale device state and changed local bytes invalidate a confirmed preview", async t => {
  const {file, hashed} = calendarFixture(t);
  const tablet = new Tablet();
  const plan = await previewGoogle(tablet, state, [file]);
  tablet.disabled.clear();
  await assert.rejects(plan.apply(() => {}), /changed|review/i);
  tablet.disabled.add(provider);
  hashed.mock.mockImplementation(async () => new Uint8Array(32).buffer);
  await assert.rejects(plan.apply(() => {}), /audit|changed|match/i);
  assert.deepEqual(tablet.writes, []);
});
test("failed post-install readback stops before changing a provider and reports a possible partial install", async t => {
  const {file} = calendarFixture(t);
  const tablet = new Tablet();
  const plan = await previewGoogle(tablet, state, [file]);
  const read = tablet.hashRemote.bind(tablet);
  tablet.hashRemote = async (path, limit) => path.includes(calendar.name) ? {sha256: "wrong", size: limit} : read(path, limit);
  await assert.rejects(plan.apply(() => {}), /com.google.android.syncadapters.calendar.*(installed|changed)|installed.*com.google.android.syncadapters.calendar/i);
  assert.deepEqual(tablet.writes, [calendar.name]);
  assert.ok(tablet.disabled.has(provider));
});
test("core installs require all three compatible components and use dependency order", async t => {
  // Exercise package planning without redistributing the independently audited binaries.
  const bySize = new Map(Object.values(core).map(([, size, digest]) => [size, digest]));
  t.mock.method(crypto.subtle, "digest", async (_algorithm, bytes) =>
    Uint8Array.from(Buffer.from(bySize.get(bytes.byteLength), "hex")).buffer);
  const files = [...Object.entries(core)].reverse().map(([id, [, size]]) => ({
    name: id + ".apk", size, arrayBuffer: async () => new ArrayBuffer(size),
  }));
  const tablet = new Tablet();
  for (const id of Object.keys(core)) tablet.packages.delete(id);
  await assert.rejects(previewGoogle(tablet, state, files.slice(1)), /together/i);
  await assert.rejects(previewGoogle(tablet, {...state, abis: ["armeabi-v7a"]}, files), /architecture/i);
  const plan = await previewGoogle(tablet, state, files);
  for (const [index, id] of Object.keys(core).entries()) assert.ok(plan.details[index].includes("(" + id + ")"));
  assert.deepEqual(tablet.writes, []);
});
