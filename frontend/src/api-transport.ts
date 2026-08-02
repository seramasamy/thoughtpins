/** How a request is actually made.
 *
 * Sending, parsing the error envelope, refreshing an expired session and
 * retrying once, and reading binary responses. Split out of api.ts, which had
 * grown past its size budget: this is one concern and naming the routes is
 * another. Everything here is re-exported from ./api so no caller changes.
 */

import type { ApiErrorBody, TokenResponse } from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string;

  constructor(message: string, status: number, code = "request_failed", requestId = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export type ApiSession = {
  accessToken: string;
  refreshToken: string;
};

type SessionAccess = {
  get: () => ApiSession | null;
  set: (session: ApiSession | null) => void;
};

let sessionAccess: SessionAccess | null = null;

export function configureApiSession(access: SessionAccess | null) {
  sessionAccess = access;
}

type RequestOptions = {
  token?: string | null;
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  skipAuthRefresh?: boolean;
  idempotencyKey?: string;
};

async function send(path: string, options: RequestOptions, token: string | null) {
  const requestId = crypto.randomUUID();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Request-ID": requestId,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
    return { requestId, response };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      "Thought Pins is temporarily unreachable. The service may be restarting or in maintenance.",
      0,
      "network_unavailable",
      requestId,
    );
  }
}

async function parseResponse<T>(response: Response, requestId: string): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = {};
    }
    const error = body.error;
    throw new ApiError(
      error?.message || response.statusText || "Request failed",
      response.status,
      error?.code || "request_failed",
      error?.request_id || response.headers.get("X-Request-ID") || requestId,
    );
  }

  return (await response.json()) as T;
}

async function refreshSession(): Promise<ApiSession | null> {
  const current = sessionAccess?.get();
  if (!current?.refreshToken) {
    return null;
  }
  const tokens = await request<TokenResponse>("/v1/auth/refresh", {
    method: "POST",
    token: null,
    skipAuthRefresh: true,
    body: { refresh_token: current.refreshToken },
  });
  const next = { accessToken: tokens.access_token, refreshToken: tokens.refresh_token };
  sessionAccess?.set(next);
  return next;
}

export async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    };
    reader.readAsDataURL(blob);
  });
}

export async function sha256Hex(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const prepared = {
    ...options,
    idempotencyKey:
      options.idempotencyKey || (["POST", "PUT", "PATCH", "DELETE"].includes(method) ? crypto.randomUUID() : undefined),
  };
  let token = prepared.token !== undefined ? prepared.token : sessionAccess?.get()?.accessToken || null;
  let attempt = await send(path, prepared, token);

  if (attempt.response.status === 401 && !prepared.skipAuthRefresh) {
    try {
      const refreshed = await refreshSession();
      if (refreshed?.accessToken) {
        token = refreshed.accessToken;
        attempt = await send(path, prepared, token);
      }
    } catch {
      sessionAccess?.set(null);
    }
  }

  return parseResponse<T>(attempt.response, attempt.requestId);
}

export async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  let token = options.token !== undefined ? options.token : sessionAccess?.get()?.accessToken || null;
  let attempt = await send(path, options, token);

  if (attempt.response.status === 401 && !options.skipAuthRefresh) {
    try {
      const refreshed = await refreshSession();
      if (refreshed?.accessToken) {
        token = refreshed.accessToken;
        attempt = await send(path, options, token);
      }
    } catch {
      sessionAccess?.set(null);
    }
  }
  if (!attempt.response.ok) {
    await parseResponse<never>(attempt.response, attempt.requestId);
    throw new ApiError("Request failed", attempt.response.status, "request_failed", attempt.requestId);
  }
  return attempt.response.blob();
}
