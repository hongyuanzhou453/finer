import { NextResponse } from "next/server";
import { safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/opinions";

export async function GET(request: Request) {
  const { searchParams, pathname } = new URL(request.url);

  const path = pathname.replace("/api/opinions", "");
  const queryString = searchParams.toString();
  const targetUrl = `${UPSTREAM_URL}${path}${queryString ? `?${queryString}` : ""}`;

  try {
    const res = await fetch(targetUrl, {
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
    });

    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error(`API Proxy Error (GET ${targetUrl}):`, error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  const { pathname } = new URL(request.url);
  const path = pathname.replace("/api/opinions", "");
  const targetUrl = `${UPSTREAM_URL}${path}`;

  try {
    const body = await request.text();

    const res = await fetch(targetUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error(`API Proxy Error (POST ${targetUrl}):`, error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}
