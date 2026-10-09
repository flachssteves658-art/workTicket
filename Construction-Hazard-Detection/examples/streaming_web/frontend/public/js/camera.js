import { buildStreamingWsUrl } from './app_endpoints.js';

/* ----------------------------------
   Constants
------------------------------------- */
// A list of supported "no warnings" messages in various languages
const NO_WARNINGS_MESSAGES = [
  'No warning',             // English
  '無警告',                  // Traditional Chinese
  '无警告',                  // Simplified Chinese
  "Pas d'avertissement",    // French
  'Không có cảnh báo',       // Vietnamese
  'Tidak ada peringatan',    // Indonesian
  'ไม่มีคำเตือน'             // Thai
];

const delimiterBytes = new TextEncoder().encode('--IMG--');
const headerDecoder = new TextDecoder('utf-8');
const WARNINGS_TEXTS = {
  warning_people_in_controlled_area: '警告: 有{count}个人进入受控区域!',
  warning_no_hardhat: '警告: 有{count}人未佩戴安全帽!',
  warning_no_safety_vest: '警告: 有{count}人未穿着安全背心!',
  warning_close_to_machinery: '警告: 有{count}人过于靠近机具!',
  warning_close_to_vehicle: '警告: 有{count}人过于靠近车辆!',
  warning_people_in_utility_pole_controlled_area:
    '警告: 有{count}人进入电杆管制区!',
  detect_machinery_close_to_pole:
    '警告: 有{count}个机具过于靠近电杆!',
  no_warning: '没有警告信息',
};

const WARNING_RISK_LEVELS = {
  high: { label: '高危', className: 'level-high' },
  medium: { label: '中危', className: 'level-medium' },
  low: { label: '低危', className: 'level-low' },
  info: { label: '提示', className: 'level-info' },
};

const WARNING_RISK_BY_KEY = {
  warning_close_to_machinery: 'high',
  warning_close_to_vehicle: 'high',
  detect_machinery_close_to_pole: 'high',
  warning_people_in_controlled_area: 'high',
  warning_people_in_utility_pole_controlled_area: 'high',
  warning_no_hardhat: 'medium',
  warning_no_safety_vest: 'medium',
};

/* ----------------------------------
 Global Variables & Element Selectors
------------------------------------- */
// WebSocket connection instance
let socket;
let latestFrameMeta = null;
let heartbeatIntervalId = 0;
let pullIntervalId = 0;
let overlayRafId = 0;
let currentStreamObjectUrl = '';
let lastWarningsFingerprint = '';

const CLASS_LABELS = {
  0: 'Hardhat',
  1: 'Mask',
  2: 'NO-Hardhat',
  3: 'NO-Mask',
  4: 'NO-Vest',
  5: 'Person',
  6: 'Cone',
  7: 'Safety Vest',
  8: 'Machinery',
  // 9: 'Pole',
  10: 'Vehicle',
};

const CLASS_COLORS = {
  0: '#22c55e',
  1: '#22c55e',
  2: '#ef4444',
  3: '#ef4444',
  4: '#f97316',
  5: '#22c55e',
  6: '#eab308',
  7: '#3b82f6',
  8: '#3b82f6',
  // 9: '#a855f7',
  10: '#06b6d4',
  default: '#ffffff',
};

/* ----------------------------------
 Utility Functions
------------------------------------- */
/**
* Custom logging function to avoid direct console usage
*
* @param {string} message - The message to log.
*/
function logInformation(message) {
  // For production, consider removing or sending to a logging service
  // console.log(`[INFO] ${message}`);
}

/**
* Custom error logging function to avoid direct console usage
*
* @param {string} message - The error message to log.
*/
function logError(message) {
  // For production, consider removing or sending to an error tracking service
  // console.error(`[ERROR] ${message}`);
}

/* ----------------------------------
 Initialization
------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  initialisePage();
  setupUnloadHandler();
});

/**
* Initialise the page by validating parameters and setting up WebSocket.
*/
function initialisePage() {
  const { label, key } = getURLParameters();

  // Redirect to index page if either label or key is missing
  if (!label || !key) {
      logError('Label or key parameter is missing');
      redirectToIndex();
      return;
  }

  const domReferences = getDOMReferences();
  setCameraTitle(domReferences.cameraTitle, label, key);
  setupOverlay(domReferences);
  initialiseWebSocket({ label, key, domReferences });
}

/**
* Retrieve and validate URL parameters.
*
* @returns {Object} An object containing label and key.
*/
function getURLParameters() {
  const urlParameters = new URLSearchParams(window.location.search);
  const label = urlParameters.get('label');
  const key = urlParameters.get('key');
  return { label, key };
}

