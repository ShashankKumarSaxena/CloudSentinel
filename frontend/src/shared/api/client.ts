export type * from './types';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

let csrfToken = '';
export function setSessionToken(token: string) {
  csrfToken = token;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken && options?.method && options.method !== 'GET'
          ? { 'X-CSRF-Token': csrfToken }
          : {}),
        ...options?.headers,
      },
      signal: options?.signal ?? AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error('Could not reach the workspace. Check your connection and try again.');
  }
  if (!response.ok) {
    if (response.status === 401 && csrfToken && path !== '/auth/login') {
      setSessionToken('');
      window.dispatchEvent(new Event('cloudsentinel-session-expired'));
    }
    const body = await response.json().catch(() => ({}));
    const fields = body.errors
      ?.map((e: { field: string; message: string }) => `${e.field}: ${e.message}`)
      .slice(0, 3)
      .join(' · ');
    throw new ApiError(
      `${typeof body.detail === 'string' ? body.detail : 'The request could not be completed.'}${
        fields ? ` ${fields}` : ''
      }${
        response.headers.get('X-Request-ID')
          ? ` Reference: ${response.headers.get('X-Request-ID')}`
          : ''
      }`,
      response.status,
    );
  }
  return response.json();
}

export async function downloadReport(scanId?: string) {
  const report = await request<unknown>(
    scanId ? `/export?scan_id=${encodeURIComponent(scanId)}` : '/export',
  );
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = 'cloudsentinel-report.json';
  link.click();
  URL.revokeObjectURL(url);
}
