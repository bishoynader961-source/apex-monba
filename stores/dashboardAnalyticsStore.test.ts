import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the dashboard API module
vi.mock("@/lib/api/dashboard", () => ({
  getDashboardAnalytics: vi.fn(),
}));

import { useDashboardAnalyticsStore } from "@/stores/dashboardAnalyticsStore";
import { getDashboardAnalytics } from "@/lib/api/dashboard";

const MOCK_DATA = {
  total_sales: 12345,
  total_customers: 250,
  top_items: [
    { product_name: "Aspirin", total_quantity: 100, total_revenue: 500 },
    { product_name: "Ibuprofen", total_quantity: 80, total_revenue: 400 },
    { product_name: "Acetaminophen", total_quantity: 60, total_revenue: 300 },
  ],
} as const;

beforeEach(() => {
  vi.clearAllMocks();
  // Reset store state before each test
  useDashboardAnalyticsStore.setState({ data: null, isLoading: false, error: null });
});

describe("dashboardAnalyticsStore", () => {
  it("fetches analytics and updates state on success", async () => {
    // Mock successful API response
    (getDashboardAnalytics as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_DATA);

    await useDashboardAnalyticsStore.getState().fetch();

    expect(getDashboardAnalytics).toHaveBeenCalled();
    const state = useDashboardAnalyticsStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.data).toEqual(MOCK_DATA);
  });

  it("sets error state when the API call fails", async () => {
    const errorMessage = "network error";
    (getDashboardAnalytics as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error(errorMessage));

    await useDashboardAnalyticsStore.getState().fetch();

    const state = useDashboardAnalyticsStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.data).toBeNull();
    expect(state.error).toContain(errorMessage);
  });
});
