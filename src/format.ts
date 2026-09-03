export function formatSeconds(seconds: number): string {
  const safeSeconds = Math.max(0, seconds);
  const totalTenths = Math.round(safeSeconds * 10);
  const minutes = Math.floor(totalTenths / 600);
  const remainingTenths = totalTenths % 600;
  return `${minutes}:${(remainingTenths / 10).toFixed(1).padStart(4, "0")}`;
}

export function formatDate(value?: string | null, locale?: string): string | null {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}
