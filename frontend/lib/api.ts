/** Backend base URL from env, with protocol if omitted. */
export function apiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
  if (/^https?:\/\//i.test(raw)) return raw;
  if (/^(localhost|127\.0\.0\.1)(:|\/|$)/i.test(raw)) return `http://${raw}`;
  return `https://${raw}`;
}

/**
 * Header for authenticated backend calls, issued via create_api_key.py.
 *
 * This ships in the client bundle (NEXT_PUBLIC_*), so it's visible to
 * anyone who can load the page, same as any other client-side secret.
 * Fine for an internal tool on a trusted network; if this app is ever
 * exposed publicly, proxy these calls through a Next.js server route
 * that holds the key server-side instead.
 */
export function apiKeyHeader(): Record<string, string> {
  const key = process.env.NEXT_PUBLIC_API_KEY;
  return key ? { "X-API-Key": key } : {};
}

/** Pull a readable message out of a failed response: FastAPI's error
 * bodies (HTTPExceptions, and the rate limiter's 429s) are all
 * {"detail": "..."}, already worded for display, so that's read first.
 * 401s get a dedicated hint since there's no body to parse for those. */
export async function errorMessage(response: Response): Promise<string> {
  if (response.status === 401) {
    return "Authentication failed. Check that your API key is set correctly and the dev server was restarted after setting it.";
  }
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON, fall through to the generic message
  }
  return `Request failed (server responded ${response.status}).`;
}
