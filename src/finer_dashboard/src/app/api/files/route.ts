import { NextResponse } from "next/server";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/files";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const tier = searchParams.get("tier") || "F1";
  
  try {
    const res = await fetch(`${UPSTREAM_URL}?tier=${tier}`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("API Proxy Error (GET /api/files):", error);
    return NextResponse.json({ error: "Failed to connect to API backend" }, { status: 502 });
  }
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const res = await fetch(UPSTREAM_URL, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("API Proxy Error (POST /api/files):", error);
    return NextResponse.json({ error: "Failed to connect to API backend" }, { status: 502 });
  }
}
