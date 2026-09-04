/**
 * AEGIS API Client Module
 * Base URL from environment, typed fetch wrapper, normalized error shape.
 */

export interface ApiErrorShape {
  status: number;
  message: string;
  code?: string;
  details?: unknown;
  raw?: unknown;
}

export class ApiError extends Error implements ApiErrorShape {
  status: number;
  code?: string;
  details?: unknown;
  raw?: unknown;

  constructor(status: number, message: string, code?: string, details?: unknown, raw?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code || (status === 0 ? 'NETWORK_ERROR' : `HTTP_${status}`);
    this.details = details;
    this.raw = raw;
  }
}

export const getBaseUrl = (): string => {
  if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '').replace('//localhost:', '//127.0.0.1:');
  }
  return '';
};

const resolveUrl = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  const base = getBaseUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
};

const getErrorCode = (status: number): string => {
  switch (status) {
    case 400:
      return 'BAD_REQUEST';
    case 401:
      return 'UNAUTHORIZED';
    case 403:
      return 'FORBIDDEN';
    case 404:
      return 'NOT_FOUND';
    case 409:
      return 'CONFLICT';
    case 422:
      return 'VALIDATION_ERROR';
    case 500:
      return 'INTERNAL_SERVER_ERROR';
    case 502:
      return 'BAD_GATEWAY';
    case 503:
      return 'SERVICE_UNAVAILABLE';
    default:
      return `HTTP_${status}`;
  }
};

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = resolveUrl(path);
  const headers = new Headers(options.headers || {});

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : 'Network request failed';
    throw new ApiError(
      0,
      `Unable to connect to server: ${errorMsg}`,
      'NETWORK_ERROR',
      undefined,
      err
    );
  }

  if (!response.ok) {
    let parsedBody: unknown = undefined;
    let errorMessage = `Request failed with status ${response.status} (${response.statusText || 'Error'})`;

    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        parsedBody = await response.json();
        if (typeof parsedBody === 'object' && parsedBody !== null) {
          const bodyObj = parsedBody as Record<string, unknown>;
          if (typeof bodyObj.detail === 'string') {
            errorMessage = bodyObj.detail;
          } else if (Array.isArray(bodyObj.detail)) {
            // FastAPI validation errors
            errorMessage = bodyObj.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
          } else if (typeof bodyObj.message === 'string') {
            errorMessage = bodyObj.message;
          } else if (typeof bodyObj.error === 'string') {
            errorMessage = bodyObj.error;
          }
        }
      } else {
        const text = await response.text();
        if (text) {
          errorMessage = text;
        }
      }
    } catch {
      // Ignore JSON parse errors on error bodies
    }

    throw new ApiError(
      response.status,
      errorMessage,
      getErrorCode(response.status),
      parsedBody,
      response
    );
  }

  if (response.status === 204) {
    return null as T;
  }

  try {
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return (await response.json()) as T;
    }
    return (await response.text()) as unknown as T;
  } catch (err: unknown) {
    throw new ApiError(
      response.status,
      'Failed to parse server response as JSON',
      'PARSE_ERROR',
      undefined,
      err
    );
  }
}

export const apiClient = {
  get: <T>(path: string, options?: RequestInit): Promise<T> =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> =>
    request<T>(path, {
      ...options,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),

  put: <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> =>
    request<T>(path, {
      ...options,
      method: 'PUT',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),

  patch: <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> =>
    request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),

  delete: <T>(path: string, options?: RequestInit): Promise<T> =>
    request<T>(path, { ...options, method: 'DELETE' }),
};
