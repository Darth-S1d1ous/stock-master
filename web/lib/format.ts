// ES(ECMAScript) is the standard for JavaScript, so we have ES2023, ES2024...
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric" }).format(new Date(value));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

export function formatMetric(value: string | null, metric?: string | null): string {
  if (value === null) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  if (metric?.includes("percent")) return `${number.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  if (metric === "ebitda") return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(number);
  return number.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
