const storeName = "packs";
const packKey = "hd10-android11-arm64";
const databaseFiles = new WeakSet();

// Only File objects returned by a committed IndexedDB read enter this set.
// They retain an immutable browser-storage snapshot even if the record is replaced.
export function isStoredFile(file) {
  return databaseFiles.has(file);
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

export async function writeStoredPack(verified, signal) {
  await access("readwrite", store => store.put(verified, packKey), signal);
}

export async function readStoredPack(signal) {
  const files = await access("readonly", store => store.get(packKey), signal);
  if (Array.isArray(files)) {
    for (const file of files) {
      if (file instanceof File) databaseFiles.add(file);
    }
  }
  return files;
}

export async function forgetPack(signal) {
  await access("readwrite", store => store.delete(packKey), signal);
}
