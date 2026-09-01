import Link from "next/link";
import { ThesisForm } from "@/components/thesis-form";

export default function NewThesisPage() {
  return <div className="page"><header className="page-header"><div><p className="eyebrow">New thesis</p><h1>Record investment rationale</h1><p className="lede">State why the company matters, then define which facts would support, challenge, or invalidate that judgment.</p></div><Link className="button" href="/theses">Back to list</Link></header><ThesisForm /></div>;
}
