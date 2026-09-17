import type { ApiEnvelope } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "";

function describeNetworkError() {
  return "导览服务正在连接，请稍后重试。若持续出现，请重新运行一键启动脚本。";
}

function unwrapApiPayload<T>(payload: ApiEnvelope<T> | (T & { ok?: boolean; message?: string }), path: string): T {
  const maybeEnvelope = payload as ApiEnvelope<T>;
  if ("data" in maybeEnvelope) return maybeEnvelope.data;
  if (payload && typeof payload === "object" && "ok" in payload && payload.ok === false) {
    throw new Error(String(payload.message || `请求失败: ${path}`));
  }
  return payload as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" }).catch(() => {
    throw new Error(describeNetworkError());
  });
  const payload = (await response.json()) as ApiEnvelope<T> | (T & { ok?: boolean; message?: string });
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload.message || `请求失败: ${path}`);
  }
  return unwrapApiPayload<T>(payload, path);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  }).catch(() => {
    throw new Error(describeNetworkError());
  });
  const payload = (await response.json()) as ApiEnvelope<T> | (T & { ok?: boolean; message?: string });
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload.message || `请求失败: ${path}`);
  }
  return unwrapApiPayload<T>(payload, path);
}

export async function apiPostNdjson<T>(
  path: string,
  body: unknown,
  onEvent: (event: T) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify(body),
    signal
  }).catch((error: unknown) => {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error(describeNetworkError());
  });
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `请求失败: ${path}`);
  }
  if (!response.body) throw new Error("导览服务未返回可读取的回答流。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const consumeLine = (line: string) => {
    const value = line.trim();
    if (value) onEvent(JSON.parse(value) as T);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      lines.forEach(consumeLine);
      if (done) break;
    }
    consumeLine(buffer);
  } finally {
    reader.releaseLock();
  }
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).catch(() => {
    throw new Error(describeNetworkError());
  });
  const payload = (await response.json()) as ApiEnvelope<T> | (T & { ok?: boolean; message?: string });
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload.message || `请求失败: ${path}`);
  }
  return unwrapApiPayload<T>(payload, path);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE"
  }).catch(() => {
    throw new Error(describeNetworkError());
  });
  const payload = (await response.json()) as ApiEnvelope<T> | (T & { ok?: boolean; message?: string });
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload.message || `请求失败: ${path}`);
  }
  return unwrapApiPayload<T>(payload, path);
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData
  }).catch(() => {
    throw new Error(describeNetworkError());
  });
  const payload = (await response.json()) as ApiEnvelope<T> | (T & { ok?: boolean; message?: string });
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload.message || `请求失败: ${path}`);
  }
  return unwrapApiPayload<T>(payload, path);
}
