import { NextResponse } from "next/server";
import { proxyGet, safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/files";

export async function GET(request: Request) {
  return proxyGet(UPSTREAM_URL, request);
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const res = await fetch(UPSTREAM_URL, {
      method: "POST",
      body: formData,
    });
    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error("API Proxy Error (POST /api/files):", error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}
