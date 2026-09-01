import "server-only";
import { apiRequest, queryString } from "@/lib/api/client";
import type {
  InvestmentThesis,
  MarketDataSource,
  PriceAdjustment,
  ThesisCondition,
  ThesisMonitoringResult,
  ThesisStatus,
  ThesisStatusHistory,
} from "@/types/domain";

export function listTheses(filters: { symbol?: string; status?: ThesisStatus; limit?: number; offset?: number } = {}) {
  return apiRequest<InvestmentThesis[]>(`/api/v1/theses${queryString(filters)}`);
}
export function getThesis(id: string) {
  return apiRequest<InvestmentThesis>(`/api/v1/theses/${encodeURIComponent(id)}`);
}
export function createThesis(body: { symbol: string; title: string; description: string }) {
  return apiRequest<InvestmentThesis>("/api/v1/theses", { method: "POST", body: JSON.stringify(body) });
}
export function updateThesis(id: string, body: Record<string, unknown>) {
  return apiRequest<InvestmentThesis>(`/api/v1/theses/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) });
}
export function listConditions(id: string, enabled?: boolean) {
  return apiRequest<ThesisCondition[]>(`/api/v1/theses/${encodeURIComponent(id)}/conditions${queryString({ enabled: enabled === undefined ? undefined : String(enabled) })}`);
}
export function createCondition(id: string, body: Record<string, unknown>) {
  return apiRequest<ThesisCondition>(`/api/v1/theses/${encodeURIComponent(id)}/conditions`, { method: "POST", body: JSON.stringify(body) });
}
export function updateCondition(thesisId: string, conditionId: string, body: Record<string, unknown>) {
  return apiRequest<ThesisCondition>(`/api/v1/theses/${encodeURIComponent(thesisId)}/conditions/${encodeURIComponent(conditionId)}`, { method: "PATCH", body: JSON.stringify(body) });
}
export function listStatusHistory(id: string) {
  return apiRequest<ThesisStatusHistory[]>(`/api/v1/theses/${encodeURIComponent(id)}/status-history`);
}
export function evaluateThesis(id: string, source: MarketDataSource, adjustment: PriceAdjustment) {
  return apiRequest<ThesisMonitoringResult>(`/api/v1/theses/${encodeURIComponent(id)}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ source, adjustment }),
  });
}
