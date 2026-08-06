/**
 * Central HTTP layer for the ActiveHome frontend.
 *
 * Every request to the backend goes through this module so that:
 *  - the base URL / `/api/v1` prefix is defined in exactly one place
 *  - cookies are always sent (`credentials: "include"`), which the backend
 *    session model (`ah_session` HttpOnly cookie, see contracts/openapi.yaml)
 *    requires
 *  - errors are normalised into the backend's Problem-style `Error` envelope
 *    (`type`, `title`, `status`, `code`, `traceId`, `details`)
 *
 * Do not call `fetch` directly elsewhere in the app — go through `http`.
 */

/** Raw origin the API is served from, e.g. http://localhost:8000 */
const API_ORIGIN = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000")
).replace(/\/+$/, "");

/** Every backend route is mounted under /api/v1 (see apps/backend/src/main.py). */
export const API_BASE_URL = `${API_ORIGIN}/api/v1`;

export interface ValidationErrorItem {
  path: string;
  rule: string;
  message: string;
}

/** Shape of the backend's Problem-style error envelope (`#/components/schemas/Error`). */
export interface ApiErrorBody {
  type?: string;
  title?: string;
  status: number;
  code?: string;
  detail?: string;
  instance?: string;
  traceId?: string;
  details?: ValidationErrorItem[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly traceId?: string;
  readonly details?: ValidationErrorItem[];

  constructor(body: ApiErrorBody) {
    super(body.detail || body.title || `Request failed with status ${body.status}`);
    this.name = "ApiError";
    this.status = body.status;
    this.code = body.code ?? "UNKNOWN_ERROR";
    this.traceId = body.traceId;
    this.details = body.details;
  }

  get isAuthError(): boolean {
    return (
      this.status === 401 ||
      this.code === "AUTHENTICATION_REQUIRED" ||
      this.code === "SESSION_EXPIRED"
    );
  }
}

export type QueryParams = Record<string, string | number | boolean | undefined | null | string[]>;

export function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(path.replace(/^\/+/, ""), `${API_BASE_URL}/`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, String(v)));
      } else {
        url.searchParams.append(key, String(value));
      }
    });
  }
  return url.toString();
}

function randomIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

interface RequestOptions {
  params?: QueryParams;
  headers?: Record<string, string>;
  /** Attach an `Idempotency-Key` header — required by the contract for some side-effecting POSTs. */
  idempotent?: boolean;
  signal?: AbortSignal;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined;
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (options.idempotent) headers["Idempotency-Key"] = randomIdempotencyKey();

  const response = await fetch(buildUrl(path, options.params), {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: options.signal,
  });

  const data = await parseBody(response);

  if (!response.ok) {
    const errorBody: ApiErrorBody =
      data && typeof data === "object"
        ? { status: response.status, ...(data as object) }
        : { status: response.status };
    throw new ApiError(errorBody);
  }

  return data as T;
}

export const http = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
};
