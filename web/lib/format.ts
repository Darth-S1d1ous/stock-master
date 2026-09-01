export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(new Date(value));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

export function formatMetric(value: string | null, metric?: string | null): string {
  if (value === null) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  if (metric?.includes("percent")) return `${number.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`;
  if (metric === "ebitda") return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 }).format(number);
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}
