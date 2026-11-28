import assert from "node:assert/strict";
import { test } from "node:test";
import { savePack, loadPack } from "../assets/browser-apks.mjs";
import { forgetPack } from "../assets/browser-apk-library.mjs";

function database(t, stored, options = {}) {
  const stats = { commits: 0, closes: 0, opens: 0, added: 0 };
  const factory = { open() {
    stats.opens++;
    const request = {};
    const db = { close() { stats.closes++; }, transaction() {
      const tx = { objectStore() { return { get: () => issue("get"), delete: () => issue("delete"), add: value => issue("add", value) }; } };
      function issue(action, value) {
        const operation = {};
        queueMicrotask(() => {
          operation.result = stored;
          if (options.abort) {
            tx.error = new DOMException("No space", "QuotaExceededError");
            tx.onabort();
          } else {
            if (action === "delete") stored = undefined;
            if (action === "add") {
              assert.equal(stored, undefined, "a previously saved record must never be replaced");
              stats.added++;
              stored = options.unreadableAfterCommit ? {} : value;
            }
            stats.commits++;
            tx.oncomplete();
          }
        });
        return operation;
      }
      return tx;
    } };
    queueMicrotask(() => { request.result = db; request.onsuccess(); });
    return request;
  } };
  const original = Object.getOwnPropertyDescriptor(globalThis, "indexedDB");
  Object.defineProperty(globalThis, "indexedDB", { configurable:true, value:factory });
  t.after(() => original ? Object.defineProperty(globalThis, "indexedDB", original) : delete globalThis.indexedDB);
  return stats;
}

test("an incomplete selection or four wrong files never touch storage", async t => {
  const stats = database(t);
  await assert.rejects(savePack([]), /four/i);
  await assert.rejects(savePack(Array(4).fill(new File(["fake"], "Google.apk"))), /four|audited/i);
  class SpoofedSize extends File {
    constructor(size) { super(["substituted"], "Google.apk"); this.reportedSize = size; }
    get size() { return this.reportedSize; }
  }
  await assert.rejects(savePack([6552461, 4296499, 228440903, 59468089].map(size => new SpoofedSize(size))), /audited/i);
  assert.equal(stats.opens, 0);
});

test("loading distinguishes an absent set from corrupt or substituted local files", async t => {
  for (const [name, stored, error] of [
    ["missing", undefined, /no saved/i],
    ["invalid record", {}, /invalid|damaged/i],
    ["unknown four", Array(4).fill(new File(["bad"], "trusted.apk")), /four|audited/i],
  ]) {
    await t.test(name, async t => {
      const stats = database(t, stored);
      await assert.rejects(loadPack(), error);
      assert.equal(stats.closes, 1);
    });
  }
});

test("forget completes only after the deletion commits", async t => {
  await t.test("committed", async t => {
    const stats = database(t, {});
    await forgetPack();
    await assert.rejects(loadPack(), /no saved/i);
    assert.equal(stats.commits, 2);
  });
  await t.test("aborted", async t => {
    const stats = database(t, {}, {abort:true});
    await assert.rejects(forgetPack(), /storage|space/i);
    assert.equal(stats.commits, 0);
    assert.equal(stats.closes, 1);
  });
});

test("an already canceled operation does not open the database", async t => {
  const stats = database(t);
  const signal = AbortSignal.abort();
  await assert.rejects(loadPack(signal));
  await assert.rejects(forgetPack(signal));
  assert.equal(stats.opens, 0);
});

function fourFiles(t) {
  const hashes = new Map([
    [6552461, "3324ee2f67d23848ae3d9086f20ada10f2cb0dbb6d202067b918cc4fb4d167be"],
    [4296499, "32156365bcff60f2a0576abe1f15ef7e2b705aea9536bfcbd6fef784d131ccb5"],
    [228440903, "1db5544caff5d45b0e8bdf9d4beeaf26621457418b7d66807ae5583c47491f07"],
    [59468089, "03acdf87da98c09239737f56c568e0e8e82262b071081c14633593600664b8fa"],
  ]);
  // Simulate hashing for a small unit test. The real-file Chromium smoke covers
  // all four full-size APKs and exercises the native IndexedDB implementation.
  t.mock.method(crypto.subtle, "digest", async (_, bytes) => Uint8Array.from(Buffer.from(hashes.get(bytes.byteLength), "hex")).buffer);
  const FileClass = globalThis.File;
  const sizes = new Map([["com.google.android.gsf.login.apk", 6552461], ["com.google.android.gsf.apk", 4296499],
    ["com.google.android.gms.apk", 228440903], ["com.android.vending.apk", 59468089]]);
  class SimulatedFile extends FileClass {
    constructor(parts, name) {
      super(parts, name);
      if (sizes.has(name)) Object.defineProperty(this, "size", {value: sizes.get(name)});
    }
    async arrayBuffer() { return {byteLength: this.size}; }
  }
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "File");
  Object.defineProperty(globalThis, "File", {configurable: true, writable: true, value: SimulatedFile});
  t.after(() => Object.defineProperty(globalThis, "File", descriptor));
  return [...hashes.keys()].map(size => {
    const file = new File(["test"], "original.apk");
    Object.defineProperty(file, "size", {value: size});
    Object.defineProperty(file, "arrayBuffer", {value: async () => ({byteLength: size})});
    return file;
  });
}

test("only a fresh authenticated database readback marks the pack ready", async t => {
  const stats = database(t, undefined, {unreadableAfterCommit: true});
  await assert.rejects(savePack(fourFiles(t)), /damaged/i);
  assert.equal(stats.added, 1);
});

test("saving the same complete set twice reuses the first verified copy", async t => {
  const stats = database(t);
  const first = fourFiles(t);
  const saved = await savePack(first);
  assert.deepEqual(await savePack([...first].reverse()), saved);
  assert.equal(stats.added, 1);
  await forgetPack();
  await assert.rejects(loadPack(), /no saved/i);
});

test("a damaged existing set requires explicit removal before replacing it", async t => {
  const stats = database(t, {});
  await assert.rejects(savePack(fourFiles(t)), /forget/i);
  assert.equal(stats.added, 0);
});

test("a forget requested while save verifies leaves the committed set removed", async t => {
  if (!navigator.locks) { t.skip("Chrome uses Web Locks across tabs"); return; }
  const stats = database(t);
  const files = fourFiles(t);
  let notifyStarted, release;
  const started = new Promise(resolve => { notifyStarted = resolve; });
  const pause = new Promise(resolve => { release = resolve; });
  const file = files[0];
  const delayed = new File(["test"], "delayed.apk");
  Object.defineProperty(delayed, "size", {value: file.size});
  Object.defineProperty(delayed, "arrayBuffer", {value: async () => {
    notifyStarted();
    await pause;
    return file.arrayBuffer();
  }});
  files[0] = delayed;
  const saving = savePack(files);
  await started;
  const forgetting = forgetPack();
  release();
  await Promise.all([saving, forgetting]);
  assert.equal(stats.added, 1);
  await assert.rejects(loadPack(), /no saved/i);
});
