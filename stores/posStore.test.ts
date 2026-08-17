import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the network + persistence boundaries so the store can be tested headless.
vi.mock("@/lib/api/pos", () => ({
  checkout: vi.fn(),
  drawerMovement: vi.fn(),
}));
vi.mock("@/lib/api/sync", () => ({
  pushSync: vi.fn(),
}));
vi.mock("@/lib/offlineQueue", () => ({
  enqueueCheckout: vi.fn(),
  getQueue: vi.fn(),
  removeEntry: vi.fn(),
}));

import { usePosStore } from "@/stores/posStore";
import { checkout } from "@/lib/api/pos";
import { pushSync } from "@/lib/api/sync";
import { enqueueCheckout, getQueue, removeEntry } from "@/lib/offlineQueue";

const MOCK_ENTRY = {
  id: 1,
  local_seq: 1,
  client_txn_id: "txn-1",
  payload: { items: [{ product_name: "Aspirin", quantity: 1 }] },
  attempts: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  usePosStore.setState({
    lines: [],
    error: null,
    result: null,
    offlineCount: 0,
    syncing: false,
    hydrated: false,
  });
});

describe("posStore offline queue", () => {
  it("enqueues a sale when checkout fails (offline)", async () => {
    (checkout as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("network down"));
    (getQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    usePosStore.setState({ lines: [{ product_name: "Aspirin", quantity: 2, unit_price: "5.00" }] });
    await usePosStore.getState().checkout();

    expect(checkout).toHaveBeenCalled();
    expect(enqueueCheckout).toHaveBeenCalledWith({
      items: [{ product_name: "Aspirin", quantity: 2 }],
    });
    expect(usePosStore.getState().error).toContain("queued");
  });

  it("flushes the queue exactly-once via the merge-sync hub", async () => {
    (getQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([MOCK_ENTRY]);
    (pushSync as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      accepted: 1,
      deduped: 0,
      over_sells: 0,
      merge_seq_max: 1,
    });

    await usePosStore.getState().flushQueue();

    expect(pushSync).toHaveBeenCalledWith([
      {
        device_id: "server",
        local_seq: 1,
        client_txn_id: "txn-1",
        payload: { items: [{ product_name: "Aspirin", quantity: 1 }] },
      },
    ]);
    expect(removeEntry).toHaveBeenCalledWith(1);
  });

  it("does nothing when the queue is empty", async () => {
    (getQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    await usePosStore.getState().flushQueue();
    expect(pushSync).not.toHaveBeenCalled();
  });
});
