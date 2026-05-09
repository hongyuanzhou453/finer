/**
 * Shared proxy helper for Next.js API routes that forward to the Python backend.
 *
 * Handles non-JSON responses (e.g. plain-text "Internal Server Error") gracefully
 * instead of crashing with SyntaxError on `res.json()`.
 */

import { NextResponse } from "next/server";

/**
 * Safely parse a backend response as JSON.
 *
 * If the response is not JSON (e.g. plain-text error from uvicorn/gunicorn),
 * wraps it in a canonical error envelope instead of throwing SyntaxError.
 */
export async function safeJsonResponse(
  res: Response,
): Promise<{ data: unknown; status: number }> {
  const contentType = res.headers.get("content-type") || "";

  if (!contentType.includes("application/json")) {
    const text = await res.text().catch(() => "");
    return {
      data: {
        ok: false,
        error: {
          code: `HTTP_${res.status}`,
          message: text || `Backend returned non-JSON response (status ${res.status})`,
        },
      },
      status: res.status >= 500 ? 502 : res.status,
    };
  }

  try {
    const data = await res.json();
    return { data, status: res.status };
  } catch {
    const text = await res.text().catch(() => "");
    return {
      data: {
        ok: false,
        error: {
          code: "PROXY_PARSE_ERROR",
          message: `Backend returned malformed JSON (status ${res.status}): ${text.slice(0, 200)}`,
        },
      },
      status: 502,
    };
  }
}

/**
 * Proxy a GET request to the Python backend and return a NextResponse.
 *
 * @param upstreamUrl - Full backend URL (e.g. "http://127.0.0.1:8000/api/files")
 * @param request - Incoming Next.js request (query params are forwarded)
 * @param fetchInit - Optional extra fetch options
 */
export async function proxyGet(
  upstreamUrl: string,
  request: Request,
  fetchInit?: RequestInit,
): Promise<NextResponse> {
  try {
    const url = new URL(upstreamUrl);
    const { searchParams } = new URL(request.url);
    searchParams.forEach((value, key) => {
      url.searchParams.set(key, value);
    });

    const res = await fetch(url.toString(), { cache: "no-store", ...fetchInit });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error(`API Proxy Error (GET ${upstreamUrl}):`, error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}

/**
 * Proxy a POST request to the Python backend and return a NextResponse.
 *
 * @param upstreamUrl - Full backend URL
 * @param request - Incoming Next.js request (body is forwarded as-is)
 * @param bodyTransform - Optional function to transform the request body before forwarding
 */
export async function proxyPost(
  upstreamUrl: string,
  request: Request,
  bodyTransform?: (req: Request) => Promise<BodyInit | undefined>,
): Promise<NextResponse> {
  try {
    const body = bodyTransform ? await bodyTransform(request) : await request.text();

    const res = await fetch(upstreamUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error(`API Proxy Error (POST ${upstreamUrl}):`, error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}
