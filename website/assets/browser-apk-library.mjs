const storeName = "packs";
const packKey = "hd10-android11-arm64";

export function withPackLock(mode, work, signal) {
  signal?.throwIfAborted();
  const locks = globalThis.navigator?.locks;
  // add() also refuses an existing key in browsers without Web Locks.
  return locks ? locks.request("fire-tools-google-apk-pack", {mode, ...(signal ? {signal} : {})}, work) : work();
}

function storageError(error) {
  if (error?.name === "QuotaExceededError") {
    return Error("There is not enough browser storage. Free up space or use the selected APKs for this session.");
  }
  return Error("Chrome could not access the saved APKs. You can still choose local files for this session.");
}

function openLibrary() {
  return new Promise((resolve, reject) => {
    let request, blocked = false;
    try { request = globalThis.indexedDB.open("fire-tools-apk-library", 1); }
    catch (error) { reject(storageError(error)); return; }
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(storeName)) request.result.createObjectStore(storeName);
    };
    request.onblocked = () => {
      blocked = true;
      reject(Error("Close other Fire Tools tabs using saved APKs and try again."));
    };
    request.onerror = () => reject(storageError(request.error));
    request.onsuccess = () => {
      const db = request.result;
      if (blocked) { db.close(); return; }
      db.onversionchange = () => db.close();
      resolve(db);
    };
  });
}

async function access(mode, issue, signal) {
  signal?.throwIfAborted();
  const db = await openLibrary();
  try {
    signal?.throwIfAborted();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, mode);
      const cancel = () => { try { tx.abort(); } catch { /* The transaction already ended. */ } };
      signal?.addEventListener("abort", cancel, {once: true});
      let request;
      tx.onabort = () => {
        signal?.removeEventListener("abort", cancel);
        reject(signal?.aborted ? signal.reason : storageError(tx.error));
      };
      tx.oncomplete = () => {
        signal?.removeEventListener("abort", cancel);
        resolve(request.result);
      };
      try { request = issue(tx.objectStore(storeName)); }
      catch (error) { cancel(); reject(storageError(error)); }
    });
  } finally {
    db.close();
  }
}

export async function addStoredPack(files, signal) {
  await access("readwrite", store => store.add(files, packKey), signal);
}

export function readStoredPack(signal) {
  return access("readonly", store => store.get(packKey), signal);
}

export async function forgetPack(signal) {
  await withPackLock("exclusive", () => access("readwrite", store => store.delete(packKey), signal), signal);
}
