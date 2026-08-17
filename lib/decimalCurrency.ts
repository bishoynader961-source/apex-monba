// Integer-cents money math. NEVER use floating point for currency.
// Money is stored as a bigint of cents; serialized via `format()`/`toString`.

export const CENTS_PER_UNIT = 100n;

export type Cents = bigint;

/** Parse a Decimal string ("12.34", "0", "-5.5") into integer cents. */
export function parseMoney(input: string | number | Cents): Cents {
  if (typeof input === "bigint") return input;
  if (typeof input === "number") {
    // Only whole-number or .xx numbers from trusted config; reject lossy input.
    if (!Number.isFinite(input)) throw new Error("money: non-finite number");
    return BigInt(Math.round(input * 100));
  }
  const s = input.trim();
  if (!/^-?\d+(\.\d+)?$/.test(s)) throw new Error(`money: invalid decimal "${input}"`);
  const negative = s.startsWith("-");
  const digits = negative ? s.slice(1) : s;
  const [whole, frac = ""] = digits.split(".");
  const fracPadded = (frac + "00").slice(0, 2);
  const mag = BigInt(whole || "0") * CENTS_PER_UNIT + BigInt(fracPadded || "0");
  return negative ? -mag : mag;
}

/** Add cents. */
export function addMoney(a: Cents, b: Cents): Cents {
  return a + b;
}

/** Multiply cents by a (trusted) quantity integer. */
export function mulByQty(a: Cents, qty: number): Cents {
  if (!Number.isInteger(qty)) throw new Error("money: quantity must be integer");
  return a * BigInt(qty);
}

/** Multiply cents by a tax rate expressed as an integer basis point (e.g. 825 = 8.25%). */
export function applyRate(a: Cents, basisPoints: number): Cents {
  if (!Number.isFinite(basisPoints)) throw new Error("money: invalid rate");
  // tax = a * basisPoints / 10000, rounded half-up to the nearest cent.
  const raw = a * BigInt(Math.round(basisPoints));
  const q = raw / 10000n;
  const r = raw % 10000n;
  return r * 2n >= 10000n ? q + 1n : q;
}

/** Sum a list of cents. */
export function sumMoney(items: Cents[]): Cents {
  return items.reduce((acc, v) => acc + v, 0n);
}

/** Format cents to a fixed 2-decimal string ("12.34"). */
export function formatMoney(cents: Cents): string {
  const negative = cents < 0n;
  const mag = negative ? -cents : cents;
  const whole = mag / CENTS_PER_UNIT;
  const frac = mag % CENTS_PER_UNIT;
  const out = `${whole}.${frac.toString().padStart(2, "0")}`;
  return negative ? `-${out}` : out;
}

/** Backend Decimal string for a cents value, used in request bodies. */
export function toDecimalString(cents: Cents): string {
  return formatMoney(cents);
}

/** Compare two cents values: -1, 0, 1. */
export function cmpMoney(a: Cents, b: Cents): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
