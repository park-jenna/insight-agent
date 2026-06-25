/** Backend base URL from env, with protocol if omitted. */
export function apiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
  if (/^https?:\/\//i.test(raw)) return raw;
  if (/^(localhost|127\.0\.0\.1)(:|\/|$)/i.test(raw)) return `http://${raw}`;
  return `https://${raw}`;
}
