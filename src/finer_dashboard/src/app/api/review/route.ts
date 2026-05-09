import { NextResponse } from "next/server";
import { safeJsonResponse } from "@/lib/api-proxy";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/review";

export async function POST(request: Request) {
  try {
    const body = await request.text();

    const res = await fetch(UPSTREAM_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    const { data, status } = await safeJsonResponse(res);
    return NextResponse.json(data, { status });
  } catch (error) {
    console.error("API Proxy Error (POST /api/review):", error);
    return NextResponse.json(
      { ok: false, error: { code: "PROXY_ERROR", message: "Failed to connect to API backend" } },
      { status: 502 },
    );
  }
}
