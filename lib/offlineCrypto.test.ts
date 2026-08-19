import { describe, it, expect } from "vitest";
import {
  provisionManagerPolicy,
  verifyPinOffline,
  constantTimeEqual,
  OFFLINE_MAX_ATTEMPTS,
  type ManagerPolicy,
} from "@/lib/offlineCrypto";

// A2 — Offline manager-PIN fallback (Concern 2). H19 = constant-time compare;
// T25 = brute-force resistance + self-wipe at OFFLINE_MAX_ATTEMPTS.
describe("offline manager PIN (A2)", () => {
  it("H19: correct PIN verifies with constant-time compare and resets counter", async () => {
    const policy = await provisionManagerPolicy("mgr", "1234");
    const ok = await verifyPinOffline("1234", policy);
    expect(ok.verified).toBe(true);
    expect(ok.wiped).toBe(false);
    expect(ok.policy.attempts).toBe(0);
  });

  it("H19: wrong PIN returns false without throwing and increments counter", async () => {
    const policy = await provisionManagerPolicy("mgr", "1234");
    const bad = await verifyPinOffline("9999", policy);
    expect(bad.verified).toBe(false);
    expect(bad.wiped).toBe(false);
    expect(bad.policy.attempts).toBe(1);
  });

  it("H19: constantTimeEqual is true for equal buffers, false for different, never throws on length mismatch", () => {
    expect(constantTimeEqual(new Uint8Array([1, 2, 3]), new Uint8Array([1, 2, 3]))).toBe(true);
    expect(constantTimeEqual(new Uint8Array([1, 2, 3]), new Uint8Array([1, 2, 4]))).toBe(false);
    expect(constantTimeEqual(new Uint8Array([1, 2, 3]), new Uint8Array([1, 2]))).toBe(false);
  });

  it("T25: three wrong attempts wipe the policy (self-wipe, no brute-force oracle)", async () => {
    let policy: ManagerPolicy = await provisionManagerPolicy("mgr", "1234");

    const r1 = await verifyPinOffline("0000", policy);
    expect(r1.verified).toBe(false);
    expect(r1.wiped).toBe(false);
    policy = r1.policy;

    const r2 = await verifyPinOffline("0000", policy);
    expect(r2.verified).toBe(false);
    expect(r2.wiped).toBe(false);
    policy = r2.policy;

    const r3 = await verifyPinOffline("0000", policy);
    expect(r3.verified).toBe(false);
    expect(r3.wiped).toBe(true);
    expect(r3.policy.attempts).toBe(OFFLINE_MAX_ATTEMPTS);
  });

  it("T25: a correct PIN after failures resets the attempt counter", async () => {
    let policy = await provisionManagerPolicy("mgr", "1234");
    policy = (await verifyPinOffline("0000", policy)).policy;
    expect(policy.attempts).toBe(1);
    const ok = await verifyPinOffline("1234", policy);
    expect(ok.verified).toBe(true);
    expect(ok.policy.attempts).toBe(0);
  });

  it("T25: provisioned policy carries a salt + 32-byte PBKDF2 hash (not a fast hash)", async () => {
    const policy = await provisionManagerPolicy("mgr", "1234");
    // base64 of 16-byte salt -> 24 chars; base64 of 32-byte hash -> 44 chars.
    expect(policy.salt).toHaveLength(24);
    expect(policy.pin_hash).toHaveLength(44);
  });
});
