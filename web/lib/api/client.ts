import "server-only";
import { headers } from "next/headers";
import { ApiError, type ErrorEnvelope } from "@/lib/errors";

function backendConfig(): { baseUrl: string; token: string } {
  const baseUrl = process.env.BACKEND_API_URL;
  const token = process.env.BACKEND_API_TOKEN;
  if (!baseUrl || !token) {
    throw new Error("BACKEND_API_URL and BACKEND_API_TOKEN are required");
  }
  const parsed = new URL(baseUrl);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("BACKEND_API_URL must use HTTP or HTTPS");
  }
  return { baseUrl: parsed.toString().replace(/\/$/, ""), token };
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.code === "string" && typeof candidate.message === "string";
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!path.startsWith("/api/v1/")) throw new Error("Backend path is not allowed");
  const { baseUrl, token } = backendConfig();
  const incomingHeaders = await headers();
  const requestId = incomingHeaders.get("x-request-id") ?? crypto.randomUUID();
  const method = init.method ?? "GET";
  const startedAt = performance.now();

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(12_000),
      headers: {
        accept: "application/json",
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
        "x-request-id": requestId,
        ...init.headers,
      },
    });

    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const envelope = isErrorEnvelope(body)
        ? body
        : { code: "upstream_error", message: "后端服务未能完成请求。" };
      console.error(JSON.stringify({
        level: "error",
        request_id: requestId,
        route: path,
        method,
        status_code: response.status,
        duration_ms: Math.round(performance.now() - startedAt),
        err_code: envelope.code,
        err_msg: envelope.message,
      }));
      throw new ApiError(response.status, envelope.code, envelope.message);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const errMsg = error instanceof Error ? error.message : "Unknown upstream failure";
    console.error(JSON.stringify({
      level: "error",
      request_id: requestId,
      route: path,
      method,
      status_code: 502,
      duration_ms: Math.round(performance.now() - startedAt),
      err_code: "backend_unavailable",
      err_msg: errMsg,
    }));
    throw new ApiError(502, "backend_unavailable", "Backend service is unavailable",);
  }
}

// Transform an object into a url query string (e.g. ?name=Smith&age=18&page=2)
export function queryString(values: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}
