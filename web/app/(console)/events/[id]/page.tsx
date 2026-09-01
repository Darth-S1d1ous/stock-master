import Link from "next/link";
import { getEvent, listEventEvidence, listEventFeedback } from "@/lib/api/events";
import { feedbackLabels, metricLabels } from "@/lib/constants";
import { formatDate, formatDateTime, formatMetric } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { EventStatusForm, FeedbackForm } from "@/components/event-actions";

export default async function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [event, evidence, feedback] = await Promise.all([getEvent(id), listEventEvidence(id), listEventFeedback(id)]);
  return <div className="page">
    <section className="detail-hero"><p className="eyebrow">{event.symbol} · EVENT</p><h1>{event.title}</h1><p>{event.summary}</p><div className="actions"><StatusBadge value={event.severity} /><StatusBadge value={event.status} /></div><div className="detail-meta"><span>Occurred on {formatDate(event.occurred_on)}</span><span>Detected at {formatDateTime(event.detected_at)}</span><span>Rule version v{event.rule_version}</span></div></section>
    <div className="grid split"><div>
      <section className="card"><div className="card-header"><div><p className="eyebrow">Audit trail</p><h2>Evidence trail</h2></div><span className="badge">{evidence.length} records</span></div><div className="card-body">{evidence.length ? <ol className="timeline">{evidence.map((item) => <li key={item.id}><div className="actions"><strong>{item.metric ? metricLabels[item.metric] : "Source material"}</strong><span className="badge">{item.evidence_type}</span></div>{item.observed_value !== null ? <div className="evidence-value">{formatMetric(item.observed_value, item.metric)}</div> : null}<p>{item.description}</p>{item.excerpt ? <blockquote className="subtle">{item.excerpt}</blockquote> : null}<div className="meta">Source: {item.source} · Data as of {formatDate(item.data_as_of)} · Observed at {formatDateTime(item.observed_at)}</div>{item.source_reference ? <div className="meta">Source reference: {item.source_reference}</div> : null}</li>)}</ol> : <p className="lede">No evidence is available for this event.</p>}</div></section>
      <section className="card"><div className="card-header"><h2>Feedback history</h2><span className="badge">Append-only history</span></div><div className="card-body">{feedback.length ? <ol className="timeline">{feedback.map((item) => <li key={item.id}><strong>{feedbackLabels[item.feedback_type]}</strong><p className="subtle">{item.comment || "No comment provided"}</p><span className="meta">{formatDateTime(item.created_at)}</span></li>)}</ol> : <p className="lede">No user feedback has been recorded.</p>}</div></section>
    </div><aside>
      <section className="card"><div className="card-header"><h2>Event workflow</h2></div><div className="card-body"><EventStatusForm eventId={event.id} status={event.status} /></div></section>
      <section className="card"><div className="card-header"><h2>Research feedback</h2></div><div className="card-body"><FeedbackForm eventId={event.id} /></div></section>
      <section className="card card-body"><h3>Related research</h3><p className="subtle">Open the investment thesis that triggered this event to review its conditions and status history.</p><Link className="button" href={`/theses/${event.thesis_id}`}>View investment thesis</Link></section>
    </aside></div>
  </div>;
}
