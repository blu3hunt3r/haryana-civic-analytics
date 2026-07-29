export const integer = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0,
});

export function formatCount(value: number): string {
  return integer.format(value);
}

export function formatRupees(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "Not published";
  const absolute = Math.abs(value);
  if (absolute >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)} crore`;
  if (absolute >= 100_000) return `₹${(value / 100_000).toFixed(2)} lakh`;
  return `₹${integer.format(value)}`;
}

export function label(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function shortHash(value: string): string {
  return value ? `${value.slice(0, 10)}…${value.slice(-8)}` : "Not published";
}

