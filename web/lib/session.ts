import "server-only"; // from Next.js
import { cookies } from "next/headers";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth-token";

export async function hasSession(): Promise<boolean> {
  const cookieStore = await cookies(); // all cookies from the CURRENT request
  return verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value);
}
