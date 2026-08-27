/**
 * Lightweight CSV export utility.
 * Converts an array of flat records into a standard browser CSV download blob.
 */

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const str = String(value);
  // Quote fields that contain comma, quote, newline, or leading/trailing space
  if (/[",\n\r\t ]/.test(str)) {
    const escaped = str.replace(/"/g, '""');
    return `"${escaped}"`;
  }
  return str;
}

export function downloadCsv(
  filename: string,
  headers: string[],
  rows: Record<string, unknown>[],
): void {
  const allKeys = Array.from(
    new Set([...headers, ...rows.flatMap((r) => Object.keys(r))]),
  );
  const headerLine = allKeys.map(escapeCsvCell).join(",");
  const bodyLines = rows.map((row) => allKeys.map((k) => escapeCsvCell(row[k])).join(","));
  const csv = [headerLine, ...bodyLines].join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
