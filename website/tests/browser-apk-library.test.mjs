import assert from "node:assert/strict";
import { test } from "node:test";
import { savePack, loadPack } from "../assets/browser-apks.mjs";
import { forgetPack, isStoredFile, readStoredPack } from "../assets/browser-apk-library.mjs";

function database(t, stored, options = {}) {
  const stats = { commits: 0, closes: 0, opens: 0 };
  const factory = { open() {
    stats.opens++;
    const request = {};
    const db = { close() { stats.closes++; }, transaction() {
      const tx = { objectStore() { return { get: () => issue(false), delete: () => issue(true) }; } };
      function issue(remove) {
        const operation = {};
        queueMicrotask(() => {
          operation.result = stored;
          if (options.abort) {
            tx.error = new DOMException("No space", "QuotaExceededError");
            tx.onabort();
          } else {
            if (remove) stored = undefined;
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


test("only immutable database reads can reuse a File during install staging", async t => {
  const disk = new File(["bytes"], "source.apk");
  const stored = new File(["bytes"], "saved.apk");
  database(t, [stored]);
  assert.equal(isStoredFile(disk), false);
  assert.equal(isStoredFile(stored), false);
  const [dbFile] = await readStoredPack();
  assert.equal(isStoredFile(dbFile), true);
  assert.equal(isStoredFile(disk), false);
  await assert.rejects(loadPack(), /four|verification/i);
});