/**
* Retrieve necessary DOM elements for dynamic updates.
*
* @returns {Object} An object containing DOM references.
*/
function getDOMReferences() {
  return {
      cameraTitle: document.getElementById('camera-title'),
      streamImage: document.getElementById('stream-image'),
      overlayCanvas: document.getElementById('stream-overlay'),
      loadingIndicator: document.getElementById('loading-indicator'),
      streamMeta: document.getElementById('stream-meta'),
      warningsContainer: document.getElementById('warnings-list'),
      warningsList: document.getElementById('warnings-ul'),
  };
}

/**
* Set the camera title to include the label and key.
*
* @param {HTMLElement} cameraTitle - The DOM element for camera title.
* @param {string} label - The label parameter.
* @param {string} key - The key parameter.
*/
function setCameraTitle(cameraTitle, label, key) {
  cameraTitle.textContent = `${label} - ${key}`;
}

/**
* Ensure the WebSocket is properly closed when the page is unloaded.
*/
function setupUnloadHandler() {
  window.addEventListener('beforeunload', () => {
      closeWebSocket();
  });
}

/**
* Redirect the user to the index page.
*/
function redirectToIndex() {
  window.location.href = 'index.html';
}

/* ----------------------------------
 WebSocket Handling
------------------------------------- */
/**
* Initialise WebSocket with an object parameter.
*
* @param {Object} params - The parameters for WebSocket initialization.
* @param {string} params.label - The label used to establish the WebSocket connection.
* @param {string} params.key - The key used to establish the WebSocket connection.
* @param {Object} params.domReferences - The DOM elements to update based on WebSocket messages.
*/
function initialiseWebSocket({ label, key, domReferences }) {
  const token = getAccessTokenFromStorage();
  let webSocketUrl = buildStreamingWsUrl(
    `/ws/stream/${encodeURIComponent(label)}/${encodeURIComponent(key)}`,
  );
  if (token) {
      webSocketUrl += `?token=${encodeURIComponent(token)}`;
  }

  // Create a new WebSocket connection
  socket = new WebSocket(webSocketUrl);
  socket.binaryType = 'arraybuffer';

  // Define WebSocket event handlers
  socket.onopen = handleWebSocketOpen;
  socket.onmessage = (event) => handleWebSocketMessage(event, domReferences);
  socket.onerror = handleWebSocketError;
  socket.onclose = handleWebSocketClose;
}

/**
* Handle WebSocket connection establishment.
*/
function handleWebSocketOpen() {
  logInformation('WebSocket connected!');
  setupWebSocketHeartbeat();
  startPullLoop();
}

/**
* Set up a heartbeat mechanism to keep the WebSocket connection alive.
*/
function setupWebSocketHeartbeat() {
  if (heartbeatIntervalId) {
      clearInterval(heartbeatIntervalId);
  }
  heartbeatIntervalId = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ action: 'ping' }));
      }
  }, 30000); // 30 seconds
}

function startPullLoop() {
  if (pullIntervalId) {
      clearInterval(pullIntervalId);
  }
  pullIntervalId = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ action: 'pull' }));
      }
  }, 1000);
}

/**
* Handle incoming WebSocket messages.
*
* @param {MessageEvent} event - The WebSocket message event.
* @param {Object} domReferences - The DOM elements to update.
*/
function handleWebSocketMessage(event, domReferences) {
  const data = event.data;
  if (typeof data === 'string') {
      handleTextMessage(data, domReferences);
      return;
  }
  if (data instanceof ArrayBuffer) {
      handleBinaryFrame(data, domReferences);
      return;
  }
  if (data instanceof Blob) {
      data.arrayBuffer().then((buffer) => handleBinaryFrame(buffer, domReferences));
  }
}

function handleTextMessage(text, domReferences) {
  try {
      const obj = JSON.parse(text);
      if (obj && obj.error) {
          handleServerError(obj.error);
      }
  } catch {
  }
}

