// Stable per-device id used to scope the Lamport local_seq in multi-terminal
// merge-sync (C.1). Persisted in localStorage so reloads keep the same device.
export const DEVICE_ID_KEY = "pp_device_id";

export function getDeviceId(): string {
  if (typeof window === "undefined") return "server";
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `dev_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}
