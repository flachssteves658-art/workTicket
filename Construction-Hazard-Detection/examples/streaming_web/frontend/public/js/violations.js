import { ENDPOINTS, buildApiUrl } from './app_endpoints.js';

const WARNINGS_TEXTS = {
  warning_people_in_controlled_area: '警告: 有{count}个人进入受控区域!',
  warning_no_hardhat: '警告: 有{count}人未佩戴安全帽!',
  warning_no_safety_vest: '警告: 有{count}人未穿着安全背心!',
  warning_close_to_machinery: '警告: 有{count}人过于靠近机具!',
  warning_close_to_vehicle: '警告: 有{count}人过于靠近车辆!',
  warning_people_in_utility_pole_controlled_area: '警告: 有{count}人进入电杆管制区!',
  detect_machinery_close_to_pole: '警告: 有{count}个机具过于靠近电杆!',
  no_warning: '没有警告信息',
};

const WARNING_LABELS = {
  warning_people_in_controlled_area: '受控区',
  warning_no_hardhat: '未戴安全帽',
  warning_no_safety_vest: '未穿反光背心',
  warning_close_to_machinery: '靠近机具',
  warning_close_to_vehicle: '靠近车辆',
  warning_people_in_utility_pole_controlled_area: '进入电杆管制区',
  detect_machinery_close_to_pole: '机具靠近电杆',
};

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

