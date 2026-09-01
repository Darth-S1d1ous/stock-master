"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/session/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password: form.get("password") }),
      });
      const result = await response.json() as { message?: string };
      if (!response.ok) {
        setError(result.message ?? "Sign-in failed.");
        return;
      }
      const next = params.get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch {
      setError("Unable to reach the web service. Please try again later.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {error ? <div className="form-message error" role="alert">{error}</div> : null}
      <div className="field"><label htmlFor="password">Console password</label><input id="password" name="password" type="password" minLength={12} autoComplete="current-password" required autoFocus /></div>
      <button className="button button-primary" disabled={pending} type="submit">{pending ? "Verifying…" : "Open research console"}</button>
    </form>
  );
}
