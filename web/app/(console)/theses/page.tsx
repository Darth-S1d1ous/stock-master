import Link from "next/link";
import { Plus } from "lucide-react";
import { listTheses } from "@/lib/api/theses";
import { formatDate } from "@/lib/format";
import { thesisStatusLabels } from "@/lib/constants";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";
import type { ThesisStatus } from "@/types/domain";

export default async function ThesesPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const status = Object.hasOwn(thesisStatusLabels, params.status ?? "") ? params.status as ThesisStatus : undefined;
  const symbol = params.symbol?.trim().toUpperCase();
  const offset = Math.max(0, Number(params.offset) || 0);
  const limit = 25;
  const theses = await listTheses({ symbol, status, limit, offset });
  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">Thesis registry</p><h1>Investment thesis</h1><p className="lede">Turn the reasons for holding a stock into a structured, continuously monitored research record.</p></div><Link className="button button-primary" href="/theses/new"><Plus size={16} />New thesis</Link></header>
    <form className="filters"><input name="symbol" defaultValue={symbol} placeholder="Stock symbol" maxLength={15} /><select name="status" defaultValue={status ?? ""}><option value="">All statuses</option>{Object.entries(thesisStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="button" type="submit">Filter</button><Link className="button" href="/theses">Reset</Link></form>
    <section className="card">{theses.length ? <div className="table-wrap"><table><thead><tr><th>Symbol</th><th>Investment thesis</th><th>Status</th><th>Version</th><th>Updated at</th></tr></thead><tbody>{theses.map((thesis) => <tr key={thesis.id}><td><span className="symbol">{thesis.symbol}</span></td><td><Link className="title-link" href={`/theses/${thesis.id}`}>{thesis.title}</Link><span className="subtle">{thesis.description.slice(0, 90)}{thesis.description.length > 90 ? "…" : ""}</span></td><td><StatusBadge value={thesis.status} /></td><td>v{thesis.version}</td><td>{formatDate(thesis.updated_at)}</td></tr>)}</tbody></table></div> : <EmptyState title="No matching investment theses" description="Adjust the filters or create the first structured investment thesis." action="Create thesis" href="/theses/new" />}</section>
    <div className="actions" style={{ marginTop: 18 }}>{offset > 0 ? <Link className="button" href={`/theses?offset=${Math.max(0, offset - limit)}`}>Previous</Link> : null}{theses.length === limit ? <Link className="button" href={`/theses?offset=${offset + limit}`}>Next</Link> : null}</div>
  </div>;
}
