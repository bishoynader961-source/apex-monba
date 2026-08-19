import { describe, it, expect, vi, beforeEach } from "vitest";

// In-memory IndexedDB stand-in so recovery/GC logic can be exercised headless.
const mem = new Map<string, unknown>();
vi.mock("@/lib/db", () => ({
  STORE_KV: "kv",
  STORE_QUEUE: "queue",
  idbGet: vi.fn(async (_s: string, key: IDBValidKey) => mem.get(String(key))),
  idbSet: vi.fn(async (_s: string, key: IDBValidKey, value: unknown) => {
    mem.set(String(key), value);
  }),
  idbDelete: vi.fn(async (_s: string, key: IDBValidKey) => {
    mem.delete(String(key));
  }),
  idbGetAll: vi.fn(async () => []),
}));

import {
  deleteCart,
  findRecoverable,
  persistState,
  RECOVERY_WINDOW_MS,
  registerCart,
  sweepStaleTabs,
} from "@/lib/storagePersist";

const LINE = { product_name: "Aspirin", quantity: 1, unit_price: "5.00" } as const;

let now: number;
beforeEach(() => {
  mem.clear();
  vi.clearAllMocks();
  now = 1_000_000;
  vi.spyOn(Date, "now").mockImplementation(() => now);
});

describe("cart recovery (A3 / H20)", () => {
  it("surfaces a recent non-empty cart from another tab for recovery", async () => {
    await persistState("pos:tabB:lines", [LINE]);
    await registerCart("tabB", 1);

    const rec = await findRecoverable(now, "tabA");
    expect(rec).toHaveLength(1);
    expect(rec[0].tabId).toBe("tabB");
    expect(rec[0].lines).toHaveLength(1);
  });

  it("never offers the active tab's own cart", async () => {
    await persistState("pos:tabA:lines", [LINE]);
    await registerCart("tabA", 1);
    const rec = await findRecoverable(now, "tabA");
    expect(rec).toHaveLength(0);
  });
});

describe("stale cart GC (A3 / H21)", () => {
  it("sweeps carts older than the recovery window", async () => {
    now = 0;
    await persistState("pos:stale:lines", [LINE]);
    await registerCart("stale", 1);

    now = RECOVERY_WINDOW_MS + 5000;
    const removed = await sweepStaleTabs(now);
    expect(removed).toContain("stale");
    expect(await findRecoverable(now, "other")).toHaveLength(0);
  });

  it("keeps carts inside the window", async () => {
    now = 0;
    await persistState("pos:fresh:lines", [LINE]);
    await registerCart("fresh", 1);
    now = RECOVERY_WINDOW_MS - 1000;
    const removed = await sweepStaleTabs(now);
    expect(removed).toHaveLength(0);
  });
});

describe("discard recoverable (A3 / H22)", () => {
  it("removes the cart and its registry entry", async () => {
    await persistState("pos:tabC:lines", [LINE]);
    await registerCart("tabC", 1);
    await deleteCart("tabC");
    expect(await findRecoverable(now, "other")).toHaveLength(0);
    expect(mem.has("pos:tabC:lines")).toBe(false);
  });
});
