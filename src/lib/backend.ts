// =================================================================
// Client for the Python safety service (backend/).
//
// The deterministic layer — safety checks, prompt composition — lives in
// `backend/` and is reached over HTTP. These route handlers proxy to it
// rather than the browser calling it directly, for three reasons: the
// service URL stays server-side instead of shipping in the bundle, there is
// no CORS to configure in production, and the existing `/api/*` contract
// the UI depends on is preserved exactly.
//
// The TypeScript engine in `src/lib/safety-engine.ts` is no longer on the
// request path. It stays because the Python port is verified against it —
// see `tests/differential/` and `backend/tests/divergence/`.
// =================================================================

/** Where the Python service is listening. Server-side only, never NEXT_PUBLIC_. */
export const BACKEND_URL = (
  process.env.BRAHMO_API_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** How long to wait before giving up on the service. */
const TIMEOUT_MS = Number(process.env.BRAHMO_API_TIMEOUT_MS || 30_000);

export class BackendError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "BackendError";
  }
}

/**
 * Turn whatever the service said into a single human-readable string.
 *
 * FastAPI reports errors as `detail`, which is a string for our own
 * HTTPExceptions and an array of per-field objects for request-validation
 * failures. The UI reads `error`. Without this both shapes render as
 * "undefined", which is worse than the original problem.
 */
function describe(status: number, body: unknown): string {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown; error?: unknown }).detail
      ?? (body as { error?: unknown }).error;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((d) => {
          if (typeof d === "string") return d;
          const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== "body").join(".") : "";
          const msg = typeof d?.msg === "string" ? d.msg : JSON.stringify(d);
          return loc ? `${loc}: ${msg}` : msg;
        })
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
  }
  return `Safety service returned ${status}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      cache: "no-store",
    });
  } catch (err: unknown) {
    const aborted = err instanceof Error && err.name === "AbortError";
    throw new BackendError(
      aborted
        ? `Safety service did not respond within ${TIMEOUT_MS}ms (${BACKEND_URL})`
        : `Cannot reach the safety service at ${BACKEND_URL}. Start it with: ` +
          `cd backend && uv run uvicorn --factory brahmo.api:create_app`,
      503,
    );
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) throw new BackendError(describe(res.status, body), res.status);
  return body as T;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function post<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(payload) });
}

/** `{ error }` + status, in the shape the UI already handles. */
export function errorResponse(err: unknown): { body: { error: string }; status: number } {
  if (err instanceof BackendError) return { body: { error: err.message }, status: err.status };
  const message = err instanceof Error ? err.message : "Unexpected error";
  return { body: { error: message }, status: 500 };
}
