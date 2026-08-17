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
