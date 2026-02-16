const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8080";
const DEFAULT_TIMEOUT = 60_000;

export class BackendError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "BackendError";
  }
}

export async function fetchFromBackend(
  path: string,
  options?: RequestInit & { timeout?: number }
): Promise<Response> {
  const { timeout = DEFAULT_TIMEOUT, ...fetchOptions } = options || {};
  const url = `${BACKEND_URL}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions?.headers,
      },
    });
    return response;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchJSON<T>(
  path: string,
  options?: RequestInit & { timeout?: number }
): Promise<T> {
  const response = await fetchFromBackend(path, options);
  if (!response.ok) {
    let detail = `Backend returned ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || body.error || detail;
    } catch {
      detail = await response.text().catch(() => detail);
    }
    throw new BackendError(response.status, detail);
  }
  return response.json() as Promise<T>;
}
