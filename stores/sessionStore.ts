import { create } from "zustand";

const ACTIVITY_EVENTS = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;
const COUNTDOWN_TICK_MS = 1000;
// Warn 30 seconds before auto-logout (Spec 05 §1.3).
const WARNING_BEFORE_MS = 30_000;

// null means "never expire"
type TimeoutValue = number | null;

interface SessionConfig {
  idleMinutes: TimeoutValue;
  absoluteMinutes: TimeoutValue;
}

interface SessionState {
  lastActivityAt: number;
  idleMinutes: TimeoutValue;
  absoluteMinutes: TimeoutValue;
  absoluteStartedAt: number;
  isActive: boolean;
  showWarning: boolean;
  countdownSeconds: number;

  init: (config?: Partial<SessionConfig>) => void;
  loadConfig: () => Promise<void>;
  resetIdle: () => void;
  dismissWarning: () => void;
  tick: () => void;
  expire: () => void;
}

function toInternal(value: string | undefined): TimeoutValue {
  if (value === "never" || value === undefined) return null;
  const n = parseInt(value, 10);
  return isNaN(n) || n <= 0 ? null : n;
}

function toExternal(value: TimeoutValue): string {
  return value === null ? "never" : String(value);
}

export const useSessionStore = create<SessionState>((set, get) => ({
  lastActivityAt: Date.now(),
  idleMinutes: 15,
  absoluteMinutes: 480,
  absoluteStartedAt: Date.now(),
  isActive: true,
  showWarning: false,
  countdownSeconds: 60,

  init: (config) => {
    const now = Date.now();
    set({
      lastActivityAt: now,
      absoluteStartedAt: now,
      isActive: true,
      showWarning: false,
      countdownSeconds: 60,
      idleMinutes: config?.idleMinutes ?? 15,
      absoluteMinutes: config?.absoluteMinutes ?? 480,
    });
  },

  loadConfig: async () => {
    try {
      const res = await fetch("/api/v1/settings/session_idle_minutes");
      if (res.ok) {
        const data = await res.json();
        useSessionStore.setState({ idleMinutes: toInternal(data.value) });
      }
      const resAbs = await fetch("/api/v1/settings/session_absolute_minutes");
      if (resAbs.ok) {
        const data = await resAbs.json();
        useSessionStore.setState({ absoluteMinutes: toInternal(data.value) });
      }
    } catch {
      // Use defaults if API unavailable
    }
  },

  resetIdle: () => {
    const state = get();
    if (state.showWarning) return;
    set({ lastActivityAt: Date.now() });
  },

  dismissWarning: () => {
    set({ showWarning: false, countdownSeconds: 60, lastActivityAt: Date.now() });
  },

  tick: () => {
    const state = get();
    if (!state.isActive) return;

    const now = Date.now();
    const idleMs = now - state.lastActivityAt;
    const absoluteMs = now - state.absoluteStartedAt;

    // Check absolute timeout (if configured)
    if (state.absoluteMinutes !== null) {
      const absoluteLimitMs = state.absoluteMinutes * 60_000;
      if (absoluteMs >= absoluteLimitMs) {
        set({ isActive: false, showWarning: false });
        return;
      }
    }

    // Check idle timeout (if configured)
    if (state.idleMinutes !== null) {
      const idleLimitMs = state.idleMinutes * 60_000;
      if (idleMs >= idleLimitMs) {
        set({ isActive: false, showWarning: false });
        return;
      }

      const remainingMs = idleLimitMs - idleMs;
      if (remainingMs <= WARNING_BEFORE_MS && !state.showWarning) {
        set({ showWarning: true, countdownSeconds: Math.ceil(remainingMs / COUNTDOWN_TICK_MS) });
      }

      if (state.showWarning) {
        const newCountdown = Math.max(0, Math.ceil(remainingMs / COUNTDOWN_TICK_MS));
        set({ countdownSeconds: newCountdown });
        if (newCountdown <= 0) {
          set({ isActive: false, showWarning: false });
        }
      }
    } else {
      // Idle timeout is "never" - hide warning if showing
      if (state.showWarning) {
        set({ showWarning: false, countdownSeconds: 60 });
      }
    }
  },

  expire: () => set({ isActive: false, showWarning: false }),
}));

let listenerCount = 0;
let intervalId: ReturnType<typeof setInterval> | null = null;

export function startSessionTracking() {
  if (listenerCount > 0) return;

  const store = useSessionStore.getState();
  store.init();
  store.loadConfig();

  const onActivity = () => {
    useSessionStore.getState().resetIdle();
  };

  ACTIVITY_EVENTS.forEach((event) => {
    document.addEventListener(event, onActivity, { passive: true });
  });

  listenerCount = ACTIVITY_EVENTS.length;

  intervalId = setInterval(() => {
    useSessionStore.getState().tick();
  }, COUNTDOWN_TICK_MS);
}

export function stopSessionTracking() {
  if (listenerCount === 0) return;

  const onActivity = () => {
    useSessionStore.getState().resetIdle();
  };

  ACTIVITY_EVENTS.forEach((event) => {
    document.removeEventListener(event, onActivity);
  });

  listenerCount = 0;

  if (intervalId !== null) {
    clearInterval(intervalId);
    intervalId = null;
  }
}