function handleBinaryFrame(buffer, domReferences) {
  const bytes = new Uint8Array(buffer);
  const index = findDelimiterIndex(bytes, delimiterBytes);
  if (index === -1) {
      return;
  }
  const headerBytes = bytes.slice(0, index);
  const imageBytes = bytes.slice(index + delimiterBytes.length);
  let header;
  try {
      header = JSON.parse(headerDecoder.decode(headerBytes));
  } catch {
      logError('Failed to parse header JSON');
      return;
  }
  const warningsData = header.warnings || '';
  latestFrameMeta = normaliseFrameMeta(header);
  const blob = new Blob([imageBytes], { type: 'image/jpeg' });
  const objectUrl = URL.createObjectURL(blob);
  updateStreamImage({
    streamImage: domReferences.streamImage,
    loadingIndicator: domReferences.loadingIndicator,
    streamMeta: domReferences.streamMeta,
    imageUrl: objectUrl,
  });
  const warningsFingerprint =
    typeof warningsData === 'string' ? warningsData : JSON.stringify(warningsData ?? null);
  if (warningsFingerprint !== lastWarningsFingerprint) {
    lastWarningsFingerprint = warningsFingerprint;
    updateWarningsList(
      domReferences.warningsContainer,
      domReferences.warningsList,
      warningsData,
    );
  }
  scheduleOverlayRender(domReferences);
}

function findDelimiterIndex(bytes, delimiter) {
  for (let i = 0; i <= bytes.length - delimiter.length; i += 1) {
      let match = true;
      for (let j = 0; j < delimiter.length; j += 1) {
          if (bytes[i + j] !== delimiter[j]) {
              match = false;
              break;
          }
      }
      if (match) {
          return i;
      }
  }
  return -1;
}

/**
* Process the data received from the WebSocket.
*
* @param {Object} data - The data received from the WebSocket server.
* @param {Object} domReferences - The DOM elements to update.
*/
function processWebSocketData(data, domReferences) {
  if (data.error) {
      handleServerError(data.error);
      return;
  }

  if (data.image) {
      updateStreamImage({ ...domReferences, imageData: data.image });
  }

  if (data.warnings) {
      updateWarningsList(
        domReferences.warningsContainer,
        domReferences.warningsList,
        data.warnings,
      );
  }
}

/**
* Handle error messages from the server.
*
* @param {string} errorMessage - The error message from the server.
*/
function handleServerError(errorMessage) {
  logError(errorMessage);
  closeWebSocket();
  redirectToIndex();
}

/**
* Handle WebSocket errors.
*
* @param {Event} error - The WebSocket error event.
*/
function handleWebSocketError(error) {
  logError(`WebSocket error: ${error}`);
  closeWebSocket();
  redirectToIndex();
}

/**
* Handle WebSocket closure.
*/
function handleWebSocketClose() {
  logInformation('WebSocket closed');
  clearIntervals();
}

function clearIntervals() {
  if (heartbeatIntervalId) {
    clearInterval(heartbeatIntervalId);
    heartbeatIntervalId = 0;
  }
  if (pullIntervalId) {
    clearInterval(pullIntervalId);
    pullIntervalId = 0;
  }
}

function revokeStreamObjectUrl() {
  if (currentStreamObjectUrl) {
    URL.revokeObjectURL(currentStreamObjectUrl);
    currentStreamObjectUrl = '';
  }
}

/**
* Close the WebSocket connection gracefully.
*/
function closeWebSocket() {
  clearIntervals();
  revokeStreamObjectUrl();
  if (overlayRafId) {
    cancelAnimationFrame(overlayRafId);
    overlayRafId = 0;
  }
  if (socket) {
      socket.close();
  }
}

/* ----------------------------------
 DOM Updates
------------------------------------- */
/**
* Update the live stream image.
*
* @param {Object} params - Parameters for updating the stream image.
* @param {HTMLElement} params.streamImage - The image element to update.
* @param {HTMLElement} params.loadingIndicator - The loading indicator element.
* @param {HTMLElement} params.streamMeta - The metadata element to update.
* @param {string} params.imageData - The base64-encoded image data.
*/
function updateStreamImage({ streamImage, loadingIndicator, streamMeta, imageUrl }) {
  // Hide the loading indicator and display the live stream image
  loadingIndicator.style.display = 'none';
  streamImage.style.display = 'block';

  // Set the image source to the received base64 data
  if (currentStreamObjectUrl) {
    URL.revokeObjectURL(currentStreamObjectUrl);
  }
  currentStreamObjectUrl = imageUrl;
  streamImage.src = imageUrl;

  // Update the metadata with the current timestamp
  streamMeta.textContent = `Last updated: ${new Date().toLocaleString()}`;
}

function setupOverlay(domReferences) {
  const { streamImage, overlayCanvas } = domReferences;
  if (!streamImage || !overlayCanvas) {
    return;
  }
  streamImage.addEventListener('load', () => {
    scheduleOverlayRender(domReferences);
  });
  window.addEventListener('resize', () => {
    scheduleOverlayRender(domReferences);
  });
}

function scheduleOverlayRender(domReferences) {
  if (overlayRafId) {
    return;
  }
  overlayRafId = requestAnimationFrame(() => {
    overlayRafId = 0;
    renderOverlay(domReferences);
  });
}

