import { NextResponse } from "next/server";
import { safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_BASE = "http://127.0.0.1:8000/api/sources";

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const proxyPath = path.join("/");
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();

  try {
    const res = await fetch(`${UPSTREAM_BASE}/${proxyPath}${query ? `?${query}` : ''}`, { cache: "no-store" });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch {
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Upstream connection failed" } },
      { status: 502 },
    );
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const proxyPath = path.join("/");
  try {
    const body = await request.text();
    const res = await fetch(`${UPSTREAM_BASE}/${proxyPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch {
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Upstream connection failed" } },
      { status: 502 },
    );
  }
}
