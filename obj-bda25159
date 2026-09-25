
// In practice this would be called after a successful login to seed the offline key.
// It stores a passphrase derived from the auth token in sessionStorage for the session
// and persists a seed in localStorage for offline‑only starts.

export async function initializeOfflineKey(token: string): Promise<void> {
  const pass = token; // Simplified: use the token directly as passphrase (already high‑entropy).
  sessionStorage.setItem("offline_passphrase", pass);
  if (!localStorage.getItem("offline_passphrase_seed")) {
    localStorage.setItem("offline_passphrase_seed", pass);
  }
}

export async function getOfflinePassphrase(): Promise<string> {
  const session = typeof window !== "undefined" ? sessionStorage.getItem("offline_passphrase") : null;
  if (session) return session;
  // Fallback to persisted seed for completely offline starts.
  const seed = typeof window !== "undefined" ? localStorage.getItem("offline_passphrase_seed") : null;
  if (seed) {
    // Populate session storage for future calls.
    if (typeof window !== "undefined") sessionStorage.setItem("offline_passphrase", seed);
    return seed;
  }
  // No seed – generate a random one for the current session only.
  const random = crypto.randomUUID();
  if (typeof window !== "undefined") sessionStorage.setItem("offline_passphrase", random);
  return random;
}
