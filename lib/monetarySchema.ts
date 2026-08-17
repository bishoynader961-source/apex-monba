// Zod schema + helpers for backend Decimal money strings ("12.34").
// Backend serializes Decimal as a JSON string; this guards parsing on the client.
import { z } from "zod";

import { parseMoney, formatMoney, type Cents } from "@/lib/decimalCurrency";

export const moneyStringSchema = z
  .string()
  .regex(/^-?\d+(\.\d{1,2})?$/, "money must be a decimal string with at most 2 decimals");

export type MoneyString = z.infer<typeof moneyStringSchema>;

/** Validate + parse a money string into integer cents; throws on invalid. */
export function parseMoneyString(input: unknown): Cents {
  const value = moneyStringSchema.parse(input);
  return parseMoney(value);
}

/** Guard: is the unknown a valid money string? */
export function isMoneyString(input: unknown): input is string {
  return moneyStringSchema.safeParse(input).success;
}

/** Format cents back to a backend-compatible money string. */
export function centsToMoneyString(cents: Cents): string {
  return formatMoney(cents);
}
