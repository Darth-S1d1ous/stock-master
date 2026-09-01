import type { ComparisonOperator, ConditionKind, EventSeverity, EventStatus, FeedbackType, MetricCode, ThesisStatus } from "@/types/domain";

export const thesisStatusLabels: Record<ThesisStatus, string> = {
  active: "监控中",
  challenged: "受挑战",
  invalidated: "已失效",
  archived: "已归档",
};
export const conditionKindLabels: Record<ConditionKind, string> = {
  support: "支持信号",
  risk: "风险信号",
  invalidation: "失效条件",
};
export const metricLabels: Record<MetricCode, string> = {
  daily_price_change_percent: "单日价格变动",
  volume_ratio_20d: "20 日成交量比",
  pe_ratio: "市盈率",
  pe_ratio_change_percent: "市盈率变动",
  price_to_book_ratio: "市净率",
  price_to_book_change_percent: "市净率变动",
  ebitda: "EBITDA",
};
export const operatorLabels: Record<ComparisonOperator, string> = {
  greater_than: ">",
  greater_than_or_equal: "≥",
  less_than: "<",
  less_than_or_equal: "≤",
};
export const severityLabels: Record<EventSeverity, string> = { info: "提示", warning: "警告", critical: "严重" };
export const eventStatusLabels: Record<EventStatus, string> = { open: "待处理", acknowledged: "已确认", resolved: "已解决", dismissed: "已忽略" };
export const feedbackLabels: Record<FeedbackType, string> = {
  useful: "有价值",
  not_useful: "价值有限",
  false_positive: "误报",
  confirmed: "已确认",
  ignored: "忽略",
  duplicate: "重复",
  not_relevant: "不相关",
};

export const metricOptions = Object.entries(metricLabels) as [MetricCode, string][];
export const operatorOptions = Object.entries(operatorLabels) as [ComparisonOperator, string][];
export const feedbackOptions = Object.entries(feedbackLabels) as [FeedbackType, string][];
