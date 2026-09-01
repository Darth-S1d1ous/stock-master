import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth-token";

const PUBLIC_PATHS = new Set(["/login", "/api/session/login"]);

function securityHeaders(response: NextResponse, requestId: string): NextResponse {
  response.headers.set("x-request-id", requestId);
  response.headers.set("x-content-type-options", "nosniff");
  response.headers.set("referrer-policy", "strict-origin-when-cross-origin"); // control the policy browser sends referrer headers
  response.headers.set("permissions-policy", "camera=(), microphone=(), geolocation=()"); // forbid permissions to camera, microphone, geolocation
  response.headers.set("x-frame-options", "DENY"); // prevent clickjacking
  response.headers.set( // prevent XSS attacks
    "content-security-policy",
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self'",
  );
  return response;
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // nullish Coalescing
  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();
  const authenticated = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  const isPublic = PUBLIC_PATHS.has(request.nextUrl.pathname);

  if (!authenticated && !isPublic) {
    if (request.nextUrl.pathname.startsWith("/api/")) {
      return securityHeaders(
        NextResponse.json(
          { code: "authentication_required", message: "Please login first" },
          { status: 401 },
        ),
        requestId,
      );
    }
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return securityHeaders(NextResponse.redirect(loginUrl), requestId);
  }

  if (authenticated && request.nextUrl.pathname === "/login") {
    return securityHeaders(NextResponse.redirect(new URL("/", request.url)), requestId);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-request-id", requestId);
  return securityHeaders(NextResponse.next({ request: { headers: requestHeaders } }), requestId);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
