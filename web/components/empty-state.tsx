import Link from "next/link";

export function EmptyState({ title, description, action, href }: { title: string; description: string; action?: string; href?: string }) {
  return (
    <div className="empty-state">
      <div className="empty-mark" aria-hidden="true">◎</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && href ? <Link className="button button-primary" href={href}>{action}</Link> : null}
    </div>
  );
}
