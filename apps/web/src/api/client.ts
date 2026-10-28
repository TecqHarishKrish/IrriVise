/** Minimal typed HTTP client. Errors carry the API's {code, message, details, request_id} body. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown, public requestId?: string) {
    super(message);
  }
}

export const API_BASE = '/api/v1';

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the IrriVise API. Is the backend running on port 8000?');
  }
  if (!response.ok) {
    let body: { code?: string; message?: string; details?: unknown; request_id?: string } = {};
    try {
      body = await response.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(response.status, body.code ?? 'http_error', body.message ?? `Request failed (${response.status})`, body.details, body.request_id);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' });

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const details = Array.isArray(error.details)
      ? error.details.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ')
      : '';
    return details ? `${error.message} — ${details}` : error.message;
  }
  return error instanceof Error ? error.message : 'Unknown error';
}
