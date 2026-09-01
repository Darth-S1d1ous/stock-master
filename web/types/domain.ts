export type ThesisStatus = "active" | "challenged" | "invalidated" | "archived";
export type ConditionKind = "support" | "risk" | "invalidation";
export type MetricCode =
  | "daily_price_change_percent"
  | "volume_ratio_20d"
  | "pe_ratio"
  | "pe_ratio_change_percent"
  | "price_to_book_ratio"
  | "price_to_book_change_percent"
  | "ebitda";
export type ComparisonOperator =
  | "greater_than"
  | "greater_than_or_equal"
  | "less_than"
  | "less_than_or_equal";
export type EventSeverity = "info" | "warning" | "critical";
export type EventStatus = "open" | "acknowledged" | "resolved" | "dismissed";
export type FeedbackType =
  | "useful"
  | "not_useful"
  | "false_positive"
  | "confirmed"
  | "ignored"
  | "duplicate"
  | "not_relevant";
export type MarketDataSource = "alpha_vantage" | "finnhub" | "yahoo_finance";
export type PriceAdjustment = "raw" | "split_adjusted" | "total_return";

export interface InvestmentThesis {
  id: string;
  symbol: string;
  title: string;
  description: string;
  status: ThesisStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ThesisCondition {
  id: string;
  thesis_id: string;
  name: string;
  description: string | null;
  kind: ConditionKind;
  metric: MetricCode;
  operator: ComparisonOperator;
  threshold: string;
  consecutive_periods: number;
  enabled: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ThesisStatusHistory {
  id: string;
  thesis_id: string;
  from_status: ThesisStatus;
  to_status: ThesisStatus;
  reason: string;
  triggering_event_id: string | null;
  changed_at: string;
}

export interface DomainEvent {
  id: string;
  thesis_id: string;
  condition_id: string;
  evaluation_id: string;
  symbol: string;
  event_type: string;
  severity: EventSeverity;
  status: EventStatus;
  title: string;
  summary: string;
  occurred_on: string;
  detected_at: string;
  rule_version: number;
}

export interface EventEvidence {
  id: string;
  event_id: string;
  evidence_type: "metric_observation" | "market_data" | "calculation" | "source_document";
  source: string;
  source_record_id: string | null;
  source_reference: string | null;
  metric: MetricCode | null;
  observed_value: string | null;
  description: string;
  excerpt: string | null;
  data_as_of: string | null;
  published_at: string | null;
  observed_at: string;
}

export interface EventFeedback {
  id: string;
  event_id: string;
  feedback_type: FeedbackType;
  comment: string | null;
  created_at: string;
}

export interface RuleEvaluation {
  id: string;
  thesis_id: string;
  condition_id: string;
  symbol: string;
  metric: MetricCode;
  operator: ComparisonOperator;
  observed_value: string;
  threshold: string;
  matched: boolean;
  consecutive_periods_required: number;
  consecutive_periods_matched: number;
  rule_version: number;
  data_as_of: string;
  evaluated_at: string;
  observation_ids: string[];
}

export interface ConditionMonitoringResult {
  condition: ThesisCondition;
  metric_result: { metric: MetricCode; value: string; data_as_of: string; observation_ids: string[] };
  evaluation: RuleEvaluation;
  event: DomainEvent | null;
  evidence: EventEvidence[];
  reused_evaluation: boolean;
}

export interface ThesisMonitoringResult {
  thesis: InvestmentThesis;
  source: MarketDataSource;
  started_at: string;
  completed_at: string;
  conditions: ConditionMonitoringResult[];
  evaluation_count: number;
  matched_count: number;
  event_count: number;
}
