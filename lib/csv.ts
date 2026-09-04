// Reusable CSV exporter. Builds a RFC-4180-ish CSV (comma-separated, quotes
// escaped) and triggers a browser download. Used by the Demand Analytics page
// ("Export CSV") and any future report export.
export function downloadCsv(
  filename: string,
  headers: string[],
  rows: Record<string, unknown>[],
): void {
  const escape = (value: unknown): string => {
    if (value === null || value === undefined) return "";
    const str = String(value);
    return /[",\r\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };

  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((h) => escape(row[h])).join(",")),
  ];
  const csv = lines.join("\r\n");

  if (typeof document === "undefined") return; // guard against SSR/Node
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
