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
