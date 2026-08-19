// Minimal promise-based IndexedDB wrapper used by the offline queue and the
// per-tab persisted POS state. No external dependency.

export const DB_NAME = "pharmacypro";
export const DB_VERSION = 2;

export const STORE_KV = "kv";
export const STORE_QUEUE = "offline_queue";
export const STORE_META = "meta";
// Cached offline manager-approval policy (Concern 2 / A2). Keyed by username.
// Stores a PBKDF2-derived pin_hash + salt so the manager PIN can be verified
// locally when /api/v1/pos/approve is unreachable. Self-wipes after
// OFFLINE_MAX_ATTEMPTS failures (see lib/offlineCrypto.ts).
export const STORE_MANAGER_POLICIES = "manager_policies";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("indexedDB not available"));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_KV)) {
        db.createObjectStore(STORE_KV);
      }
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        db.createObjectStore(STORE_QUEUE, { keyPath: "id", autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META);
      }
      if (!db.objectStoreNames.contains(STORE_MANAGER_POLICIES)) {
        db.createObjectStore(STORE_MANAGER_POLICIES);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("indexedDB open failed"));
  });
  return dbPromise;
}

function tx(
  db: IDBDatabase,
  store: string,
  mode: IDBTransactionMode,
): IDBObjectStore {
  return db.transaction(store, mode).objectStore(store);
}

export async function idbGet<T>(store: string, key: IDBValidKey): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const r = tx(db, store, "readonly").get(key);
    r.onsuccess = () => resolve(r.result as T | undefined);
    r.onerror = () => reject(r.error);
  });
}

export async function idbSet<T>(store: string, key: IDBValidKey, value: T): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const r = tx(db, store, "readwrite").put(value, key);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
  });
}

export async function idbDelete(store: string, key: IDBValidKey): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const r = tx(db, store, "readwrite").delete(key);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
  });
}

export async function idbGetAll<T>(store: string): Promise<T[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const r = tx(db, store, "readonly").getAll();
    r.onsuccess = () => resolve(r.result as T[]);
    r.onerror = () => reject(r.error);
  });
}
