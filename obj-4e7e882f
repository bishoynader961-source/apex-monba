// Locale-aware formatting helpers using Intl APIs.
import type { Locale } from "@/lib/i18n/config";

const CURRENCY_MAP: Record<string, string> = {
  en: "USD", de: "EUR", es: "EUR", fr: "EUR", pt: "BRL", ar: "EGP",
};

/** Format integer cents as locale-aware currency string. */
export function formatCurrency(cents: bigint, locale: Locale): string {
  const currency = CURRENCY_MAP[locale] ?? "USD";
  const amount = Number(cents) / 100;
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
}

/** Format an ISO date string as locale-aware short date. */
export function formatDate(isoDate: string, locale: Locale): string {
  if (!isoDate) return "";
  const d = new Date(isoDate);
  if (isNaN(d.getTime())) return isoDate;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(d);
}

/** Format an ISO datetime string as locale-aware datetime. */
export function formatDateTime(isoDatetime: string, locale: Locale): string {
  if (!isoDatetime) return "";
  const d = new Date(isoDatetime);
  if (isNaN(d.getTime())) return isoDatetime;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

/** Locale-aware number formatting (no currency). */
export function formatNumber(value: number, locale: Locale, decimals = 0): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
}