function normaliseFrameMeta(header) {
  const width = Number(header && header.width) || 0;
  const height = Number(header && header.height) || 0;
  const conePolygons = parseJsonValue(header && header.cone_polygons);
  const polePolygons = parseJsonValue(header && header.pole_polygons);
  const detectionItems = parseJsonValue(header && header.detection_items);
  return {
    width,
    height,
    conePolygons: Array.isArray(conePolygons) ? conePolygons : [],
    polePolygons: Array.isArray(polePolygons) ? polePolygons : [],
    detectionItems: Array.isArray(detectionItems) ? detectionItems : [],
  };
}

function parseJsonValue(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    try {
      return JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  if (value && typeof value === 'object') {
    return value;
  }
  return null;
}

function renderOverlay(domReferences) {
  const { streamImage, overlayCanvas } = domReferences;
  if (!streamImage || !overlayCanvas || !latestFrameMeta) {
    return;
  }
  const rect = streamImage.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  overlayCanvas.width = Math.max(1, Math.round(rect.width * dpr));
  overlayCanvas.height = Math.max(1, Math.round(rect.height * dpr));
  const ctx = overlayCanvas.getContext('2d');
  if (!ctx) {
    return;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const srcW = latestFrameMeta.width || streamImage.naturalWidth || rect.width;
  const srcH = latestFrameMeta.height || streamImage.naturalHeight || rect.height;
  const scaleX = rect.width / srcW;
  const scaleY = rect.height / srcH;

  drawDetections(ctx, latestFrameMeta.detectionItems, scaleX, scaleY);
  drawPolygons(ctx, latestFrameMeta.conePolygons, scaleX, scaleY, '#f59e0b');
  drawPolygons(ctx, latestFrameMeta.polePolygons, scaleX, scaleY, '#a855f7');
}

function drawPolygons(ctx, polygons, scaleX, scaleY, strokeColor) {
  if (!Array.isArray(polygons) || polygons.length === 0) {
    return;
  }
  ctx.lineWidth = 2;
  ctx.strokeStyle = strokeColor;
  ctx.fillStyle = withAlpha(strokeColor, 0.15);
  polygons.forEach((polygon) => {
    if (!Array.isArray(polygon) || polygon.length < 2) {
      return;
    }
    ctx.beginPath();
    polygon.forEach((pt, index) => {
      if (!Array.isArray(pt) || pt.length < 2) {
        return;
      }
      const x = Number(pt[0]) * scaleX;
      const y = Number(pt[1]) * scaleY;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  });
}

function drawDetections(ctx, detectionItems, scaleX, scaleY) {
  if (!Array.isArray(detectionItems) || detectionItems.length === 0) {
    return;
  }
  ctx.lineWidth = 2;
  ctx.font = '12px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
  ctx.textBaseline = 'top';
  detectionItems.forEach((item) => {
    if (!Array.isArray(item) || item.length < 6) {
      return;
    }
    const x1 = Number(item[0]) * scaleX;
    const y1 = Number(item[1]) * scaleY;
    const x2 = Number(item[2]) * scaleX;
    const y2 = Number(item[3]) * scaleY;
    const conf = Number(item[4]);
    const cls = Number(item[5]);
    if (![x1, y1, x2, y2].every((v) => Number.isFinite(v))) {
      return;
    }
    const color = CLASS_COLORS[cls] || CLASS_COLORS.default;
    ctx.strokeStyle = color;
    ctx.fillStyle = withAlpha(color, 0.15);
    const w = x2 - x1;
    const h = y2 - y1;
    ctx.fillRect(x1, y1, w, h);
    ctx.strokeRect(x1, y1, w, h);

    const label = CLASS_LABELS[cls] || `Class ${cls}`;
    const confText = Number.isFinite(conf) ? ` ${(conf * 100).toFixed(0)}%` : '';
    const text = `${label}${confText}`;
    const padX = 6;
    const padY = 4;
    const metrics = ctx.measureText(text);
    const textW = metrics.width;
    const textH = 12;
    const bgX = x1;
    const bgY = Math.max(0, y1 - (textH + padY * 2));
    ctx.fillStyle = withAlpha('#111827', 0.75);
    ctx.fillRect(bgX, bgY, textW + padX * 2, textH + padY * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, bgX + padX, bgY + padY);
  });
}

function withAlpha(hexColor, alpha) {
  const v = String(hexColor || '').trim();
  if (!v.startsWith('#') || (v.length !== 7 && v.length !== 4)) {
    return `rgba(0,0,0,${alpha})`;
  }
  if (v.length === 4) {
    const r = parseInt(v[1] + v[1], 16);
    const g = parseInt(v[2] + v[2], 16);
    const b = parseInt(v[3] + v[3], 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  const r = parseInt(v.slice(1, 3), 16);
  const g = parseInt(v.slice(3, 5), 16);
  const b = parseInt(v.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
* Update the warnings list.
*
* @param {HTMLElement} warningsContainer - The container element for warnings.
* @param {HTMLElement} warningsList - The unordered list element to update.
* @param {string} warningsData - The warnings data as a newline-separated string.
*/
function updateWarningsList(
  warningsContainer,
  warningsList,
  warningsData,
) {
  warningsList.innerHTML = '';
  let parsed = null;
  if (typeof warningsData === 'string' && warningsData.trim() !== '') {
    try {
      parsed = JSON.parse(warningsData);
    } catch {
    }
  } else if (
    warningsData &&
    typeof warningsData === 'object' &&
    !Array.isArray(warningsData)
  ) {
    parsed = warningsData;
  }
  const messages = [];
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const entries = Object.entries(parsed);
    for (const [key, value] of entries) {
      const count =
        value && typeof value === 'object'
          ? Number(value.count) || 0
          : 0;
      if (count === 0) {
        continue;
      }
      const template = WARNINGS_TEXTS[key];
      const level = inferWarningRiskLevel({ key });
      if (template) {
        messages.push({
          key,
          text: template.replace('{count}', String(count)),
          level,
        });
      } else {
        messages.push({
          key,
          text: `${key}: ${count}`,
          level,
        });
      }
    }
  } else if (typeof warningsData === 'string') {
    const parts = warningsData
      .split('\n')
      .map((v) => v.trim())
      .filter((v) => v !== '');
    parts.forEach((text) => {
      messages.push({
        key: '',
        text,
        level: inferWarningRiskLevel({ text }),
      });
    });
  }
  if (messages.length === 0) {
    messages.push({
      key: 'no_warning',
      text: WARNINGS_TEXTS.no_warning,
      level: 'info',
    });
  }
  if (messages.length === 1 && messages[0].text === WARNINGS_TEXTS.no_warning) {
    warningsContainer.className = 'no-warnings';
    appendWarningItem(warningsList, messages[0], ['no-warning']);
  } else {
    warningsContainer.className = 'warnings';
    messages.forEach((warning) => appendWarningItem(warningsList, warning));
  }
}

/**
* Append a single warning to the list.
*
* @param {HTMLElement} warningsList - The unordered list element.
* @param {string} warningText - The warning text to append.
* @param {Array} additionalClasses - Additional CSS classes to add to the warning item.
*/
function appendWarningItem(warningsList, warning, additionalClasses = []) {
  const paragraph = document.createElement('p');
  const text = warning && typeof warning === 'object' ? warning.text : String(warning || '');
  const level = warning && typeof warning === 'object' ? String(warning.level || '') : '';
  paragraph.classList.add('warning-item', ...additionalClasses);
  const risk = WARNING_RISK_LEVELS[level];
  if (risk && !additionalClasses.includes('no-warning')) {
    paragraph.classList.add(risk.className);
    const badge = document.createElement('span');
    badge.className = 'warning-badge';
    badge.textContent = risk.label;
    const content = document.createElement('span');
    content.className = 'warning-text';
    content.textContent = text;
    paragraph.appendChild(badge);
    paragraph.appendChild(content);
  } else {
    paragraph.textContent = text;
  }
  warningsList.appendChild(paragraph);
}

function inferWarningRiskLevel({ key, text } = {}) {
  const normalisedKey = typeof key === 'string' ? key.trim() : '';
  if (normalisedKey && WARNING_RISK_BY_KEY[normalisedKey]) {
    return WARNING_RISK_BY_KEY[normalisedKey];
  }
  const v = typeof text === 'string' ? text : '';
  if (!v) {
    return 'info';
  }
  if (v.includes('靠近机具') || v.includes('靠近车辆') || v.includes('机具过于靠近')) {
    return 'high';
  }
  if (v.includes('未佩戴安全帽') || v.includes('未穿着安全背心') || v.includes('未穿着安全背心')) {
    return 'medium';
  }
  if ((v.includes('进入') && v.includes('受控区域')) || (v.includes('进入') && v.includes('管制区')) || v.includes('闯入')) {
    return 'high';
  }
  return 'info';
}

function getAccessTokenFromStorage() {
  try {
      const raw = localStorage.getItem('chd_tokens');
      if (!raw) return '';
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.accessToken === 'string') {
          return parsed.accessToken;
      }
  } catch {
  }
  return '';
}
