// Offline PII encryption-at-rest using Web Crypto (SubtleCrypto).
// PBKDF2-HMAC-SHA256 with 200k iterations (Concern 8: edge PII local-encryption).
// Runs on the main thread by default; lib/offlineCryptoWorker.ts offloads it.

const PBKDF2_ITERATIONS = 200_000;
const SALT_BYTES = 16;
const IV_BYTES = 12;

function getSubtle(): SubtleCrypto {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (!c || !c.subtle) throw new Error("Web Crypto unavailable");
  return c.subtle;
}

function toB64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function fromB64(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function deriveKey(
  passphrase: string,
  salt: Uint8Array,
): Promise<CryptoKey> {
  const subtle = getSubtle();
  const baseKey = await subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase) as BufferSource,
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

/** Encrypt a UTF-8 string; returns base64(salt|iv|ciphertext). */
export async function encryptString(passphrase: string, plaintext: string): Promise<string> {
  const subtle = getSubtle();
  const salt = crypto.getRandomValues(new Uint8Array(SALT_BYTES));
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const key = await deriveKey(passphrase, salt);
  const cipher = await subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    key,
    new TextEncoder().encode(plaintext) as BufferSource,
  );
  const packed = new Uint8Array(salt.length + iv.length + cipher.byteLength);
  packed.set(salt, 0);
  packed.set(iv, salt.length);
  packed.set(new Uint8Array(cipher), salt.length + iv.length);
  return toB64(packed.buffer);
}

/** Decrypt a value produced by encryptString. */
export async function decryptString(passphrase: string, packedB64: string): Promise<string> {
  const subtle = getSubtle();
  const packed = fromB64(packedB64);
  const salt = packed.slice(0, SALT_BYTES);
  const iv = packed.slice(SALT_BYTES, SALT_BYTES + IV_BYTES);
  const cipher = packed.slice(SALT_BYTES + IV_BYTES);
  const key = await deriveKey(passphrase, salt);
  const plain = await subtle.decrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    key,
    cipher as BufferSource,
  );
  return new TextDecoder().decode(plain);
}

// ── Offline manager-PIN verification (Concern 2 / Phase A, A2) ──────────────
// PBKDF2-HMAC-SHA256 at 200k iterations via WebCrypto (browser-native, no dep).
// The client self-provisions its offline policy on a successful *online* approval
// (see ManagerApprovalDialog): it derives pin_hash from the PIN it just verified.
// This is fully self-contained and never depends on the server's device-bound
// (peppered) pin_hash, which is unrecoverable off-machine by design (C.4).

export const OFFLINE_MAX_ATTEMPTS = 3;
const PBKDF2_PIN_ITERS = 200_000;
const PIN_SALT_BYTES = 16;
const PIN_DKLEN = 32;

export interface ManagerPolicy {
  username: string;
  salt: string; // base64
  pin_hash: string; // base64 (PBKDF2-HMAC-SHA256, 32 bytes)
  attempts: number;
  locked_until?: number | null;
}

export interface PinVerifyResult {
  verified: boolean;
  wiped: boolean;
  policy: ManagerPolicy;
  reason?: "invalid" | "locked";
}

/** Derive the 32-byte PBKDF2-HMAC-SHA256 digest of a PIN for offline verify. */
export async function derivePinOffline(pin: string, salt: Uint8Array): Promise<Uint8Array> {
  const subtle = getSubtle();
  const baseKey = await subtle.importKey(
    "raw",
    new TextEncoder().encode(pin) as BufferSource,
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await subtle.deriveBits(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: PBKDF2_PIN_ITERS, hash: "SHA-256" },
    baseKey,
    PIN_DKLEN * 8,
  );
  return new Uint8Array(bits);
}

/** Constant-time buffer comparison — never early-returns on mismatch. */
export function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  const len = Math.min(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** Build a cacheable offline policy from a freshly-verified online PIN. */
export async function provisionManagerPolicy(username: string, pin: string): Promise<ManagerPolicy> {
  const salt = crypto.getRandomValues(new Uint8Array(PIN_SALT_BYTES));
  const pin_hash = await derivePinOffline(pin, salt);
  return {
    username,
    salt: toB64(salt.buffer),
    pin_hash: toB64(pin_hash.buffer as ArrayBuffer),
    attempts: 0,
    locked_until: null,
  };
}

/**
 * Verify a PIN against a cached ManagerPolicy (pure — no IndexedDB access).
 * On a wrong PIN the attempt counter is incremented; at OFFLINE_MAX_ATTEMPTS the
 * policy is flagged `wiped` so the caller can delete the cached row (self-wipe,
 * preventing a brute-force oracle). Correct PIN resets the counter.
 */
export async function verifyPinOffline(pin: string, policy: ManagerPolicy): Promise<PinVerifyResult> {
  const salt = fromB64(policy.salt);
  const expected = fromB64(policy.pin_hash);
  const actual = await derivePinOffline(pin, salt);
  const match = constantTimeEqual(actual, expected);

  if (match) {
    return { verified: true, wiped: false, policy: { ...policy, attempts: 0, locked_until: null } };
  }

  const attempts = (policy.attempts || 0) + 1;
  if (attempts >= OFFLINE_MAX_ATTEMPTS) {
    return { verified: false, wiped: true, policy: { ...policy, attempts } };
  }
  return { verified: false, wiped: false, policy: { ...policy, attempts } };
}
