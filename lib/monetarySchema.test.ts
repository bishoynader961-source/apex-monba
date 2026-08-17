import { describe, it, expect } from "vitest";
import { centsToMoneyString, isMoneyString, moneyStringSchema, parseMoneyString } from "@/lib/monetarySchema";

describe("monetarySchema", () => {
  it("accepts valid money strings", () => {
    expect(moneyStringSchema.parse("12.34")).toBe("12.34");
    expect(moneyStringSchema.parse("0")).toBe("0");
    expect(moneyStringSchema.parse("-5.50")).toBe("-5.50");
  });

  it("rejects malformed money strings", () => {
    expect(moneyStringSchema.safeParse("12.345").success).toBe(false);
    expect(moneyStringSchema.safeParse("1.2.3").success).toBe(false);
    expect(moneyStringSchema.safeParse("abc").success).toBe(false);
  });

  it("round-trips through parse/format", () => {
    expect(isMoneyString("9.99")).toBe(true);
    expect(isMoneyString(42)).toBe(false);
    expect(parseMoneyString("7.50")).toBe(750n);
    expect(centsToMoneyString(750n)).toBe("7.50");
  });
});
