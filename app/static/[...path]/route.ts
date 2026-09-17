import { NextRequest, NextResponse } from "next/server";
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function resolveBackendUrl() {
  const configured = process.env.BACKEND_INTERNAL_URL?.trim() || process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  try {
    const runtime = JSON.parse(readFileSync(join(process.cwd(), "backend", "storage", "runtime-ports.json"), "utf-8"));
    if (runtime.api_base) return String(runtime.api_base).replace(/\/$/, "");
    if (runtime.backend_port) return `http://127.0.0.1:${runtime.backend_port}`;
  } catch {
    // Fall through to the default local FastAPI port.
  }
  return "http://127.0.0.1:8000";
}

export async function GET(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  const target = new URL(`${resolveBackendUrl()}/static/${params.path.join("/")}`);
  target.search = request.nextUrl.search;

  try {
    const upstream = await fetch(target, { cache: "no-store" });
    const headers = new Headers(upstream.headers);
    headers.delete("content-encoding");
    headers.delete("content-length");
    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers
    });
  } catch {
    return NextResponse.json({ ok: false, message: "语音资源暂时不可用" }, { status: 503 });
  }
}
