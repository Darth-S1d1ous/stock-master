"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({ children, pendingText = "Processing…", className = "button button-primary" }: { children: React.ReactNode; pendingText?: string; className?: string }) {
  const { pending } = useFormStatus();
  return <button className={className} type="submit" disabled={pending}>{pending ? pendingText : children}</button>;
}
