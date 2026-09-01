import { LogOut } from "lucide-react";
import { Navigation } from "@/components/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">S</div><div className="brand-copy"><strong>Stock Master</strong><span>THESIS MONITOR</span></div></div>
        <Navigation />
        <div className="sidebar-footer">
          <form method="post" action="/api/session/logout">
            <button className="nav-link logout" type="submit"><LogOut size={17} /><span>Sign out</span></button>
          </form>
        </div>
      </aside>
      <main className="main">
        <header className="topbar"><span className="topbar-label">Auditable investment research console</span><span className="live-pill"><span className="live-dot" />Deterministic rule engine</span></header>
        {children}
      </main>
    </div>
  );
}