function authHeaders() {
  const token = getAccessTokenFromStorage();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

function readFiltersFromUI() {
  const siteSelect = document.getElementById('site-select');
  const keywordInput = document.getElementById('keyword-input');
  const startInput = document.getElementById('start-time');
  const endInput = document.getElementById('end-time');
  return {
    siteId: siteSelect ? String(siteSelect.value || '') : '',
    keyword: keywordInput ? String(keywordInput.value || '').trim() : '',
    startTime: startInput ? String(startInput.value || '') : '',
    endTime: endInput ? String(endInput.value || '') : '',
  };
}

let sitesCache = [];

function siteNameFromId(siteId) {
  if (!siteId) return '';
  const match = sitesCache.find((site) => String(site.id) === String(siteId));
  return match ? String(match.name || '').trim() : '';
}

function safeDateFromInput(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function toDatetimeLocalValue(date) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (v) => String(v).padStart(2, '0');
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mi = pad(d.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

function applyTimePreset({ minutes }) {
  const startInput = document.getElementById('start-time');
  const endInput = document.getElementById('end-time');
  if (!startInput || !endInput) return;
  const now = new Date();
  const start = new Date(now.getTime() - Math.max(1, Number(minutes) || 1) * 60 * 1000);
  startInput.value = toDatetimeLocalValue(start);
  endInput.value = toDatetimeLocalValue(now);
}

function buildSummaryText({ total, siteId, keyword, startTime, endTime }) {
  const parts = [];
  const name = siteNameFromId(siteId);
  if (name) parts.push(`工地：${name}`);
  if (keyword) parts.push(`关键字：${keyword}`);
  const start = safeDateFromInput(startTime);
  const end = safeDateFromInput(endTime);
  if (start || end) {
    const left = start ? start.toLocaleString() : '不限';
    const right = end ? end.toLocaleString() : '不限';
    parts.push(`时间：${left} ~ ${right}`);
  }
  const meta = parts.length > 0 ? `｜${parts.join(' ｜ ')}` : '';
  const count = Number.isFinite(total) ? total : 0;
  return `命中 ${count} 条${meta}`;
}

function setSummaryText(text) {
  const el = document.getElementById('violations-summary');
  if (!el) return;
  el.textContent = text || '';
}

const imageUrlCache = new Map();
const IMAGE_URL_CACHE_LIMIT = 100;

function setCachedObjectUrl(cache, key, objectUrl) {
  const previous = cache.get(key);
  if (previous) {
    URL.revokeObjectURL(previous);
  }
  cache.set(key, objectUrl);
  if (cache.size <= IMAGE_URL_CACHE_LIMIT) {
    return;
  }
  const oldestKey = cache.keys().next().value;
  if (oldestKey === undefined) {
    return;
  }
  const oldestUrl = cache.get(oldestKey);
  cache.delete(oldestKey);
  if (oldestUrl) {
    URL.revokeObjectURL(oldestUrl);
  }
}

function parseDetectionItems(raw) {
  if (!raw) return [];
  let parsed = raw;
  if (typeof raw === 'string') {
    if (!raw.trim()) {
      return [];
    }
    try {
      parsed = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed;
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

function drawViolationDetections(ctx, detectionItems, scaleX, scaleY) {
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
    if (cls !== 2 && cls !== 4) {
      return;
    }
    const color = cls === 2 ? '#ef4444' : '#f97316';
    const label = cls === 2 ? 'NO-Hardhat' : 'NO-Vest';
    const confText = Number.isFinite(conf) ? ` ${(conf * 100).toFixed(0)}%` : '';
    const text = `${label}${confText}`;
    ctx.strokeStyle = color;
    const w = x2 - x1;
    const h = y2 - y1;
    ctx.strokeRect(x1, y1, w, h);
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

let modalMounted = false;
let modalOverlay = null;
let modalImage = null;
let modalCanvas = null;
let modalTitleNode = null;
let modalToggleBtn = null;
let modalOpenLink = null;
let modalCloseBtn = null;
let modalDownloadBtn = null;
let modalDownloadAnnotatedBtn = null;
let modalLastUrl = '';
let modalLastDetections = [];
let modalShowDetections = true;
let modalPreviousOverflow = '';

function drawCanvasOverlay({ img, canvas, detectionItems }) {
  if (!img || !canvas) return;
  const rect = img.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const displayWidth = rect.width || img.naturalWidth || 0;
  const displayHeight = rect.height || img.naturalHeight || 0;
  if (!displayWidth || !displayHeight) {
    return;
  }
  canvas.width = Math.max(1, Math.round(displayWidth * dpr));
  canvas.height = Math.max(1, Math.round(displayHeight * dpr));
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, displayWidth, displayHeight);
  const srcW = img.naturalWidth || displayWidth;
  const srcH = img.naturalHeight || displayHeight;
  const scaleX = displayWidth / srcW;
  const scaleY = displayHeight / srcH;
  drawViolationDetections(ctx, detectionItems, scaleX, scaleY);
}

function mountImageModal() {
  if (modalMounted) return;
  modalMounted = true;

  modalOverlay = document.createElement('div');
  modalOverlay.className = 'violation-modal-overlay hidden';
  modalOverlay.setAttribute('role', 'dialog');
  modalOverlay.setAttribute('aria-modal', 'true');

  const modal = document.createElement('div');
  modal.className = 'violation-modal';

  const header = document.createElement('div');
  header.className = 'violation-modal-header';

  modalTitleNode = document.createElement('div');
  modalTitleNode.className = 'violation-modal-title';
  modalTitleNode.textContent = '图片预览';
  header.appendChild(modalTitleNode);

  const actions = document.createElement('div');
  actions.className = 'violation-modal-actions';

  modalToggleBtn = document.createElement('button');
  modalToggleBtn.type = 'button';
  modalToggleBtn.className = 'button secondary';
  modalToggleBtn.textContent = '隐藏标注';
  modalToggleBtn.addEventListener('click', () => {
    modalShowDetections = !modalShowDetections;
    if (modalCanvas) {
      modalCanvas.style.display = modalShowDetections ? '' : 'none';
    }
    if (modalToggleBtn) {
      modalToggleBtn.textContent = modalShowDetections ? '隐藏标注' : '显示标注';
    }
    if (modalShowDetections && modalImage && modalCanvas) {
      drawCanvasOverlay({ img: modalImage, canvas: modalCanvas, detectionItems: modalLastDetections });
    }
  });
  actions.appendChild(modalToggleBtn);

  modalOpenLink = document.createElement('button');
  modalOpenLink.type = 'button';
  modalOpenLink.className = 'button secondary';
  modalOpenLink.textContent = '新标签打开';
  modalOpenLink.addEventListener('click', () => {
    if (!modalLastUrl) return;
    window.open(modalLastUrl, '_blank', 'noopener,noreferrer');
  });
  actions.appendChild(modalOpenLink);

  modalDownloadBtn = document.createElement('button');
  modalDownloadBtn.type = 'button';
  modalDownloadBtn.className = 'button secondary';
  modalDownloadBtn.textContent = '下载原图';
  modalDownloadBtn.addEventListener('click', () => {
    if (!modalLastUrl) return;
    const a = document.createElement('a');
    a.href = modalLastUrl;
    a.download = 'violation.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
  actions.appendChild(modalDownloadBtn);

  modalDownloadAnnotatedBtn = document.createElement('button');
  modalDownloadAnnotatedBtn.type = 'button';
  modalDownloadAnnotatedBtn.className = 'button secondary';
  modalDownloadAnnotatedBtn.textContent = '下载标注图';
  modalDownloadAnnotatedBtn.addEventListener('click', () => {
    if (!modalImage) return;
    const naturalWidth = modalImage.naturalWidth;
    const naturalHeight = modalImage.naturalHeight;
    if (!naturalWidth || !naturalHeight) {
      return;
    }
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = naturalWidth;
    exportCanvas.height = naturalHeight;
    const exportCtx = exportCanvas.getContext('2d');
    if (!exportCtx) {
      return;
    }
    exportCtx.drawImage(modalImage, 0, 0, naturalWidth, naturalHeight);
    drawViolationDetections(exportCtx, modalLastDetections, 1, 1);
    const dataUrl = exportCanvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = 'violation-annotated.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
  actions.appendChild(modalDownloadAnnotatedBtn);

  modalCloseBtn = document.createElement('button');
  modalCloseBtn.type = 'button';
  modalCloseBtn.className = 'button secondary';
  modalCloseBtn.textContent = '关闭';
  actions.appendChild(modalCloseBtn);

  header.appendChild(actions);
  modal.appendChild(header);

  const body = document.createElement('div');
  body.className = 'violation-modal-body';

  const imageWrap = document.createElement('div');
  imageWrap.className = 'violation-modal-image';

  modalImage = document.createElement('img');
  modalImage.alt = '预览图片';
  imageWrap.appendChild(modalImage);

  modalCanvas = document.createElement('canvas');
  modalCanvas.className = 'violation-modal-canvas';
  imageWrap.appendChild(modalCanvas);

  body.appendChild(imageWrap);
  modal.appendChild(body);
  modalOverlay.appendChild(modal);
  document.body.appendChild(modalOverlay);

  const close = () => {
    if (!modalOverlay) return;
    modalOverlay.classList.add('hidden');
    document.body.style.overflow = modalPreviousOverflow;
    modalLastUrl = '';
    modalLastDetections = [];
  };

  modalCloseBtn.addEventListener('click', close);

  modalOverlay.addEventListener('click', (event) => {
    if (event.target === modalOverlay) {
      close();
    }
  });

  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!modalOverlay || modalOverlay.classList.contains('hidden')) return;
    event.preventDefault();
    close();
  });

  window.addEventListener('resize', () => {
    if (!modalOverlay || modalOverlay.classList.contains('hidden')) return;
    if (!modalShowDetections) return;
    if (!modalImage || !modalCanvas) return;
    drawCanvasOverlay({ img: modalImage, canvas: modalCanvas, detectionItems: modalLastDetections });
  });

  modalImage.addEventListener('load', () => {
    if (!modalShowDetections) return;
    if (!modalImage || !modalCanvas) return;
    drawCanvasOverlay({ img: modalImage, canvas: modalCanvas, detectionItems: modalLastDetections });
  });
}

function openImageModal({ url, detectionItems, title }) {
  mountImageModal();
  if (!modalOverlay || !modalImage || !modalCanvas || !modalTitleNode || !modalToggleBtn || !modalOpenLink) {
    return;
  }
  modalLastUrl = String(url || '');
  modalLastDetections = Array.isArray(detectionItems) ? detectionItems : [];
  modalTitleNode.textContent = title ? String(title) : '图片预览';
  modalOpenLink.disabled = !modalLastUrl;

  const hasDetections = modalLastDetections.length > 0;
  modalShowDetections = hasDetections;
  modalCanvas.style.display = hasDetections ? '' : 'none';
  modalToggleBtn.disabled = !hasDetections;
  modalToggleBtn.textContent = hasDetections ? '隐藏标注' : '无标注';

  modalPreviousOverflow = document.body.style.overflow || '';
  document.body.style.overflow = 'hidden';
  modalOverlay.classList.remove('hidden');
  modalImage.src = modalLastUrl;

  if (modalDownloadBtn) {
    modalDownloadBtn.disabled = !modalLastUrl;
  }
  if (modalDownloadAnnotatedBtn) {
    modalDownloadAnnotatedBtn.disabled = !hasDetections;
  }
}

async function fetchViolationImageUrl(imagePath) {
  if (!imagePath) return '';
  if (imageUrlCache.has(imagePath)) {
    return imageUrlCache.get(imagePath);
  }
  const headers = authHeaders();
  if (!headers.Authorization) {
    return '';
  }
  const url =
    `${buildApiUrl(ENDPOINTS.violationApiUrl, '/get_violation_image')}?image_path=${encodeURIComponent(imagePath)}`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    return '';
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  setCachedObjectUrl(imageUrlCache, imagePath, objectUrl);
  return objectUrl;
}

function formatWarningsText(warningsData) {
  if (!warningsData) return WARNINGS_TEXTS.no_warning;
  let parsed = null;
  if (typeof warningsData === 'string' && warningsData.trim() !== '') {
    try {
      parsed = JSON.parse(warningsData);
    } catch {
    }
  } else if (warningsData && typeof warningsData === 'object' && !Array.isArray(warningsData)) {
    parsed = warningsData;
  }
  const messages = [];
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const entries = Object.entries(parsed);
    for (const [key, value] of entries) {
      const count = value && typeof value === 'object' ? Number(value.count) || 0 : 0;
      if (!count) continue;
      const template = WARNINGS_TEXTS[key];
      if (template) {
        messages.push(template.replace('{count}', String(count)));
      } else {
        messages.push(`${key}: ${count}`);
      }
    }
  }
  if (messages.length === 0 && typeof warningsData === 'string') {
    return warningsData;
  }
  if (messages.length === 0) {
    return WARNINGS_TEXTS.no_warning;
  }
  return messages.join('\n');
}

function parseWarningsObject(warningsData) {
  if (!warningsData) return null;
  if (typeof warningsData === 'string') {
    const raw = warningsData.trim();
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch {
    }
    return null;
  }
  if (warningsData && typeof warningsData === 'object' && !Array.isArray(warningsData)) {
    return warningsData;
  }
  return null;
}

function buildWarningBadges(warningsData) {
  const obj = parseWarningsObject(warningsData);
  if (!obj) return [];
  const result = [];
  Object.entries(obj).forEach(([key, value]) => {
    const label = WARNING_LABELS[key] || String(key);
    const count = value && typeof value === 'object' ? Number(value.count) || 0 : 0;
    if (!count) return;
    result.push({ key: String(key), label, count });
  });
  return result;
}

function severityFromBadges(badges) {
  const keys = new Set(badges.map((b) => b.key));
  if (keys.has('warning_people_in_controlled_area') || keys.has('warning_people_in_utility_pole_controlled_area')) {
    return 'high';
  }
  if (keys.has('warning_no_hardhat') || keys.has('warning_no_safety_vest')) {
    return 'high';
  }
  if (keys.has('warning_close_to_vehicle') || keys.has('warning_close_to_machinery') || keys.has('detect_machinery_close_to_pole')) {
    return 'medium';
  }
  return badges.length > 0 ? 'low' : '';
}

function buildBadgeText(badge) {
  const count = Number(badge.count) || 0;
  if (count > 1) return `${badge.label}×${count}`;
  return badge.label;
}

function shouldCollapseText(text) {
  const value = String(text || '').trim();
  if (!value) return false;
  if (value.length > 180) return true;
  const lines = value.split('\n').filter((v) => v.trim() !== '');
  return lines.length > 3;
}

function createExpandableTextBlock({ className, text, collapsedLines = 3 }) {
  const wrapper = document.createElement('div');
  wrapper.className = className;
  wrapper.dataset.collapsedLines = String(Math.max(1, Number(collapsedLines) || 3));

  const content = document.createElement('div');
  content.className = `${className}-text`;
  content.textContent = String(text || '').trim();
  wrapper.appendChild(content);

  if (!shouldCollapseText(content.textContent)) {
    wrapper.classList.add('expanded');
    return wrapper;
  }

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = `${className}-toggle`;
  toggle.textContent = '展开';
  toggle.addEventListener('click', () => {
    const expanded = wrapper.classList.toggle('expanded');
    toggle.textContent = expanded ? '收起' : '展开';
  });
  wrapper.appendChild(toggle);
  return wrapper;
}

function formatRelativeTime(when, now = new Date()) {
  if (!(when instanceof Date) || Number.isNaN(when.getTime())) return '';
  const deltaMs = now.getTime() - when.getTime();
  if (!Number.isFinite(deltaMs)) return '';
  const absMs = Math.abs(deltaMs);
  const isFuture = deltaMs < 0;
  const suffix = isFuture ? '后' : '前';
  const sec = Math.max(0, Math.floor(absMs / 1000));
  if (sec < 10) return isFuture ? '即将' : '刚刚';
  if (sec < 60) return `${sec}秒${suffix}`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}分钟${suffix}`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}小时${suffix}`;
  const day = Math.floor(hour / 24);
  if (day < 30) return `${day}天${suffix}`;
  const month = Math.floor(day / 30);
  if (month < 12) return `${month}个月${suffix}`;
  const year = Math.floor(day / 365);
  return `${year}年${suffix}`;
}

function formatDetectionTime(value) {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '未知';
  const absolute = dt.toLocaleString();
  const relative = formatRelativeTime(dt);
  return relative ? `${relative}（${absolute}）` : absolute;
}

function severityLabel(severity) {
  if (severity === 'high') return '高风险';
  if (severity === 'medium') return '中风险';
  if (severity === 'low') return '低风险';
  return '';
}

function createAgentReportBlock(record) {
  const wrapper = document.createElement('div');
  wrapper.className = 'violation-agent-report';

  const header = document.createElement('div');
  header.className = 'violation-agent-report-header';

  const title = document.createElement('div');
  title.className = 'violation-agent-report-title';
  title.textContent = 'AI 分析报告';
  header.appendChild(title);

  const exportButton = document.createElement('button');
  exportButton.type = 'button';
  exportButton.className = 'violation-export-button';
  exportButton.textContent = '导出预警报告';
  exportButton.addEventListener('click', () => {
    exportViolationReport(record);
  });
  header.appendChild(exportButton);

  wrapper.appendChild(header);

  const content = document.createElement('div');
  content.className = 'violation-agent-report-text';
  content.textContent = String(record && record.agent_report ? record.agent_report : '').trim();
  wrapper.appendChild(content);

  const value = content.textContent;
  const lines = value.split('\n').filter((v) => v.trim() !== '');
  const shouldCollapse = value.length > 120 || lines.length > 2;
  if (!shouldCollapse) {
    wrapper.classList.add('expanded');
    return wrapper;
  }

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'violation-agent-report-toggle';
  toggle.textContent = '展开';
  toggle.addEventListener('click', () => {
    const expanded = wrapper.classList.toggle('expanded');
    toggle.textContent = expanded ? '收起' : '展开';
  });
  wrapper.appendChild(toggle);
  return wrapper;
}

function installBadgesScrollHint(badgeRow) {
  if (!badgeRow) return;
  const hint = document.createElement('span');
  hint.className = 'violation-badges-hint';
  hint.textContent = '左右滑动';
  badgeRow.appendChild(hint);

  const update = () => {
    const scrollable = badgeRow.scrollWidth > badgeRow.clientWidth + 1;
    badgeRow.classList.toggle('scrollable', scrollable);
    if (!scrollable) {
      badgeRow.classList.remove('hint-dismissed');
    }
  };

  requestAnimationFrame(update);
  badgeRow.addEventListener(
    'scroll',
    () => {
      if (badgeRow.scrollLeft > 6) {
        badgeRow.classList.add('hint-dismissed');
      }
    },
    { passive: true },
  );
}

async function fetchMySites() {
  const headers = authHeaders();
  if (!headers.Authorization) {
    return [];
  }
  const response = await fetch(buildApiUrl(ENDPOINTS.violationApiUrl, '/my_sites'), { headers });
  if (!response.ok) {
    return [];
  }
  return response.json();
}

function buildQueryParams(siteId, keyword, startTime, endTime) {
  const params = new URLSearchParams();
  if (siteId) params.append('site_id', siteId);
  if (keyword) params.append('keyword', keyword);
  if (startTime) {
    const startIso = new Date(startTime).toISOString();
    params.append('start_time', startIso);
  }
  if (endTime) {
    const endIso = new Date(endTime).toISOString();
    params.append('end_time', endIso);
  }
  params.append('limit', '50');
  params.append('offset', '0');
  return params.toString();
}

async function fetchViolations(siteId, keyword, startTime, endTime) {
  const headers = authHeaders();
  if (!headers.Authorization) {
    return { total: 0, items: [] };
  }
  const query = buildQueryParams(siteId, keyword, startTime, endTime);
  const response = await fetch(`${buildApiUrl(ENDPOINTS.violationApiUrl, '/violations')}?${query}`, {
    headers,
  });
  if (!response.ok) {
    return { total: 0, items: [] };
  }
  return response.json();
}

function createViolationItem(record) {
  const container = document.createElement('div');
  container.className = 'violation-item';

  const row = document.createElement('div');
  row.className = 'violation-row';

  const content = document.createElement('div');
  content.className = 'violation-content';

  const header = document.createElement('div');
  header.className = 'violation-header';

  const titleRow = document.createElement('div');
  titleRow.className = 'violation-title-row';

  const title = document.createElement('div');
  title.className = 'violation-title';
  title.textContent = String(record.stream_name || '未知串流');
  titleRow.appendChild(title);

  const badges = buildWarningBadges(record.warnings);
  const severity = severityFromBadges(badges);

  if (severity || badges.length > 0) {
    const badgeRow = document.createElement('div');
    badgeRow.className = 'violation-badges';

    if (severity) {
      const sev = document.createElement('span');
      sev.className = `violation-severity ${severity}`;
      sev.textContent = severityLabel(severity);
      badgeRow.appendChild(sev);
    }

    badges.slice(0, 5).forEach((badge) => {
      const node = document.createElement('span');
      node.className = 'violation-badge';
      node.textContent = buildBadgeText(badge);
      badgeRow.appendChild(node);
    });

    installBadgesScrollHint(badgeRow);
    header.appendChild(titleRow);
    header.appendChild(badgeRow);
  } else {
    header.appendChild(titleRow);
  }

  const time = document.createElement('div');
  time.className = 'violation-meta';
  const siteName = String(record.site_name || '').trim();
  const when = formatDetectionTime(record.detection_time);
  time.textContent = `${siteName ? `工地: ${siteName} ｜ ` : ''}检测时间: ${when}`;

  const warnings = createExpandableTextBlock({
    className: 'violation-warning',
    text: formatWarningsText(record.warnings),
    collapsedLines: 3,
  });

  content.appendChild(header);
  content.appendChild(time);
  content.appendChild(warnings);

  if (record.agent_report) {
    const agentReport = createAgentReportBlock(record);
    content.appendChild(agentReport);
  }

  if (!record.agent_report) {
    const actions = document.createElement('div');
    actions.className = 'violation-actions';
    const exportButton = document.createElement('button');
    exportButton.type = 'button';
    exportButton.className = 'violation-export-button';
    exportButton.textContent = '导出预警报告';
    exportButton.addEventListener('click', () => {
      exportViolationReport(record);
    });
    actions.appendChild(exportButton);
    content.appendChild(actions);
  }

  row.appendChild(content);

  if (record.image_path) {
    const detectionItems = parseDetectionItems(record.detection_items);
    const placeholder = document.createElement('div');
    placeholder.className = 'violation-image-container';
    row.appendChild(placeholder);
    loadViolationImage(record.image_path, placeholder, detectionItems, {
      modalTitle: `工地: ${record.site_name} ｜ 串流: ${record.stream_name}`,
    });
  }

  container.appendChild(row);
  return container;
}

async function exportViolationReport(record) {
  const headers = authHeaders();
  if (!headers.Authorization) {
    return;
  }
  const url =
    `${buildApiUrl(ENDPOINTS.violationApiUrl, `/violations/${record.id}/export`)}?format=markdown`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    return;
  }
  const blob = await response.blob();
  const downloadUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `violation-report-${record.id}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(downloadUrl);
}

async function loadViolationImage(imagePath, container, detectionItems, options = {}) {
  const url = await fetchViolationImageUrl(imagePath);
  if (!url) {
    container.remove();
    return;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'violation-image-wrapper';
  const imageLink = document.createElement('a');
  imageLink.className = 'violation-image';
  imageLink.href = url;
  imageLink.target = '_blank';
  imageLink.rel = 'noreferrer';
  const img = document.createElement('img');
  img.src = url;
  img.alt = '违章截图';
  imageLink.appendChild(img);
  wrapper.appendChild(imageLink);
  imageLink.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    openImageModal({
      url,
      detectionItems: Array.isArray(detectionItems) ? detectionItems : [],
      title: options && options.modalTitle ? String(options.modalTitle) : '',
    });
  });

  if (Array.isArray(detectionItems) && detectionItems.length > 0) {
    const canvas = document.createElement('canvas');
    canvas.style.position = 'absolute';
    canvas.style.left = '0';
    canvas.style.top = '0';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.pointerEvents = 'none';
    imageLink.style.position = 'relative';
    imageLink.appendChild(canvas);
    img.addEventListener('load', () => {
      const rect = img.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const displayWidth = rect.width || img.naturalWidth || 0;
      const displayHeight = rect.height || img.naturalHeight || 0;
      if (!displayWidth || !displayHeight) {
        return;
      }
      canvas.width = Math.max(1, Math.round(displayWidth * dpr));
      canvas.height = Math.max(1, Math.round(displayHeight * dpr));
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        return;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, displayWidth, displayHeight);
      const srcW = img.naturalWidth || displayWidth;
      const srcH = img.naturalHeight || displayHeight;
      const scaleX = displayWidth / srcW;
      const scaleY = displayHeight / srcH;
      drawViolationDetections(ctx, detectionItems, scaleX, scaleY);
    });
  }

  if (Array.isArray(detectionItems) && detectionItems.length > 0) {
    const downloadBtn = document.createElement('button');
    downloadBtn.type = 'button';
    downloadBtn.className = 'violation-download-button';
    downloadBtn.textContent = '下载带标注图片';
    downloadBtn.addEventListener('click', () => {
      const naturalWidth = img.naturalWidth;
      const naturalHeight = img.naturalHeight;
      if (!naturalWidth || !naturalHeight) {
        return;
      }
      const exportCanvas = document.createElement('canvas');
      exportCanvas.width = naturalWidth;
      exportCanvas.height = naturalHeight;
      const exportCtx = exportCanvas.getContext('2d');
      if (!exportCtx) {
        return;
      }
      exportCtx.drawImage(img, 0, 0, naturalWidth, naturalHeight);
      drawViolationDetections(exportCtx, detectionItems, 1, 1);
      const dataUrl = exportCanvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = 'violation-annotated.png';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });
    wrapper.appendChild(downloadBtn);
  }

  container.replaceWith(wrapper);
}

function renderViolations(records) {
  const list = document.getElementById('violation-list');
  if (!list) {
    return;
  }
  list.innerHTML = '';
  const items = Array.isArray(records)
    ? records
    : records && Array.isArray(records.items)
      ? records.items
      : [];
  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-text';
    empty.textContent = getAccessTokenFromStorage()
      ? '目前没有违规记录'
      : '未登录或登录已过期，请先登录后再查询违规记录';
    list.appendChild(empty);
    return;
  }
  items.forEach((record) => {
    const item = createViolationItem(record);
    list.appendChild(item);
  });
}

function renderSiteOptions(sites) {
  const select = document.getElementById('site-select');
  select.innerHTML = '';
  const allOption = document.createElement('option');
  allOption.value = '';
  allOption.textContent = '全部站点';
  select.appendChild(allOption);
  sites.forEach((site) => {
    const option = document.createElement('option');
    option.value = String(site.id);
    option.textContent = site.name;
    select.appendChild(option);
  });
}

async function initialisePage() {
  sitesCache = await fetchMySites();
  renderSiteOptions(sitesCache);
  if (!getAccessTokenFromStorage()) {
    setSummaryText('未登录或登录已过期，请先登录后再查询违规记录');
    renderViolations([]);
    return;
  }
  setSummaryText('加载中...');
  const result = await fetchViolations('', '', '', '');
  setSummaryText(buildSummaryText({ total: result.total, siteId: '', keyword: '', startTime: '', endTime: '' }));
  renderViolations(result);
}

function bindSearch() {
  const button = document.getElementById('search-button');
  if (!button) {
    return;
  }
  const resetButton = document.getElementById('reset-button');
  const preset1h = document.getElementById('preset-1h');
  const preset24h = document.getElementById('preset-24h');
  const preset7d = document.getElementById('preset-7d');

  const runSearch = async () => {
    if (!getAccessTokenFromStorage()) {
      setSummaryText('未登录或登录已过期，请先登录后再查询违规记录');
      renderViolations([]);
      return;
    }
    const { siteId, keyword, startTime, endTime } = readFiltersFromUI();
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = '查询中...';
    setSummaryText('查询中...');
    const list = document.getElementById('violation-list');
    if (list) {
      list.innerHTML = '';
      const loading = document.createElement('div');
      loading.className = 'empty-text';
      loading.textContent = '加载中...';
      list.appendChild(loading);
    }
    try {
      const result = await fetchViolations(siteId, keyword, startTime, endTime);
      setSummaryText(buildSummaryText({ total: result.total, siteId, keyword, startTime, endTime }));
      renderViolations(result);
    } finally {
      button.disabled = false;
      button.textContent = originalText || '查询';
    }
  };

  button.addEventListener('click', () => {
    void runSearch();
  });

  if (resetButton) {
    resetButton.addEventListener('click', () => {
      const siteSelect = document.getElementById('site-select');
      const keywordInput = document.getElementById('keyword-input');
      const startInput = document.getElementById('start-time');
      const endInput = document.getElementById('end-time');
      if (siteSelect) siteSelect.value = '';
      if (keywordInput) keywordInput.value = '';
      if (startInput) startInput.value = '';
      if (endInput) endInput.value = '';
      void runSearch();
    });
  }

  if (preset1h) {
    preset1h.addEventListener('click', () => {
      applyTimePreset({ minutes: 60 });
      void runSearch();
    });
  }
  if (preset24h) {
    preset24h.addEventListener('click', () => {
      applyTimePreset({ minutes: 24 * 60 });
      void runSearch();
    });
  }
  if (preset7d) {
    preset7d.addEventListener('click', () => {
      applyTimePreset({ minutes: 7 * 24 * 60 });
      void runSearch();
    });
  }

  const enterTargets = [
    document.getElementById('keyword-input'),
    document.getElementById('start-time'),
    document.getElementById('end-time'),
  ].filter(Boolean);
  enterTargets.forEach((el) => {
    el.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      void runSearch();
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  mountViolationsView();
});

let violationsMounted = false;

export async function mountViolationsView() {
  if (!violationsMounted) {
    bindSearch();
    violationsMounted = true;
  }
  await initialisePage();
}
