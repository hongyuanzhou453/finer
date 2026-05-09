import { proxyGet } from "@/lib/api-proxy";

const UPSTREAM_URL = "http://127.0.0.1:8000/api/stats";

export async function GET(request: Request) {
  return proxyGet(UPSTREAM_URL, request);
}
