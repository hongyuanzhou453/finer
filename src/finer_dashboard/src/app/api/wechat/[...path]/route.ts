import { NextResponse } from "next/server";
import { safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/wechat";

export async function GET(request: Request) {
  const { searchParams, pathname } = new URL(request.url);
  const path = pathname.replace("/api/wechat", "");

  try {
    const res = await fetch(`${UPSTREAM_URL}${path}?${searchParams.toString()}`, {
      cache: "no-store",
      headers: request.headers,
    });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error("API Proxy Error (GET /api/wechat):", error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  const { searchParams, pathname } = new URL(request.url);
  const path = pathname.replace("/api/wechat", "");

  try {
    let body: string | undefined;
    const contentType = request.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      try {
        const parsed = await request.json();
        body = JSON.stringify(parsed);
      } catch {
        // Empty body or invalid JSON — send no body
      }
    }

    const fetchInit: RequestInit = {
      method: "POST",
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
    };
    if (body) {
      fetchInit.body = body;
    }

    const res = await fetch(`${UPSTREAM_URL}${path}?${searchParams.toString()}`, fetchInit);
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error("API Proxy Error (POST /api/wechat):", error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}

export async function DELETE(request: Request) {
  const { searchParams, pathname } = new URL(request.url);
  const path = pathname.replace("/api/wechat", "");

  try {
    const res = await fetch(`${UPSTREAM_URL}${path}?${searchParams.toString()}`, {
      method: "DELETE",
      headers: request.headers,
    });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error("API Proxy Error (DELETE /api/wechat):", error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}
