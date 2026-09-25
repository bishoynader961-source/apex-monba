export const CENTS_PER_UNIT = 100n;

export type Cents = bigint;

export function parseMoney(input: string | number | Cents): Cents {
  if (typeof input === "bigint") return input;
  if (typeof input === "number") {
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

export function addMoney(a: Cents, b: Cents): Cents {
  return a + b;
}

export function mulByQty(a: Cents, qty: number): Cents {
  if (!Number.isInteger(qty)) throw new Error("money: quantity must be integer");
  return a * BigInt(qty);
}

export function applyRate(a: Cents, basisPoints: number): Cents {
  if (!Number.isFinite(basisPoints)) throw new Error("money: invalid rate");
  const raw = a * BigInt(Math.round(basisPoints));
  const q = raw / 10000n;
  const r = raw % 10000n;
  return r * 2n >= 10000n ? q + 1n : q;
}

export function sumMoney(items: Cents[]): Cents {
  return items.reduce((acc, v) => acc + v, 0n);
}

export function formatMoney(cents: Cents): string {
  const negative = cents < 0n;
  const mag = negative ? -cents : cents;
  const whole = mag / CENTS_PER_UNIT;
  const frac = mag % CENTS_PER_UNIT;
  const out = `${whole}.${frac.toString().padStart(2, "0")}`;
  return negative ? `-${out}` : out;
}

export function toDecimalString(cents: Cents): string {
  return formatMoney(cents);
}

export function cmpMoney(a: Cents, b: Cents): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
