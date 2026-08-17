// Worker wrapper around lib/offlineCrypto to keep PBKDF2 (200k iterations) off
// the main thread. Posts { id, op: "encrypt"|"decrypt", passphrase, payload };
// responds { id, ok, result } or { id, ok:false, error }.
import { encryptString, decryptString } from "@/lib/offlineCrypto";

type Req = {
  id: number;
  op: "encrypt" | "decrypt";
  passphrase: string;
  payload: string;
};

self.onmessage = async (e: MessageEvent<Req>) => {
  const { id, op, passphrase, payload } = e.data;
  try {
    const result =
      op === "encrypt"
        ? await encryptString(passphrase, payload)
        : await decryptString(passphrase, payload);
    (self as unknown as Worker).postMessage({ id, ok: true, result });
  } catch (err) {
    (self as unknown as Worker).postMessage({
      id,
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
};
