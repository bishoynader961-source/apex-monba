// Step 1.7 — Mobile API base URL discovery (blueprint §1.3.3).
//
// Owner-adapted strategy (as instructed, diverging from the blueprint's
// AsyncStorage + react-native-zeroconf sketch):
//   1. SecureStore key `ph_desktop_url` (pairing wrote it; survives restarts,
//      hardware-backed — never AsyncStorage).
//   2. Ping it: a stored URL is only trusted while the desktop actually
//      answers (IP changes after DHCP renewals make stale entries useless).
//   3. No mDNS client on mobile v1: discovery from the QR (the desktop
//      advertises _pharmacysuite._tcp so users can find the QR tab, not so
//      the phone can skip scanning — pairing is cryptographic, discovery is
//      not).
//   4. Otherwise throw MANUAL_ENTRY_REQUIRED — RootNavigator shows the
//      ConnectScreen (QR scan) when this sentinel is the reason there is no
//      base URL.
//
// Security: this module stores only a LAN origin (scheme://host:port). No
// tokens, no PHI, no credentials ever pass through here.

import * as SecureStore from "expo-secure-store";
import axios from "axios";

export const DESKTOP_URL_KEY = "ph_desktop_url";
/** Thrown (as error.message) when no cached desktop URL exists or it is dead. */
export const MANUAL_ENTRY_REQUIRED = "MANUAL_ENTRY_REQUIRED";

export async function getStoredDesktopUrl(): Promise<string | null> {
  return SecureStore.getItemAsync(DESKTOP_URL_KEY);
}

export async function storeDesktopUrl(url: string): Promise<void> {
  await SecureStore.setItemAsync(DESKTOP_URL_KEY, url);
}

export async function clearStoredDesktopUrl(): Promise<void> {
  await SecureStore.deleteItemAsync(DESKTOP_URL_KEY);
}

/** True when the desktop answers /api/v1/health at this origin. */
export async function pingDesktopUrl(url: string, timeoutMs = 4000): Promise<boolean> {
  try {
    const resp = await axios.get(`${url}/api/v1/health`, { timeout: timeoutMs });
    return resp.status === 200;
  } catch {
    return false;
  }
}

/**
 * Resolve the desktop origin per the strategy above. Callers that merely
 * want the value (ConnectScreen prefill, Settings) can catch the sentinel.
 */
export async function discoverDesktopUrl(): Promise<string> {
  const cached = await getStoredDesktopUrl();
  if (cached && (await pingDesktopUrl(cached))) {
    return cached;
  }
  throw new Error(MANUAL_ENTRY_REQUIRED);
}

/** Extract scheme://host:port from any desktop URL (for the pairing POST). */
export function desktopOrigin(url: string): string {
  try {
    const parsed = new URL(url);
    const port = parsed.port ? `:${parsed.port}` : "";
    return `${parsed.protocol}//${parsed.hostname}${port}`;
  } catch {
    return url.replace(/\/+$/, "");
  }
}
