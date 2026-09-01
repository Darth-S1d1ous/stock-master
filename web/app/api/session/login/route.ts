import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { createSessionToken, SESSION_COOKIE } from "@/lib/auth-token";
import { isSameOriginRequest } from "@/lib/request-security";

const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 5;
const attempts = new Map<string, { count: number; resetAt: number }>();

function sameValue(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}

function clientKey(request: NextRequest): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ code: "origin_rejected", message: "The request origin is invalid." }, { status: 403 });
  }

  const key = clientKey(request);
  const now = Date.now();
  const current = attempts.get(key);
  if (current && current.resetAt > now && current.count >= MAX_ATTEMPTS) {
    return NextResponse.json({ code: "login_rate_limited", message: "Too many attempts. Please try again later." }, { status: 429 });
  }

  const body = await request.json().catch(() => null) as { password?: unknown } | null;
  const supplied = typeof body?.password === "string" ? body.password : "";
  const expected = process.env.WEB_ADMIN_PASSWORD ?? "";
  if (!expected || expected.length < 12) {
    console.error(JSON.stringify({ err_code: "web_auth_misconfigured", err_msg: "WEB_ADMIN_PASSWORD is missing or too short" }));
    return NextResponse.json({ code: "service_unavailable", message: "Web sign-in is not configured." }, { status: 503 });
  }

  if (!sameValue(supplied, expected)) {
    const next = !current || current.resetAt <= now ? { count: 1, resetAt: now + WINDOW_MS } : { ...current, count: current.count + 1 };
    attempts.set(key, next);
    return NextResponse.json({ code: "invalid_credentials", message: "The password is incorrect." }, { status: 401 });
  }

  attempts.delete(key);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, await createSessionToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 12 * 60 * 60,
  });
  return response;
}
