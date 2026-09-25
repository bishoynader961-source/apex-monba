import { useRegionStore } from "@/stores/regionStore";

export function useCurrencyFormatter() {
  const region = useRegionStore((s) => s.region);
  const symbol = region?.currency_symbol ?? "$";
  const code = region?.currency ?? "USD";

  const format = (amount: number): string => {
    return `${symbol}${amount.toFixed(2)}`;
  };

  const formatWithCode = (amount: number): string => {
    return `${symbol}${amount.toFixed(2)} ${code}`;
  };

  return { format, formatWithCode, symbol, code };
}

export function useDateFormatter() {
  const region = useRegionStore((s) => s.region);
  const fmt = region?.date_format ?? "MM/DD/YYYY";

  const format = (dateStr: string): string => {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const year = String(d.getFullYear());
    return fmt.replace("DD", day).replace("MM", month).replace("YYYY", year);
  };

  return { format, pattern: fmt };
}
