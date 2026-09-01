"use client";

import Link from "next/link";
import { Activity, FileText, LayoutDashboard } from "lucide-react";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/theses", label: "Investment thesis", icon: FileText },
  { href: "/events", label: "Event center", icon: Activity },
];

export function Navigation() {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main navigation">
      {items.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === href : pathname.startsWith(href);
        return <Link key={href} href={href} className={`nav-link${active ? " active" : ""}`}><Icon size={17} /><span>{label}</span></Link>;
      })}
    </nav>
  );
}
