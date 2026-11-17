import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
// Streaming (SSE) needs the Node runtime so the body is piped, not buffered.
export const runtime = "nodejs";

function apiBase(): string {
  return (
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000"
  ).replace(/\/+$/, "");
}

const FORWARDED_HEADERS = ["accept", "accept-language", "cookie", "last-event-id", "user-agent"];

const PASSTHROUGH_HEADERS = [
  "content-type",
  "cache-control",
  "x-request-id",
  "x-accel-buffering",
  "www-authenticate",
];

/**
 * Same-origin read-only proxy for `/api/v1/*`.
 *
 * `EventSource` cannot attach our CSRF header and must call the Next origin, so
 * the SSE stream (and any other GET) is forwarded to FastAPI here. The upstream
 * body is piped straight through so `text/event-stream` is not buffered.
 */
async function proxy(request: NextRequest): Promise<Response> {
  const incoming = new URL(request.url);
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (!headers.has("accept")) headers.set("accept", "application/json");

  try {
    const upstream = await fetch(`${apiBase()}${incoming.pathname}${incoming.search}`, {
      method: "GET",
      headers,
      redirect: "manual",
      cache: "no-store",
    });

    const responseHeaders = new Headers();
    for (const name of PASSTHROUGH_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    // Required for SSE behind proxies: never buffer the event stream.
    responseHeaders.set("x-accel-buffering", "no");
    // Session/CSRF cookies must survive the hop (e.g. GET /auth/csrf).
    for (const cookie of upstream.headers.getSetCookie()) {
      responseHeaders.append("set-cookie", cookie);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "UPSTREAM_UNAVAILABLE",
          message: "后端服务暂时不可用，请稍后重试。",
          details: {},
        },
      },
      { status: 502 },
    );
  }
}

export async function GET(request: NextRequest): Promise<Response> {
  return proxy(request);
}