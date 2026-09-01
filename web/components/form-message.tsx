"use client";

import type { ActionState } from "@/lib/errors";

export function FormMessage({ state }: { state: ActionState }) {
  if (!state.message) return null;
  return <div className={state.ok ? "form-message success" : "form-message error"} role="status">{state.message}</div>;
}
