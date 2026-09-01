import "server-only";
import { apiRequest, queryString } from "@/lib/api/client";
import type { DomainEvent, EventEvidence, EventFeedback, EventSeverity, EventStatus, FeedbackType } from "@/types/domain";

export interface EventFilters {
  symbol?: string;
  thesis_id?: string;
  severity?: EventSeverity;
  status?: EventStatus;
  occurred_from?: string;
  occurred_to?: string;
  limit?: number;
  offset?: number;
}

export function listEvents(filters: EventFilters = {}) {
  return apiRequest<DomainEvent[]>(`/api/v1/events${queryString({ ...filters })}`);
}
export function getEvent(id: string) {
  return apiRequest<DomainEvent>(`/api/v1/events/${encodeURIComponent(id)}`);
}
export function listEventEvidence(id: string) {
  return apiRequest<EventEvidence[]>(`/api/v1/events/${encodeURIComponent(id)}/evidence`);
}
export function updateEventStatus(id: string, status: EventStatus) {
  return apiRequest<DomainEvent>(`/api/v1/events/${encodeURIComponent(id)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
export function listEventFeedback(id: string) {
  return apiRequest<EventFeedback[]>(`/api/v1/events/${encodeURIComponent(id)}/feedback`);
}
export function createEventFeedback(id: string, feedbackType: FeedbackType, comment?: string) {
  return apiRequest<EventFeedback>(`/api/v1/events/${encodeURIComponent(id)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback_type: feedbackType, comment: comment || null }),
  });
}
