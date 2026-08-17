// Integer-cents money math must never use floating point.
import { describe, it, expect } from "vitest";
import {
  CENTS_PER_UNIT,
  addMoney,
  applyRate,
  cmpMoney,
  formatMoney,
  mulByQty,
  parseMoney,
  sumMoney,
  toDecimalString,
} from "@/lib/decimalCurrency";

describe("decimalCurrency", () => {
  it("parses decimal strings to integer cents", () => {
    expect(parseMoney("12.34")).toBe(1234n);
    expect(parseMoney("0")).toBe(0n);
    expect(parseMoney("-5.5")).toBe(-550n);
    expect(parseMoney(20)).toBe(2000n);
  });

  it("rejects non-decimal input", () => {
    expect(() => parseMoney("abc")).toThrow();
    expect(() => parseMoney("1.2.3")).toThrow();
  });

  it("formats cents back to fixed 2-decimal strings", () => {
    expect(formatMoney(1234n)).toBe("12.34");
    expect(formatMoney(0n)).toBe("0.00");
    expect(formatMoney(-550n)).toBe("-5.50");
    expect(formatMoney(9n)).toBe("0.09");
  });

  it("adds, multiplies by qty, and applies tax rate without floats", () => {
    expect(addMoney(100n, 250n)).toBe(350n);
    expect(mulByQty(199n, 3)).toBe(597n);
    // 8.25% tax on $10.00 -> 82.5 cents -> rounds to 83 cents (0.83)
    expect(applyRate(1000n, 825)).toBe(83n);
  });

  it("sums a list of cents", () => {
    expect(sumMoney([100n, 250n, 50n])).toBe(400n);
  });

  it("compares and serializes for the wire", () => {
    expect(cmpMoney(100n, 200n)).toBe(-1);
    expect(cmpMoney(200n, 100n)).toBe(1);
    expect(cmpMoney(100n, 100n)).toBe(0);
    expect(toDecimalString(1234n)).toBe("12.34");
    expect(CENTS_PER_UNIT).toBe(100n);
  });
});
