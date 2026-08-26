// Tests for the pure license-gate logic (computeLicenseGateState).
// The project's vitest runs in the "node" environment, so we test the pure
// helper rather than the React hook (which requires jsdom + renderHook).
import { describe, it, expect } from "vitest";

import { computeLicenseGateState } from "@/hooks/useLicenseGate";

describe("computeLicenseGateState", () => {
  it("bypass when NEXT_PUBLIC_REQUIRE_LICENSE is false (Test build)", () => {
    const result = computeLicenseGateState(false, "/dashboard", null);
    expect(result.shouldGate).toBe(false);
    expect(result.loading).toBe(false);
    expect(result.licensed).toBe(true);
  });

  it("bypass on /pos when flag is false", () => {
    const result = computeLicenseGateState(false, "/pos", null);
    expect(result.shouldGate).toBe(false);
    expect(result.licensed).toBe(true);
  });

  it("enforce redirects without key when flag is true", () => {
    const result = computeLicenseGateState(true, "/dashboard", null);
    expect(result.shouldGate).toBe(true);
    expect(result.loading).toBe(false);
    expect(result.licensed).toBe(false);
  });

  it("enforce requires async validation when key is present", () => {
    const result = computeLicenseGateState(true, "/dashboard", "PHARM-A1B2-C3D4-E5F6");
    expect(result.shouldGate).toBe(true);
    expect(result.loading).toBe(true);
    expect(result.licensed).toBe(false);
  });

  it("non-gated routes (/, /login, /license, /portal) pass through", () => {
    for (const path of ["/", "/login", "/license", "/portal"]) {
      const result = computeLicenseGateState(true, path, null);
      expect(result.shouldGate).toBe(false);
      expect(result.licensed).toBe(true);
    }
  });

  it("sub-routes of /dashboard are also gated", () => {
    const result = computeLicenseGateState(true, "/dashboard/inventory", null);
    expect(result.shouldGate).toBe(true);
    expect(result.licensed).toBe(false);
  });

  it("sub-routes of /pos are also gated", () => {
    const result = computeLicenseGateState(true, "/pos/sales", null);
    expect(result.shouldGate).toBe(true);
    expect(result.licensed).toBe(false);
  });
});
