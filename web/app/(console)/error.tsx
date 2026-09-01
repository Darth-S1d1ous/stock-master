"use client";

export default function ConsoleError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="page">
      <div className="empty-state card">
        <div className="empty-mark">!</div>
        <h3>Unable to load data</h3>
        <p>The backend may be unavailable or incompletely configured. Verify the service and try again.</p>
        <button className="button button-primary" onClick={reset}>Reload</button>
      </div>
    </div>
  );
}
