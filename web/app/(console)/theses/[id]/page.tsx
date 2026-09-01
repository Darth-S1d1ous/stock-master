import Link from "next/link";
import { Archive, ArrowRight } from "lucide-react";
import { getThesis, listConditions, listStatusHistory } from "@/lib/api/theses";
import { listEvents } from "@/lib/api/events";
import { metricLabels, operatorLabels, thesisStatusLabels } from "@/lib/constants";
import { formatDate, formatDateTime, formatMetric } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { ThesisForm } from "@/components/thesis-form";
import { ConditionForm } from "@/components/condition-form";
import { EvaluationPanel } from "@/components/evaluation-panel";
import { archiveThesisAction } from "../actions";

export default async function ThesisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [thesis, conditions, history, events] = await Promise.all([getThesis(id), listConditions(id), listStatusHistory(id), listEvents({ thesis_id: id, limit: 8 })]);
  return <div className="page">
    <section className="detail-hero"><p className="eyebrow">{thesis.symbol} · {thesisStatusLabels[thesis.status]}</p><h1>{thesis.title}</h1><p>{thesis.description}</p><div className="detail-meta"><span>Version v{thesis.version}</span><span>Created on {formatDate(thesis.created_at)}</span><span>Updated at {formatDateTime(thesis.updated_at)}</span></div></section>
    <div className="grid split">
      <div>
        <section className="card"><div className="card-header"><div><p className="eyebrow">Monitoring rules</p><h2>Monitoring conditions</h2></div><span className="badge">{conditions.length} records</span></div><div className="card-body">
          {conditions.map((condition) => <details className="condition" key={condition.id}><summary className="condition-top" style={{ cursor: "pointer" }}><div><strong>{condition.name}</strong><p className="subtle">{condition.description || "No description"}</p><div className="rule">{metricLabels[condition.metric]} {operatorLabels[condition.operator]} {formatMetric(condition.threshold, condition.metric)} · For {condition.consecutive_periods} periods</div></div><div><StatusBadge value={condition.kind} /> {!condition.enabled ? <span className="badge">Disabled</span> : null}</div></summary><div style={{ paddingTop: 20 }}><ConditionForm thesisId={id} condition={condition} /></div></details>)}
          {!conditions.length ? <p className="lede">No monitoring conditions are defined. Add a condition before running an evaluation.</p> : null}
          <details style={{ marginTop: 22 }}><summary className="button">Add monitoring condition</summary><div style={{ paddingTop: 20 }}><ConditionForm thesisId={id} /></div></details>
        </div></section>
        <EvaluationPanel thesisId={id} />
        <section className="card"><div className="card-header"><h2>Related events</h2><Link className="button" href={`/events?thesis_id=${id}`}>View all <ArrowRight size={15} /></Link></div><div className="card-body">{events.length ? events.map((event) => <div className="condition" key={event.id}><div className="condition-top"><div><Link className="title-link" href={`/events/${event.id}`}>{event.title}</Link><span className="subtle">{formatDate(event.occurred_on)} · {event.summary}</span></div><StatusBadge value={event.severity} /></div></div>) : <p className="lede">No events are currently associated with this thesis.</p>}</div></section>
      </div>
      <aside>
        <section className="card"><div className="card-header"><h2>Edit thesis</h2></div><div style={{ padding: 0 }}><ThesisForm thesis={thesis} /></div></section>
        <section className="card"><div className="card-header"><h2>Status history</h2></div><div className="card-body">{history.length ? <ol className="timeline">{history.map((item) => <li key={item.id}><strong>{thesisStatusLabels[item.from_status]} → {thesisStatusLabels[item.to_status]}</strong><p className="subtle">{item.reason}</p><span className="meta">{formatDateTime(item.changed_at)}</span></li>)}</ol> : <p className="lede">No status changes have been recorded.</p>}</div></section>
        {thesis.status !== "archived" ? <section className="card card-body"><h3>End monitoring</h3><p className="subtle">Archiving preserves the complete audit history but removes the thesis from monitoring.</p><form action={archiveThesisAction}><input type="hidden" name="id" value={thesis.id} /><input type="hidden" name="expected_version" value={thesis.version} /><button className="button button-danger" type="submit"><Archive size={15} />Archive thesis</button></form></section> : null}
      </aside>
    </div>
  </div>;
}
