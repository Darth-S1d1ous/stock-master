export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const host = forwardedHost || request.headers.get("host");
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  try {
    const parsed = new URL(origin);
    if (!host || parsed.host !== host) return false;
    return !forwardedProto || parsed.protocol === `${forwardedProto}:`;
  } catch {
    return false;
  }
}
