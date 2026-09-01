import { Suspense } from "react";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="login-page">
      <section className="login-art">
        <div className="brand-mark">S</div>
        <p className="eyebrow">STOCK MASTER BOT</p>
        <h1>Continuously validate your investment rationale.</h1>
        <p>Keep facts, rules, and judgment separate. Every event comes from deterministic calculations and traces back to its observations and evidence.</p>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <p className="eyebrow">Secure access</p>
          <h2>Welcome back</h2>
          <p className="lede">Sign in to the single-user research workspace. API credentials always remain on the server.</p>
          <Suspense><LoginForm /></Suspense>
        </div>
      </section>
    </main>
  );
}
