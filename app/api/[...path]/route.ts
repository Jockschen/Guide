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

async function proxy(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  const target = new URL(`${resolveBackendUrl()}/api/${params.path.join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const key of ["accept", "authorization", "content-type", "user-agent"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : Buffer.from(await request.arrayBuffer());

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store"
    });
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");
    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        message: "导览服务正在启动，请稍后刷新；若仍无法连接，请重新运行一键启动脚本。"
      },
      { status: 503 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
