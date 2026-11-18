import API_BASE_URL from '../config';

const ACCESS_KEY = 'stockbot_access_code';

export function getAccessCode() {
  try { return localStorage.getItem(ACCESS_KEY) || ''; } catch { return ''; }
}

export function setAccessCode(code) {
  try { localStorage.setItem(ACCESS_KEY, code); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function toApiError(response) {
  let code = 'error';
  let message = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === 'string') message = detail;
    else if (Array.isArray(detail)) message = detail[0]?.msg || message;
    else if (detail) { code = detail.code || code; message = detail.message || message; }
  } catch { /* non-JSON error */ }
  if (code === 'access_code_required') window.dispatchEvent(new Event('stockbot:access-required'));
  return new ApiError(response.status, code, message);
}

/** fetch() against the API. Throws ApiError for non-2xx responses. */
export async function apiFetch(path, options = {}) {
  const headers = { ...options.headers };
  const code = getAccessCode();
  if (code) headers['X-Access-Code'] = code;
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    options = { ...options, body: JSON.stringify(options.json) };
  }
  const response = await fetch(`${API_BASE_URL}/api${path}`, { ...options, headers });
  if (!response.ok) throw await toApiError(response);
  return response;
}

export async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  return response.json();
}
