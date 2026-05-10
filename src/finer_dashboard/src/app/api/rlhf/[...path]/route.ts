import { NextResponse } from "next/server";
import { safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_BASE = "http://127.0.0.1:8000/api/rlhf";

async function proxyRequest(
  request: Request,
  method: string,
  path: string[],
): Promise<NextResponse> {
  const proxyPath = path.join("/");
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();
  const url = `${UPSTREAM_BASE}/${proxyPath}${query ? `?${query}` : ""}`;

  const fetchInit: RequestInit = {
    method,
    cache: "no-store",
  };

  if (method === "POST" || method === "PUT") {
    const body = await request.text();
    if (body) {
      fetchInit.body = body;
      fetchInit.headers = { "Content-Type": "application/json" };
    }
  }

  try {
    const res = await fetch(url, fetchInit);
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error(`API Proxy Error (${method} /api/rlhf/${proxyPath}):`, error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, "GET", path);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, "POST", path);
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, "PUT", path);
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, "DELETE", path);
}
