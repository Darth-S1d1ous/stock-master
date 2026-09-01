import { SignJWT } from "jose/jwt/sign";
import { jwtVerify } from "jose/jwt/verify";

export const SESSION_COOKIE = "stock_master_session";
const SESSION_ISSUER = "stock-master-web";
const SESSION_AUDIENCE = "stock-master-console";

function sessionKey(): Uint8Array {
  // read from environment variable
  const secret = process.env.WEB_SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("WEB_SESSION_SECRET must contain at least 32 characters");
  }
  return new TextEncoder().encode(secret);
}

export async function createSessionToken(): Promise<string> {
  return new SignJWT({ role: "owner" })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject("owner")
    .setIssuer(SESSION_ISSUER)
    .setAudience(SESSION_AUDIENCE)
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(sessionKey());
}

export async function verifySessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    await jwtVerify(token, sessionKey(), {
      algorithms: ["HS256"],
      issuer: SESSION_ISSUER,
      audience: SESSION_AUDIENCE,
      subject: "owner",
    });
    return true;
  } catch {
    return false;
  }
}
