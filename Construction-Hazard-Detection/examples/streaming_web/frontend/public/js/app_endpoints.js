const env = import.meta.env || {};
const runtime =
  typeof window !== 'undefined' && window.__CHD_RUNTIME_CONFIG__
    ? window.__CHD_RUNTIME_CONFIG__
    : {};

const DEFAULTS = {
  platformApiUrl: '/api/platform',
  streamingBackendApiUrl: '/api/streaming',
  violationApiUrl: '/api/violation',
  ticketUiUrl: 'http://127.0.0.1:7861/',
};

function asString(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function stripTrailingSlash(value) {
  return value.replace(/\/+$/, '');
}

function normaliseBaseUrl(value, fallback) {
  const picked = asString(value) || asString(fallback);
  if (!picked) {
    return '';
  }
  return stripTrailingSlash(picked);
}

function normaliseTicketUiUrl(value, fallback) {
  const picked = asString(value) || asString(fallback);
  if (!picked) {
    return '';
  }
  if (/^https?:\/\//i.test(picked)) {
    return `${stripTrailingSlash(picked)}/`;
  }
  if (picked.startsWith('/')) {
    return `${stripTrailingSlash(picked)}/`;
  }
  return `${stripTrailingSlash(`http://${picked}`)}/`;
}

export const ENDPOINTS = {
  platformApiUrl: normaliseBaseUrl(
    runtime.platformApiUrl || runtime.platform_api_url || env.VITE_PLATFORM_API_URL,
    DEFAULTS.platformApiUrl,
  ),
  streamingBackendApiUrl: normaliseBaseUrl(
    runtime.streamingBackendApiUrl ||
      runtime.streaming_backend_api_url ||
      env.VITE_STREAMING_BACKEND_API_URL,
    DEFAULTS.streamingBackendApiUrl,
  ),
  violationApiUrl: normaliseBaseUrl(
    runtime.violationApiUrl ||
      runtime.violation_api_url ||
      env.VITE_VIOLATION_API_URL,
    DEFAULTS.violationApiUrl,
  ),
  ticketUiUrl: normaliseTicketUiUrl(
    runtime.ticketUiUrl || runtime.ticket_ui_url || env.VITE_TICKET_UI_URL,
    DEFAULTS.ticketUiUrl,
  ),
};

export function buildApiUrl(baseUrl, path = '') {
  const base = normaliseBaseUrl(baseUrl, '');
  const suffix = path ? `/${String(path).replace(/^\/+/, '')}` : '';
  return `${base}${suffix}`;
}

function getWsOriginFromCurrentPage() {
  return window.location.protocol === 'https:'
    ? `wss://${window.location.host}`
    : `ws://${window.location.host}`;
}

function toWebSocketBase(baseUrl) {
  const base = normaliseBaseUrl(baseUrl, '');
  if (!base) {
    return getWsOriginFromCurrentPage();
  }
  if (/^wss?:\/\//i.test(base)) {
    return base;
  }
  if (/^https?:\/\//i.test(base)) {
    return base.replace(/^http/i, 'ws');
  }
  if (base.startsWith('/')) {
    return `${getWsOriginFromCurrentPage()}${base}`;
  }
  return `${getWsOriginFromCurrentPage()}/${base.replace(/^\/+/, '')}`;
}

export function buildStreamingWsUrl(path = '') {
  const wsBase = toWebSocketBase(ENDPOINTS.streamingBackendApiUrl);
  const suffix = path ? `/${String(path).replace(/^\/+/, '')}` : '';
  return `${wsBase}${suffix}`;
}
