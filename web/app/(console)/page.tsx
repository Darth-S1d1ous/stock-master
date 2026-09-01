import Link from "next/link";
import { ArrowRight, Plus } from "lucide-react";
import { listEvents } from "@/lib/api/events";
import { listTheses } from "@/lib/api/theses";
import { formatDate } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";

export default async function DashboardPage() {
  const [theses, events] = await Promise.all([listTheses({ limit: 500 }), listEvents({ limit: 500 })]);
  const active = theses.filter((item) => item.status === "active" || item.status === "challenged").length;
  const open = events.filter((item) => item.status === "open").length;
  const critical = events.filter((item) => item.severity === "critical" && item.status === "open").length;
  const feedbackPending = events.filter((item) => item.status === "open" || item.status === "acknowledged").length;
  const recent = events.slice(0, 6);

  return (
    <div className="page">
      <header className="page-header">
        <div><p className="eyebrow">Research overview</p><h1>Your investment judgments at a glance.</h1><p className="lede">Focus on material fact changes while preserving the complete evidence trail for every rule decision.</p></div>
        <Link className="button button-primary" href="/theses/new"><Plus size={16} />Create investment thesis</Link>
      </header>
      <section className="grid stats" aria-label="Key metrics">
        <div className="stat"><span className="stat-label">Monitored theses</span><div className="stat-value">{active}</div><span className="stat-foot">A total of {theses.length} research records</span></div>
        <div className="stat"><span className="stat-label">Open events</span><div className="stat-value">{open}</div><span className="stat-foot">Awaiting acknowledgment or resolution</span></div>
        <div className="stat"><span className="stat-label">Critical events</span><div className="stat-value">{critical}</div><span className="stat-foot">Open invalidation signals</span></div>
        <div className="stat"><span className="stat-label">Pending review</span><div className="stat-value">{feedbackPending}</div><span className="stat-foot">User feedback is required</span></div>
      </section>
      <section className="card">
        <div className="card-header"><div><p className="eyebrow">Recent signals</p><h2>Latest events</h2></div><Link className="button" href="/events">View all <ArrowRight size={15} /></Link></div>
        {recent.length ? <div className="table-wrap"><table><thead><tr><th>Symbol and event</th><th>Severity</th><th>Status</th><th>Occurred on</th></tr></thead><tbody>{recent.map((event) => <tr key={event.id} className={`event-row-${event.severity}`}><td><Link className="title-link" href={`/events/${event.id}`}>{event.title}</Link><span className="symbol">{event.symbol}</span></td><td><StatusBadge value={event.severity} /></td><td><StatusBadge value={event.status} /></td><td>{formatDate(event.occurred_on)}</td></tr>)}</tbody></table></div> : <EmptyState title="No monitoring events yet" description="Create a thesis and conditions, ingest data, and then run a deterministic evaluation." action="Create investment thesis" href="/theses/new" />}
      </section>
    </div>
  );
}
