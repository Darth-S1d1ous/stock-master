import Link from "next/link";
import { listEvents } from "@/lib/api/events";
import { eventStatusLabels, severityLabels } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";
import type { EventSeverity, EventStatus } from "@/types/domain";

export default async function EventsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const severity = Object.hasOwn(severityLabels, params.severity ?? "") ? params.severity as EventSeverity : undefined;
  const status = Object.hasOwn(eventStatusLabels, params.status ?? "") ? params.status as EventStatus : undefined;
  const offset = Math.max(0, Number(params.offset) || 0); const limit = 25;
  const filters = { symbol: params.symbol?.trim().toUpperCase(), thesis_id: params.thesis_id, severity, status, occurred_from: params.occurred_from, occurred_to: params.occurred_to, limit, offset };
  const events = await listEvents(filters);
  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">Evidence inbox</p><h1>Event center</h1><p className="lede">Review events triggered by deterministic rules, inspect their evidence, and record feedback.</p></div></header>
    <form className="filters"><input name="symbol" defaultValue={filters.symbol} placeholder="Stock symbol" maxLength={15} /><select name="severity" defaultValue={severity ?? ""}><option value="">All severities</option>{Object.entries(severityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select name="status" defaultValue={status ?? ""}><option value="">All statuses</option>{Object.entries(eventStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input name="occurred_from" type="date" defaultValue={filters.occurred_from} aria-label="Start date" /><input name="occurred_to" type="date" defaultValue={filters.occurred_to} aria-label="End date" /><button className="button" type="submit">Filter</button><Link className="button" href="/events">Reset</Link></form>
    <section className="card">{events.length ? <div className="table-wrap"><table><thead><tr><th>Event</th><th>Symbol</th><th>Severity</th><th>Status</th><th>Occurred on</th></tr></thead><tbody>{events.map((event) => <tr key={event.id} className={`event-row-${event.severity}`}><td><Link className="title-link" href={`/events/${event.id}`}>{event.title}</Link><span className="subtle">{event.summary.slice(0, 100)}{event.summary.length > 100 ? "…" : ""}</span></td><td><span className="symbol">{event.symbol}</span></td><td><StatusBadge value={event.severity} /></td><td><StatusBadge value={event.status} /></td><td>{formatDate(event.occurred_on)}</td></tr>)}</tbody></table></div> : <EmptyState title="No matching events" description="Adjust the filters or run a monitoring evaluation for an investment thesis." />}</section>
    <div className="actions" style={{ marginTop: 18 }}>{offset > 0 ? <Link className="button" href={`/events?offset=${Math.max(0, offset - limit)}`}>Previous</Link> : null}{events.length === limit ? <Link className="button" href={`/events?offset=${offset + limit}`}>Next</Link> : null}</div>
  </div>;
}
