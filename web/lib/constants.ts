import type { ComparisonOperator, ConditionKind, EventSeverity, EventStatus, FeedbackType, MetricCode, ThesisStatus } from "@/types/domain";

export const thesisStatusLabels: Record<ThesisStatus, string> = {
  active: "Active",
  challenged: "Challenged",
  invalidated: "Invalidated",
  archived: "Archived",
};
export const conditionKindLabels: Record<ConditionKind, string> = {
  support: "Support signal",
  risk: "Risk signal",
  invalidation: "Invalidation condition",
};
export const metricLabels: Record<MetricCode, string> = {
  daily_price_change_percent: "Daily price change",
  volume_ratio_20d: "20-day volume ratio",
  pe_ratio: "P/E ratio",
  pe_ratio_change_percent: "P/E ratio change",
  price_to_book_ratio: "Price-to-book ratio",
  price_to_book_change_percent: "Price-to-book ratio change",
  ebitda: "EBITDA",
};
export const operatorLabels: Record<ComparisonOperator, string> = {
  greater_than: ">",
  greater_than_or_equal: "≥",
  less_than: "<",
  less_than_or_equal: "≤",
};
export const severityLabels: Record<EventSeverity, string> = { info: "Info", warning: "Warning", critical: "Critical" };
export const eventStatusLabels: Record<EventStatus, string> = { open: "Open", acknowledged: "Acknowledged", resolved: "Resolved", dismissed: "Dismissed" };
export const feedbackLabels: Record<FeedbackType, string> = {
  useful: "Useful",
  not_useful: "Not useful",
  false_positive: "False positive",
  confirmed: "Confirmed",
  ignored: "Ignored",
  duplicate: "Duplicate",
  not_relevant: "Not relevant",
};

export const metricOptions = Object.entries(metricLabels) as [MetricCode, string][];
export const operatorOptions = Object.entries(operatorLabels) as [ComparisonOperator, string][];
export const feedbackOptions = Object.entries(feedbackLabels) as [FeedbackType, string][];
