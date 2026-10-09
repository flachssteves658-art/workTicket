import { marked } from 'marked';
import { ENDPOINTS, buildApiUrl } from './app_endpoints.js';

const VIOLATION_API_URL = ENDPOINTS.violationApiUrl;
const SEGMENT_API_URL = ENDPOINTS.violationApiUrl;

let searchMounted = false;

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

async function fetchMySitesForSearch() {
  const headers = authHeaders();
  if (!headers.Authorization) {
    return [];
  }
  const response = await fetch(buildApiUrl(VIOLATION_API_URL, '/my_sites'), { headers });
  if (!response.ok) {
    return [];
  }
  return response.json();
}

function renderSearchSiteOptions(sites) {
  const select = document.getElementById('search-site');
  if (!select) return;
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

function normaliseText(text) {
  return String(text || '').trim();
}

function cleanSegmentsKeyword(value) {
  let text = normaliseText(value);
  if (!text) return '';
  text = text.replace(/\d{4}\s*[\/-]\s*\d{1,2}\s*[\/-]\s*\d{1,2}/g, ' ');
  text = text.replace(/\d{1,2}\s*:\s*\d{1,2}/g, ' ');
  text = text.replace(/\d{1,2}\s*点\s*\d{1,2}/g, ' ');
  text = text.replace(/\d{1,2}\s*点/g, ' ');
  text = text.replace(/\d+(?:\.\d+)?/g, ' ');
  text = text.replace(/(片段|视频|影片|畫面|监控|录像|錄像|摄像|摄像头|test3\.mp4|test3|mp4|演示|demo)/gi, ' ');
  text = text.replace(/\s+/g, ' ').trim();
  return text;
}

function cleanSegmentsLocation(value) {
  const text = normaliseText(value);
  if (!text) return '';
  if (/^\d{4}[\/-]\d{1,2}[\/-]\d{1,2}$/.test(text)) return '';
  if (/^\d{1,2}[\/-]\d{1,2}(?:[\/-]\d{1,2})?$/.test(text)) return '';
  if (/^\d+(?:\.\d+)?$/.test(text)) return '';
  if (/^\d{1,2}:\d{1,2}$/.test(text)) return '';
  if (/^\d{1,2}点\d{1,2}$/.test(text)) return '';
  if (/^\d{1,2}点$/.test(text)) return '';
  return text;
}

function appendMessage(role, text, extraNode) {
  const container = document.getElementById('search-messages');
  if (!container) return;
  const wrapper = document.createElement('div');
  wrapper.className = `chat-message chat-message-${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  if (typeof text === 'string' && text) {
    if (role === 'assistant') {
      bubble.innerHTML = marked.parse(text);
    } else {
      bubble.textContent = text;
    }
  }
  if (extraNode instanceof Node) {
    if (bubble.textContent) {
      bubble.appendChild(document.createElement('br'));
    }
    bubble.appendChild(extraNode);
  }
  wrapper.appendChild(bubble);
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  return bubble;
}

function describeTimeRange(range) {
  if (!range) return '';
  const now = new Date();
  const start = range.start ? new Date(range.start) : null;
  const end = range.end ? new Date(range.end) : null;
  const prefix = '时间范围';
  if (start && end) {
    if (start.toDateString() === end.toDateString()) {
      const dateStr = start.toLocaleDateString();
      const s = start.toTimeString().slice(0, 5);
      const e = end.toTimeString().slice(0, 5);
      return `${prefix}：${dateStr} ${s} - ${e}`;
    }
    return `${prefix}：${start.toLocaleString()} - ${end.toLocaleString()}`;
  }
  if (start && !end) {
    return `${prefix}：自 ${start.toLocaleString()} 起`;
  }
  if (!start && end) {
    return `${prefix}：截至 ${end.toLocaleString()}`;
  }
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  return `${prefix}：最近 24 小时（约自 ${yesterday.toLocaleString()} 起）`;
}

function queryContainsExplicitDate(query) {
  const text = normaliseText(query);
  if (!text) return false;
  const raw = text.replace(/\s+/g, '');
  if (/\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}/.test(raw)) return true;
  if (/\d{4}年/.test(raw)) return true;
  if (/(\d{1,2})[\/\-](\d{1,2})/.test(raw)) return true;
  if (/([0-9]+|[一二两三四五六七八九十]+)月([0-9]+|[一二两三四五六七八九十]+)[日号]/.test(raw)) {
    return true;
  }
  return false;
}

function parseTimeRangeFromQuery(query) {
  const text = normaliseText(query);
  if (!text) {
    return null;
  }
  const now = new Date();
  const raw = text.replace(/\s+/g, '');

  function clampDateRange(start, end) {
    if (!(start instanceof Date) || !(end instanceof Date)) return null;
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    if (start.getTime() > end.getTime()) {
      return { start: end, end: start };
    }
    return { start, end };
  }

  function startOfDay(d) {
    const v = new Date(d);
    v.setHours(0, 0, 0, 0);
    return v;
  }

  function endOfDay(d) {
    const v = new Date(d);
    v.setHours(23, 59, 59, 999);
    return v;
  }

  function startOfWeek(d) {
    const v = startOfDay(d);
    const day = v.getDay();
    const delta = day === 0 ? -6 : 1 - day;
    v.setDate(v.getDate() + delta);
    return v;
  }

  function endOfWeek(d) {
    const v = startOfWeek(d);
    v.setDate(v.getDate() + 6);
    return endOfDay(v);
  }

  function parseChineseNumber(input) {
    const s = String(input || '').trim();
    if (!s) return NaN;
    if (/^\d+$/.test(s)) return Number(s);
    const map = {
      零: 0,
      〇: 0,
      一: 1,
      二: 2,
      两: 2,
      三: 3,
      四: 4,
      五: 5,
      六: 6,
      七: 7,
      八: 8,
      九: 9,
    };
    if (s === '十') return 10;
    if (s.length === 2 && s[0] === '十') {
      const ones = map[s[1]];
      return Number.isFinite(ones) ? 10 + ones : NaN;
    }
    if (s.length === 2 && s[1] === '十') {
      const tens = map[s[0]];
      return Number.isFinite(tens) ? tens * 10 : NaN;
    }
    if (s.length === 3 && s[1] === '十') {
      const tens = map[s[0]];
      const ones = map[s[2]];
      if (!Number.isFinite(tens) || !Number.isFinite(ones)) return NaN;
      return tens * 10 + ones;
    }
    if (s.length === 1 && Object.prototype.hasOwnProperty.call(map, s)) {
      return map[s];
    }
    return NaN;
  }

  function parseDuration(textValue) {
    const m = textValue.match(/(近|最近|过去|前)([0-9]+|[一二两三四五六七八九十]+)(分钟|分|小时|时|天|日|周|星期|礼拜|个月|月)/);
    if (!m) return 0;
    const n = parseChineseNumber(m[2]);
    if (!Number.isFinite(n) || n <= 0) return 0;
    const unit = m[3];
    if (unit === '分钟' || unit === '分') return n * 60 * 1000;
    if (unit === '小时' || unit === '时') return n * 60 * 60 * 1000;
    if (unit === '天' || unit === '日') return n * 24 * 60 * 60 * 1000;
    if (unit === '周' || unit === '星期' || unit === '礼拜') return n * 7 * 24 * 60 * 60 * 1000;
    if (unit === '个月' || unit === '月') return n * 30 * 24 * 60 * 60 * 1000;
    return 0;
  }

  function parseExplicitDate(textValue) {
    const iso = textValue.match(/(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
    if (iso) {
      const year = Number(iso[1]);
      const month = Number(iso[2]);
      const day = Number(iso[3]);
      const d = new Date(year, month - 1, day);
      if (!Number.isNaN(d.getTime())) return d;
    }
    const md = textValue.match(/(^|[^\d])(\d{1,2})[\/\-](\d{1,2})([^\d]|$)/);
    if (md) {
      const year = now.getFullYear();
      const month = Number(md[2]);
      const day = Number(md[3]);
      const d = new Date(year, month - 1, day);
      if (!Number.isNaN(d.getTime())) return d;
    }
    const zh = textValue.match(/([0-9]+|[一二两三四五六七八九十]+)月([0-9]+|[一二两三四五六七八九十]+)[日号]/);
    if (zh) {
      const year = now.getFullYear();
      const month = parseChineseNumber(zh[1]);
      const day = parseChineseNumber(zh[2]);
      if (Number.isFinite(month) && Number.isFinite(day)) {
        const d = new Date(year, month - 1, day);
        if (!Number.isNaN(d.getTime())) return d;
      }
    }
    return null;
  }

  function inferDayOffset(textValue) {
    if (textValue.includes('大前天')) return -3;
    if (textValue.includes('前天')) return -2;
    if (textValue.includes('昨天') || textValue.includes('昨日') || textValue.includes('昨儿')) return -1;
    if (textValue.includes('今天') || textValue.includes('今日')) return 0;
    if (textValue.includes('明天')) return 1;
    return null;
  }

  function makeBaseDate() {
    const explicit = parseExplicitDate(raw);
    if (explicit) return explicit;
    const offset = inferDayOffset(raw);
    const base = new Date(now);
    base.setHours(0, 0, 0, 0);
    if (typeof offset === 'number') {
      base.setDate(base.getDate() + offset);
    }
    return base;
  }

  function applyTimeOfDay(dateBase, hour, minute) {
    const d = new Date(dateBase);
    d.setHours(hour, minute, 0, 0);
    return d;
  }

  function parseTimeToken(token, hint) {
    const v = String(token || '').trim();
    if (!v) return null;
    const h1 = v.match(/(\d{1,2})[:：](\d{1,2})/);
    if (h1) {
      const hour = Number(h1[1]);
      const minute = Number(h1[2]);
      if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
      return { hour, minute, hint };
    }
    const h2 = v.match(/(\d{1,2})点(?:(\d{1,2})分)?/);
    if (h2) {
      const hour = Number(h2[1]);
      let minute = h2[2] ? Number(h2[2]) : 0;
      if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
      if (v.includes('半')) minute = 30;
      if (v.includes('一刻')) minute = 15;
      if (v.includes('三刻')) minute = 45;
      return { hour, minute, hint };
    }
    return null;
  }

  function adjustHourByHint(hour, hint) {
    const h = Number(hour);
    if (!Number.isFinite(h)) return hour;
    const key = String(hint || '');
    if (['下午', '晚上', '夜里', '夜间', '傍晚'].includes(key)) {
      if (h >= 1 && h <= 11) return h + 12;
      return h;
    }
    if (key === '中午') {
      if (h >= 1 && h <= 10) return h + 12;
      return h;
    }
    if (key === '凌晨') {
      if (h === 12) return 0;
      return h;
    }
    if (['早上', '上午', '清晨', '今早'].includes(key)) {
      if (h === 12) return 0;
      return h;
    }
    return h;
  }

  const durationMs = parseDuration(raw);
  if (durationMs > 0) {
    const end = new Date(now);
    const start = new Date(now.getTime() - durationMs);
    return clampDateRange(start, end);
  }

  if (raw.includes('本周') || raw.includes('这周') || raw.includes('本星期') || raw.includes('本礼拜')) {
    const start = startOfWeek(now);
    const end = new Date(now);
    return clampDateRange(start, end);
  }
  if (raw.includes('上周') || raw.includes('上星期') || raw.includes('上礼拜')) {
    const start = startOfWeek(new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000));
    const end = endOfWeek(start);
    return clampDateRange(start, end);
  }
  if (raw.includes('本月') || raw.includes('这个月')) {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now);
    return clampDateRange(start, end);
  }
  if (raw.includes('上月')) {
    const y = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
    const m = now.getMonth() === 0 ? 11 : now.getMonth() - 1;
    const start = new Date(y, m, 1);
    const end = endOfDay(new Date(y, m + 1, 0));
    return clampDateRange(start, end);
  }
  if (raw.includes('今年') || raw.includes('本年')) {
    const start = new Date(now.getFullYear(), 0, 1);
    const end = new Date(now);
    return clampDateRange(start, end);
  }
  if (raw.includes('去年')) {
    const start = new Date(now.getFullYear() - 1, 0, 1);
    const end = endOfDay(new Date(now.getFullYear() - 1, 11, 31));
    return clampDateRange(start, end);
  }

  const baseDate = makeBaseDate();
  const timeRangeMatch = raw.match(
    /(凌晨|早上|上午|中午|下午|傍晚|晚上|夜里|夜间|今早)?(\d{1,2}[:：]\d{1,2}|\d{1,2}点(?:\d{1,2}分)?(?:半|一刻|三刻)?)\s*(到|至|-|~|—|－|–|～)\s*(凌晨|早上|上午|中午|下午|傍晚|晚上|夜里|夜间|今早)?(\d{1,2}[:：]\d{1,2}|\d{1,2}点(?:\d{1,2}分)?(?:半|一刻|三刻)?)/,
  );
  if (timeRangeMatch) {
    const t1 = parseTimeToken(timeRangeMatch[2], timeRangeMatch[1]);
    const t2 = parseTimeToken(timeRangeMatch[5], timeRangeMatch[4]);
    if (t1 && t2) {
      const h1 = adjustHourByHint(t1.hour, t1.hint);
      const h2 = adjustHourByHint(t2.hour, t2.hint);
      const start = applyTimeOfDay(baseDate, h1, t1.minute);
      const end = applyTimeOfDay(baseDate, h2, t2.minute);
      return clampDateRange(start, end);
    }
  }

  const singleTimeMatch = raw.match(
    /(凌晨|早上|上午|中午|下午|傍晚|晚上|夜里|夜间|今早)?(\d{1,2}[:：]\d{1,2}|\d{1,2}点(?:\d{1,2}分)?(?:半|一刻|三刻)?)(左右|附近|前后)?/,
  );
  if (singleTimeMatch) {
    const t = parseTimeToken(singleTimeMatch[2], singleTimeMatch[1]);
    if (t) {
      const hour = adjustHourByHint(t.hour, t.hint);
      const anchor = applyTimeOfDay(baseDate, hour, t.minute);
      const wide = Boolean(singleTimeMatch[3]);
      const start = new Date(anchor.getTime() - (wide ? 30 : 0) * 60 * 1000);
      const end = new Date(anchor.getTime() + (wide ? 30 : 60) * 60 * 1000);
      return clampDateRange(start, end);
    }
  }

  function segmentRangeForBase(textValue, base) {
    if (textValue.includes('凌晨')) return clampDateRange(applyTimeOfDay(base, 0, 0), applyTimeOfDay(base, 6, 0));
    if (textValue.includes('早上') || textValue.includes('上午') || textValue.includes('清晨') || textValue.includes('今早')) {
      return clampDateRange(applyTimeOfDay(base, 6, 0), applyTimeOfDay(base, 12, 0));
    }
    if (textValue.includes('中午')) return clampDateRange(applyTimeOfDay(base, 11, 0), applyTimeOfDay(base, 13, 0));
    if (textValue.includes('下午')) return clampDateRange(applyTimeOfDay(base, 12, 0), applyTimeOfDay(base, 18, 0));
    if (textValue.includes('傍晚')) return clampDateRange(applyTimeOfDay(base, 17, 0), applyTimeOfDay(base, 19, 0));
    if (textValue.includes('晚上') || textValue.includes('夜里') || textValue.includes('夜间') || textValue.includes('昨晚')) {
      return clampDateRange(applyTimeOfDay(base, 18, 0), applyTimeOfDay(base, 23, 59));
    }
    return null;
  }

  const segment = segmentRangeForBase(raw, baseDate);
  if (segment) return segment;

  const explicitDay = parseExplicitDate(raw);
  if (explicitDay) {
    return clampDateRange(startOfDay(explicitDay), endOfDay(explicitDay));
  }

  const dayOffset = inferDayOffset(raw);
  if (typeof dayOffset === 'number') {
    const d = new Date(now);
    d.setDate(d.getDate() + dayOffset);
    return clampDateRange(startOfDay(d), endOfDay(d));
  }

  if (raw.includes('近一周') || raw.includes('最近一周')) {
    const end = new Date(now);
    const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return clampDateRange(start, end);
  }
  if (raw.includes('近三天') || raw.includes('最近三天')) {
    const end = new Date(now);
    const start = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);
    return clampDateRange(start, end);
  }
  return null;
}

function pickSiteIdFromQuery(query, sites) {
  const text = normaliseText(query);
  if (!text || !Array.isArray(sites) || sites.length === 0) {
    return '';
  }
  const lower = text.toLowerCase();
  for (const site of sites) {
    const name = String(site.name || '');
    const lowerName = name.toLowerCase();
    if (!lowerName) continue;
    if (lower.includes(lowerName)) {
      return String(site.id);
    }
  }
  return '';
}

function buildKeywordFromQuery(query, siteNameMatched) {
  const text = normaliseText(query);
  if (!text) return '';
  let cleaned = text;
  if (Array.isArray(siteNameMatched)) {
    siteNameMatched.forEach((name) => {
      const v = String(name || '').trim();
      if (!v) return;
      cleaned = cleaned.replace(v, '');
    });
  } else if (siteNameMatched) {
    cleaned = cleaned.replace(siteNameMatched, '');
  }
  cleaned = cleaned.replace(/(查询|查一下|帮我查找|帮我看看|看看)/g, '');
  cleaned = cleaned.replace(/(视频|画面|录像|记录|违规|违章|违规行为|违章行为|安全隐患|危险情况|问题|情况)/g, '');
  cleaned = cleaned.replace(/\d{4}[\/-]\d{1,2}[\/-]\d{1,2}/g, '');
  cleaned = cleaned.replace(/(^|[^\d])\d{1,2}[\/-]\d{1,2}([^\d]|$)/g, '$1$2');
  cleaned = cleaned.replace(/([0-9]+|[一二两三四五六七八九十]+)月([0-9]+|[一二两三四五六七八九十]+)[日号]/g, '');
  cleaned = cleaned.replace(
    /(大前天|前天|昨天下午|昨天早上|昨日上午|昨晚|昨天|今日|今天下午|今天早上|今早|今天上午|今天|近一周|最近一周|近三天|最近三天|本周|这周|本星期|本礼拜|上周|上星期|上礼拜|本月|这个月|上月|今年|本年|去年|凌晨|清晨|早上|上午|中午|下午|傍晚|晚上|夜里|夜间|最近[0-9一二两三四五六七八九十]+(分钟|分|小时|时|天|日|周|星期|礼拜|个月|月)|近[0-9一二两三四五六七八九十]+(分钟|分|小时|时|天|日|周|星期|礼拜|个月|月)|过去[0-9一二两三四五六七八九十]+(分钟|分|小时|时|天|日|周|星期|礼拜|个月|月))/g,
    '',
  );
  const tokens = cleaned
    .split(/[\s，,。；;、]+/)
    .map((v) => v.trim())
    .filter((v) => v);
  if (tokens.length === 0) {
    return '';
  }
  return tokens.join(' ');
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
    `${buildApiUrl(VIOLATION_API_URL, '/get_violation_image')}?image_path=${encodeURIComponent(imagePath)}`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    return '';
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  setCachedObjectUrl(imageUrlCache, imagePath, objectUrl);
  return objectUrl;
}

async function loadViolationImageInto(container, imagePath) {
  const url = await fetchViolationImageUrl(imagePath);
  if (!url) {
    container.remove();
    return;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'violation-image-wrapper';
  wrapper.style.maxWidth = '220px';
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
  container.replaceWith(wrapper);
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

async function fetchViolationsForSearch(siteId, keyword, startTime, endTime) {
  const headers = authHeaders();
  if (!headers.Authorization) {
    throw new Error('UNAUTHORIZED');
  }
  const query = buildQueryParams(siteId, keyword, startTime, endTime);
  const response = await fetch(`${buildApiUrl(VIOLATION_API_URL, '/violations')}?${query}`, {
    headers,
  });
  if (response.status === 401 || response.status === 403) {
    throw new Error('UNAUTHORIZED');
  }
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

async function fetchViolationsIntent(userQuery, defaultSiteId) {
  const headers = authHeaders();
  if (!headers.Authorization) {
    throw new Error('UNAUTHORIZED');
  }
  const params = new URLSearchParams();
  params.append('user_query', userQuery);
  if (defaultSiteId) {
    params.append('default_site_id', String(defaultSiteId));
  }
  const response = await fetch(
    `${buildApiUrl(VIOLATION_API_URL, '/violations/intent')}?${params.toString()}`,
    { headers },
  );
  if (response.status === 401 || response.status === 403) {
    throw new Error('UNAUTHORIZED');
  }
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

async function fetchViolationsSummary(siteId, keyword, startTime, endTime, userQuery) {
  const headers = authHeaders();
  if (!headers.Authorization) {
    throw new Error('UNAUTHORIZED');
  }
  const params = new URLSearchParams();
  if (siteId) params.append('site_id', siteId);
  if (keyword) params.append('keyword', keyword);
  if (startTime) params.append('start_time', new Date(startTime).toISOString());
  if (endTime) params.append('end_time', new Date(endTime).toISOString());
  if (userQuery) params.append('user_query', userQuery);
  params.append('sample_limit', '20');
  const response = await fetch(
    `${buildApiUrl(VIOLATION_API_URL, '/violations/summary')}?${params.toString()}`,
    {
      headers,
    },
  );
  if (response.status === 401 || response.status === 403) {
    throw new Error('UNAUTHORIZED');
  }
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

async function fetchSegmentsIntent(userQuery) {
  const params = new URLSearchParams();
  params.append('user_query', userQuery);
  const response = await fetch(`${buildApiUrl(SEGMENT_API_URL, '/segments/intent')}?${params.toString()}`);
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

async function fetchSegments(keyword, startSec, endSec, ranges) {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  if (typeof startSec === 'number' && Number.isFinite(startSec)) params.append('start_sec', String(startSec));
  if (typeof endSec === 'number' && Number.isFinite(endSec)) params.append('end_sec', String(endSec));
  if (Array.isArray(ranges)) {
    ranges.forEach((range) => {
      if (!range) return;
      if (typeof range === 'string') {
        const text = range.trim();
        if (text) params.append('range', text);
        return;
      }
      if (typeof range === 'object') {
        const s = typeof range.start_sec === 'number' ? range.start_sec : Number(range.start_sec);
        const e = typeof range.end_sec === 'number' ? range.end_sec : Number(range.end_sec);
        if (Number.isFinite(s) && Number.isFinite(e) && e > s) {
          params.append('range', `${s}-${e}`);
        }
      }
    });
  }
  const response = await fetch(`${buildApiUrl(SEGMENT_API_URL, '/segments')}?${params.toString()}`);
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

async function fetchSegmentsClips(keyword, startSec, endSec, ranges) {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  if (typeof startSec === 'number' && Number.isFinite(startSec)) params.append('start_sec', String(startSec));
  if (typeof endSec === 'number' && Number.isFinite(endSec)) params.append('end_sec', String(endSec));
  if (Array.isArray(ranges)) {
    ranges.forEach((range) => {
      if (!range) return;
      if (typeof range === 'string') {
        const text = range.trim();
        if (text) params.append('range', text);
        return;
      }
      if (typeof range === 'object') {
        const s = typeof range.start_sec === 'number' ? range.start_sec : Number(range.start_sec);
        const e = typeof range.end_sec === 'number' ? range.end_sec : Number(range.end_sec);
        if (Number.isFinite(s) && Number.isFinite(e) && e > s) {
          params.append('range', `${s}-${e}`);
        }
      }
    });
  }
  const response = await fetch(`${buildApiUrl(SEGMENT_API_URL, '/segments/clips')}?${params.toString()}`);
  if (!response.ok) {
    throw new Error('REQUEST_FAILED');
  }
  return response.json();
}

function shouldUseSegmentsMode(query) {
  const text = normaliseText(query).toLowerCase();
  if (!text) return false;
  const compact = text.replace(/\s+/g, '');

  const hasVideoIntent = (
    compact.includes('监控')
    || compact.includes('回放')
    || compact.includes('视频')
    || compact.includes('录像')
    || compact.includes('摄像')
    || compact.includes('摄像头')
    || compact.includes('画面')
  );

  const hasTimeHint = (
    queryContainsExplicitDate(compact)
    || /\d{1,2}:\d{2}/.test(compact)
    || /(昨|今|明|前天|昨天|今天|明天|上周|本周|最近|过去|近)\b/.test(compact)
    || compact.includes('上午')
    || compact.includes('下午')
    || compact.includes('晚上')
    || compact.includes('中午')
    || compact.includes('凌晨')
  );

  const hasTimeRange = (
    /(\d{1,2}:\d{2}).*(到|至|-|~|—|－|–|～).*(\d{1,2}:\d{2})/.test(compact)
    || /(\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}).*(\d{1,2}:\d{2}).*(到|至|-|~|—|－|–|～).*(\d{1,2}:\d{2})/.test(compact)
  );

  return (
    text.includes('test3')
    || text.includes('片段')
    || text.includes('演示')
    || text.includes('demo')
    || text.includes('开头')
    || text.includes('中间')
    || text.includes('结尾')
    || text.includes('最后')
    || (hasVideoIntent && (hasTimeRange || hasTimeHint))
  );
}

function shouldTryViolationsAlongside(query) {
  const text = normaliseText(query).toLowerCase();
  if (!text) return false;
  return (
    text.includes('违规')
    || text.includes('违章')
    || text.includes('告警')
    || text.includes('预警')
    || text.includes('报警')
    || text.includes('隐患')
    || text.includes('风险')
    || text.includes('事件')
    || text.includes('记录')
  );
}

function formatSegmentTimeRange(startSec, endSec) {
  const s = typeof startSec === 'number' ? startSec : Number(startSec);
  const e = typeof endSec === 'number' ? endSec : Number(endSec);
  if (!Number.isFinite(s) || !Number.isFinite(e)) return '';
  return `时间片段：${s.toFixed(1)}s - ${e.toFixed(1)}s`;
}

function buildClipsResultsNode(description, records) {
  const container = document.createElement('div');
  const summary = document.createElement('div');
  summary.className = 'chat-result-summary';
  const parts = [];
  if (description) parts.push(description);
  parts.push(`命中区间：${Array.isArray(records) ? records.length : 0} 条`);
  summary.textContent = parts.join(' ｜ ');
  container.appendChild(summary);

  const list = document.createElement('div');
  list.className = 'chat-result-list';
  if (!records || records.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-text';
    empty.textContent = '没有找到匹配的视频区间，可以尝试修改描述或放宽时间范围。';
    list.appendChild(empty);
    container.appendChild(list);
    return container;
  }

  records.forEach((record, idx) => {
    const item = document.createElement('div');
    item.className = 'chat-result-item';

    const row = document.createElement('div');
    row.className = 'violation-row';

    const content = document.createElement('div');
    content.className = 'violation-content';

    const title = document.createElement('div');
    title.className = 'chat-result-title';
    title.textContent = `test3.mp4 ｜ 回放区间 #${typeof record.clip_id === 'number' ? record.clip_id : (idx + 1)}`;

    const meta = document.createElement('div');
    meta.className = 'chat-result-meta';
    const rangeText = formatSegmentTimeRange(record.start_sec, record.end_sec);
    const segCount = typeof record.segments_count === 'number' ? record.segments_count : Number(record.segments_count);
    meta.textContent = `${rangeText}${Number.isFinite(segCount) && segCount > 0 ? ` ｜ 证据片段：${segCount} 段` : ''}`;

    content.appendChild(title);
    content.appendChild(meta);

    const caption = String(record.caption || '').trim();
    if (caption) {
      const text = document.createElement('div');
      text.className = 'chat-result-text';
      text.textContent = caption;
      content.appendChild(text);
    }

    const controls = document.createElement('div');
    controls.className = 'chat-result-meta';
    controls.style.display = 'flex';
    controls.style.gap = '10px';
    controls.style.alignItems = 'center';

    const startSec = typeof record.start_sec === 'number' ? record.start_sec : Number(record.start_sec);
    const endSec = typeof record.end_sec === 'number' ? record.end_sec : Number(record.end_sec);

    const videoUrl = String(record.video_url || '').trim() || '/segments/video';
    const fullVideoUrl = videoUrl.startsWith('http') ? videoUrl : buildApiUrl(SEGMENT_API_URL, videoUrl);
    const playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'btn btn-primary';
    playBtn.textContent = '播放回放';
    playBtn.addEventListener('click', () => {
      const overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.right = '0';
      overlay.style.bottom = '0';
      overlay.style.background = 'rgba(0,0,0,0.6)';
      overlay.style.display = 'flex';
      overlay.style.alignItems = 'center';
      overlay.style.justifyContent = 'center';
      overlay.style.zIndex = '9999';

      const panel = document.createElement('div');
      panel.style.background = '#111';
      panel.style.padding = '12px';
      panel.style.borderRadius = '10px';
      panel.style.width = 'min(920px, 92vw)';
      panel.style.maxHeight = '92vh';
      panel.style.overflow = 'auto';

      const header = document.createElement('div');
      header.style.display = 'flex';
      header.style.justifyContent = 'space-between';
      header.style.alignItems = 'center';
      header.style.gap = '10px';
      header.style.marginBottom = '8px';

      const hText = document.createElement('div');
      hText.style.color = '#fff';
      hText.textContent = `test3.mp4 ｜ ${formatSegmentTimeRange(startSec, endSec)}`;

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn';
      closeBtn.textContent = '关闭';

      header.appendChild(hText);
      header.appendChild(closeBtn);

      const video = document.createElement('video');
      video.controls = true;
      video.preload = 'metadata';
      video.style.width = '100%';
      video.style.maxHeight = '72vh';
      video.src = fullVideoUrl;

      const onLoaded = () => {
        if (Number.isFinite(startSec) && startSec >= 0) {
          try {
            video.currentTime = Math.max(0, startSec);
          } catch {
          }
        }
        video.play().catch(() => {});
      };
      video.addEventListener('loadedmetadata', onLoaded, { once: true });

      const onTimeUpdate = () => {
        if (Number.isFinite(endSec) && endSec > 0 && video.currentTime >= endSec) {
          video.pause();
        }
      };
      video.addEventListener('timeupdate', onTimeUpdate);

      const cleanup = () => {
        video.pause();
        video.removeEventListener('timeupdate', onTimeUpdate);
        overlay.remove();
      };
      closeBtn.addEventListener('click', cleanup);
      overlay.addEventListener('click', (evt) => {
        if (evt.target === overlay) cleanup();
      });

      panel.appendChild(header);
      panel.appendChild(video);
      overlay.appendChild(panel);
      document.body.appendChild(overlay);
    });

    const openLink = document.createElement('a');
    openLink.href = `${fullVideoUrl}#t=${Number.isFinite(startSec) ? startSec : 0}${Number.isFinite(endSec) ? `,${endSec}` : ''}`;
    openLink.target = '_blank';
    openLink.rel = 'noreferrer';
    openLink.textContent = '新窗口打开';

    controls.appendChild(playBtn);
    controls.appendChild(openLink);
    content.appendChild(controls);

    row.appendChild(content);

    const imageUrl = String(record.thumbnail_url || '').trim();
    if (imageUrl) {
      const wrapper = document.createElement('div');
      wrapper.className = 'violation-image-wrapper';
      wrapper.style.maxWidth = '220px';
      const link = document.createElement('a');
      link.className = 'violation-image';
      const full = imageUrl.startsWith('http') ? imageUrl : buildApiUrl(SEGMENT_API_URL, imageUrl);
      link.href = full;
      link.target = '_blank';
      link.rel = 'noreferrer';
      const img = document.createElement('img');
      img.src = full;
      img.alt = '视频区间截图';
      link.appendChild(img);
      wrapper.appendChild(link);
      row.appendChild(wrapper);
    }

    item.appendChild(row);
    list.appendChild(item);
  });

  container.appendChild(list);
  return container;
}

function buildSegmentsResultsNode(description, records) {
  const container = document.createElement('div');
  const summary = document.createElement('div');
  summary.className = 'chat-result-summary';
  const parts = [];
  if (description) parts.push(description);
  parts.push(`命中片段：${Array.isArray(records) ? records.length : 0} 条`);
  summary.textContent = parts.join(' ｜ ');
  container.appendChild(summary);

  const list = document.createElement('div');
  list.className = 'chat-result-list';
  if (!records || records.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-text';
    empty.textContent = '没有找到匹配的片段，可以尝试修改描述或放宽时间范围。';
    list.appendChild(empty);
    container.appendChild(list);
    return container;
  }

  records.forEach((record) => {
    const item = document.createElement('div');
    item.className = 'chat-result-item';

    const row = document.createElement('div');
    row.className = 'violation-row';

    const content = document.createElement('div');
    content.className = 'violation-content';

    const title = document.createElement('div');
    title.className = 'chat-result-title';
    title.textContent = `test3.mp4 ｜ 片段 #${record.segment_id}`;

    const meta = document.createElement('div');
    meta.className = 'chat-result-meta';
    meta.textContent = formatSegmentTimeRange(record.start_sec, record.end_sec);

    content.appendChild(title);
    content.appendChild(meta);

    const caption = String(record.caption || '').trim();
    if (caption) {
      const text = document.createElement('div');
      text.className = 'chat-result-text';
      text.textContent = caption;
      content.appendChild(text);
    }

    const controls = document.createElement('div');
    controls.className = 'chat-result-meta';
    controls.style.display = 'flex';
    controls.style.gap = '10px';
    controls.style.alignItems = 'center';

    const startSec = typeof record.start_sec === 'number' ? record.start_sec : Number(record.start_sec);
    const endSec = typeof record.end_sec === 'number' ? record.end_sec : Number(record.end_sec);

    const videoUrl = String(record.video_url || '').trim() || '/segments/video';
    const fullVideoUrl = videoUrl.startsWith('http') ? videoUrl : buildApiUrl(SEGMENT_API_URL, videoUrl);
    const playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'btn btn-primary';
    playBtn.textContent = '播放片段';
    playBtn.addEventListener('click', () => {
      const overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.right = '0';
      overlay.style.bottom = '0';
      overlay.style.background = 'rgba(0,0,0,0.6)';
      overlay.style.display = 'flex';
      overlay.style.alignItems = 'center';
      overlay.style.justifyContent = 'center';
      overlay.style.zIndex = '9999';

      const panel = document.createElement('div');
      panel.style.background = '#111';
      panel.style.padding = '12px';
      panel.style.borderRadius = '10px';
      panel.style.width = 'min(920px, 92vw)';
      panel.style.maxHeight = '92vh';
      panel.style.overflow = 'auto';

      const header = document.createElement('div');
      header.style.display = 'flex';
      header.style.justifyContent = 'space-between';
      header.style.alignItems = 'center';
      header.style.gap = '10px';
      header.style.marginBottom = '8px';

      const hText = document.createElement('div');
      hText.style.color = '#fff';
      hText.textContent = `test3.mp4 ｜ ${formatSegmentTimeRange(startSec, endSec)}`;

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn';
      closeBtn.textContent = '关闭';

      header.appendChild(hText);
      header.appendChild(closeBtn);

      const video = document.createElement('video');
      video.controls = true;
      video.preload = 'metadata';
      video.style.width = '100%';
      video.style.maxHeight = '72vh';
      video.src = fullVideoUrl;

      const onLoaded = () => {
        if (Number.isFinite(startSec) && startSec >= 0) {
          try {
            video.currentTime = Math.max(0, startSec);
          } catch {
          }
        }
        video.play().catch(() => {});
      };
      video.addEventListener('loadedmetadata', onLoaded, { once: true });

      const onTimeUpdate = () => {
        if (Number.isFinite(endSec) && endSec > 0 && video.currentTime >= endSec) {
          video.pause();
        }
      };
      video.addEventListener('timeupdate', onTimeUpdate);

      const cleanup = () => {
        video.pause();
        video.removeEventListener('timeupdate', onTimeUpdate);
        overlay.remove();
      };
      closeBtn.addEventListener('click', cleanup);
      overlay.addEventListener('click', (evt) => {
        if (evt.target === overlay) cleanup();
      });

      panel.appendChild(header);
      panel.appendChild(video);
      overlay.appendChild(panel);
      document.body.appendChild(overlay);
    });

    const openLink = document.createElement('a');
    openLink.href = `${fullVideoUrl}#t=${Number.isFinite(startSec) ? startSec : 0}${Number.isFinite(endSec) ? `,${endSec}` : ''}`;
    openLink.target = '_blank';
    openLink.rel = 'noreferrer';
    openLink.textContent = '新窗口打开';

    controls.appendChild(playBtn);
    controls.appendChild(openLink);
    content.appendChild(controls);

    row.appendChild(content);

    const imageUrl = String(record.image_url || '').trim();
    if (imageUrl) {
      const wrapper = document.createElement('div');
      wrapper.className = 'violation-image-wrapper';
      wrapper.style.maxWidth = '220px';
      const link = document.createElement('a');
      link.className = 'violation-image';
      const full = imageUrl.startsWith('http') ? imageUrl : buildApiUrl(SEGMENT_API_URL, imageUrl);
      link.href = full;
      link.target = '_blank';
      link.rel = 'noreferrer';
      const img = document.createElement('img');
      img.src = full;
      img.alt = '视频片段截图';
      link.appendChild(img);
      wrapper.appendChild(link);
      row.appendChild(wrapper);
    }

    item.appendChild(row);
    list.appendChild(item);
  });

  container.appendChild(list);
  return container;
}

async function fetchViolationsForSites(siteIds, keyword, startTime, endTime) {
  const ids = Array.isArray(siteIds)
    ? siteIds.map((v) => String(v)).filter((v) => v && v !== 'null' && v !== 'undefined')
    : [];
  if (ids.length === 0) {
    return fetchViolationsForSearch('', keyword, startTime, endTime);
  }
  if (ids.length === 1) {
    return fetchViolationsForSearch(ids[0], keyword, startTime, endTime);
  }
  const results = await Promise.all(
    ids.map((id) => fetchViolationsForSearch(id, keyword, startTime, endTime)),
  );
  const merged = [];
  let total = 0;
  results.forEach((result) => {
    if (result && typeof result.total === 'number') {
      total += result.total;
    }
    if (result && Array.isArray(result.items)) {
      merged.push(...result.items);
    }
  });
  merged.sort((a, b) => {
    const at = new Date(a.detection_time).getTime();
    const bt = new Date(b.detection_time).getTime();
    return bt - at;
  });
  return { total, items: merged.slice(0, 50) };
}

function buildResultsNode(description, total, records) {
  const container = document.createElement('div');
  const summary = document.createElement('div');
  summary.className = 'chat-result-summary';
  const parts = [];
  if (description) {
    parts.push(description);
  }
  if (typeof total === 'number') {
    parts.push(`命中记录：${total} 条`);
  }
  summary.textContent = parts.join(' ｜ ');
  container.appendChild(summary);

  const list = document.createElement('div');
  list.className = 'chat-result-list';

  if (!records || records.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-text';
    empty.textContent = '没有找到匹配的记录，可以尝试放宽时间范围或修改描述。';
    list.appendChild(empty);
    container.appendChild(list);
    return container;
  }

  records.forEach((record) => {
    const item = document.createElement('div');
    item.className = 'chat-result-item';

    const row = document.createElement('div');
    row.className = 'violation-row';

    const content = document.createElement('div');
    content.className = 'violation-content';

    const title = document.createElement('div');
    title.className = 'chat-result-title';
    title.textContent = `工地: ${record.site_name} ｜ 串流: ${record.stream_name}`;

    const meta = document.createElement('div');
    meta.className = 'chat-result-meta';
    const detectionTime = new Date(record.detection_time);
    meta.textContent = `检测时间: ${detectionTime.toLocaleString()}`;

    content.appendChild(title);
    content.appendChild(meta);

    const warningText = formatWarningsText(record.warnings);
    const agentText = record.agent_report || '';
    if (warningText) {
      const warning = document.createElement('div');
      warning.className = 'chat-result-text';
      warning.textContent = warningText;
      content.appendChild(warning);
    }
    if (agentText) {
      const agent = document.createElement('div');
      agent.className = 'chat-result-text';
      agent.textContent = agentText;
      content.appendChild(agent);
    }

    row.appendChild(content);

    if (record.image_path) {
      const placeholder = document.createElement('div');
      placeholder.className = 'violation-image-container';
      row.appendChild(placeholder);
      loadViolationImageInto(placeholder, record.image_path);
    }

    item.appendChild(row);
    list.appendChild(item);
  });
  container.appendChild(list);
  return container;
}

async function runSearchFlow() {
  const input = document.getElementById('search-query');
  const siteSelect = document.getElementById('search-site');
  if (!input || !siteSelect) {
    return;
  }
  const rawQuery = normaliseText(input.value);
  if (!rawQuery) {
    appendMessage('assistant', '请先输入要检索的指令，例如：查询 XX 变电站昨天下午吊车作业的视频。');
    return;
  }
  appendMessage('user', rawQuery);
  input.value = '';

  async function runSegmentsSearch() {
    try {
      appendMessage('assistant', '片段检索中...');
      const intent = await fetchSegmentsIntent(rawQuery);
      const keyword = intent && typeof intent.keyword === 'string' ? cleanSegmentsKeyword(intent.keyword) : '';
      const startSec = intent && typeof intent.start_sec === 'number' ? intent.start_sec : null;
      const endSec = intent && typeof intent.end_sec === 'number' ? intent.end_sec : null;
      const location = intent && typeof intent.location === 'string' ? cleanSegmentsLocation(intent.location) : '';
      const realStartTime = intent && typeof intent.real_start_time === 'string' ? intent.real_start_time.trim() : '';
      const realEndTime = intent && typeof intent.real_end_time === 'string' ? intent.real_end_time.trim() : '';
      const note = intent && typeof intent.note === 'string' ? intent.note.trim() : '';
      const timeRanges = intent && Array.isArray(intent.time_ranges) ? intent.time_ranges : [];
      const ranges = timeRanges.length > 0
        ? timeRanges
        : (intent && Array.isArray(intent.ranges) ? intent.ranges : []);
      const descParts = [];
      if (location) descParts.push(`地点：${location}`);
      if (realStartTime && realEndTime) {
        const rs = new Date(realStartTime);
        const re = new Date(realEndTime);
        if (!Number.isNaN(rs.getTime()) && !Number.isNaN(re.getTime())) {
          descParts.push(`真实时间：${rs.toLocaleString()} - ${re.toLocaleString()}`);
        }
      }
      if (keyword) descParts.push(`关键词：${keyword}`);
      if (Array.isArray(ranges) && ranges.length > 1) {
        const items = ranges.map((r) => {
          if (!r) return '';
          if (typeof r === 'string') return r.trim();
          if (typeof r === 'object') return formatSegmentTimeRange(r.start_sec, r.end_sec).replace('时间片段：', '').trim();
          return '';
        }).filter((v) => v);
        if (items.length > 0) {
          descParts.push(`映射时间段：${items.join('，')}`);
        }
      } else if (Array.isArray(ranges) && ranges.length === 1 && typeof ranges[0] === 'object') {
        descParts.push(formatSegmentTimeRange(ranges[0].start_sec, ranges[0].end_sec));
      } else if (typeof startSec === 'number' || typeof endSec === 'number') {
        descParts.push(formatSegmentTimeRange(startSec, endSec));
      }
      if (note) descParts.push(note);
      appendMessage('assistant', `我理解的检索条件为：${descParts.join(' ｜ ') || '未提取到明确条件，将返回所有片段'}`);
      try {
        const records = await fetchSegmentsClips(keyword, startSec, endSec, ranges);
        const node = buildClipsResultsNode(descParts.join(' ｜ '), Array.isArray(records) ? records : []);
        appendMessage('assistant', '片段检索完成，结果如下：', node);
      } catch {
        const records = await fetchSegments(keyword, startSec, endSec, ranges);
        const node = buildSegmentsResultsNode(descParts.join(' ｜ '), Array.isArray(records) ? records : []);
        appendMessage('assistant', '片段检索完成，结果如下：', node);
      }
      return true;
    } catch {
      appendMessage('assistant', '片段检索失败。');
      return false;
    }
  }

  async function runViolationsSearch() {
    const sites = siteSelect._sitesCache || [];
    const explicitSiteId = siteSelect.value;
    let intent = null;
    try {
      intent = await fetchViolationsIntent(rawQuery, explicitSiteId);
    } catch {
    }

    let siteIds = [];
    if (intent && Array.isArray(intent.site_ids)) {
      siteIds = intent.site_ids.map((v) => String(v)).filter((v) => v);
    }
    if (siteIds.length === 0 && explicitSiteId) {
      siteIds = [String(explicitSiteId)];
    }
    if (siteIds.length === 0) {
      const inferredId = pickSiteIdFromQuery(rawQuery, sites);
      if (inferredId) {
        siteIds = [String(inferredId)];
      }
    }

    const matchedSiteNames = siteIds
      .map((id) => {
        const match = sites.find((s) => String(s.id) === String(id));
        return match ? String(match.name || '').trim() : '';
      })
      .filter((v) => v);

    const fallbackTimeRange = parseTimeRangeFromQuery(rawQuery);
    let timeRange = null;
    if (intent && (intent.start_time || intent.end_time)) {
      const start = intent.start_time ? new Date(intent.start_time) : null;
      const end = intent.end_time ? new Date(intent.end_time) : null;
      const okStart = start && !Number.isNaN(start.getTime());
      const okEnd = end && !Number.isNaN(end.getTime());
      if (okStart || okEnd) {
        const intentRange = { start: okStart ? start : null, end: okEnd ? end : null };
        const hasExplicitDate = queryContainsExplicitDate(rawQuery);
        if (hasExplicitDate || !fallbackTimeRange) {
          timeRange = intentRange;
        } else {
          timeRange = fallbackTimeRange;
        }
      }
    }
    if (!timeRange) {
      timeRange = fallbackTimeRange;
    }

    let keyword = '';
    if (intent && typeof intent.keyword === 'string') {
      keyword = intent.keyword.trim();
    }
    if (!keyword) {
      keyword = buildKeywordFromQuery(rawQuery, matchedSiteNames);
    }

    const descParts = [];
    if (matchedSiteNames.length > 0) {
      descParts.push(`站点：${matchedSiteNames.join('、')}`);
    } else if (siteIds.length > 0) {
      descParts.push(`站点：ID=${siteIds.join(',')}`);
    }
    if (timeRange) {
      descParts.push(describeTimeRange({
        start: timeRange.start && timeRange.start.toISOString ? timeRange.start.toISOString() : '',
        end: timeRange.end && timeRange.end.toISOString ? timeRange.end.toISOString() : '',
      }));
    }
    if (keyword) {
      descParts.push(`关键词：${keyword}`);
    } else {
      descParts.push('关键词：未提取，后台将基于默认匹配尝试检索');
    }
    appendMessage('assistant', `我理解的检索条件为：${descParts.join(' ｜ ')}`);
    const start = timeRange && timeRange.start && timeRange.start.toISOString ? timeRange.start.toISOString() : '';
    const end = timeRange && timeRange.end && timeRange.end.toISOString ? timeRange.end.toISOString() : '';
    const summarySiteId = siteIds.length === 1 ? siteIds[0] : '';
    try {
      appendMessage('assistant', '违规记录检索中...');
      const result = await fetchViolationsForSites(siteIds, keyword, start, end);
      let summaryText = '';
      try {
        const summary = await fetchViolationsSummary(
          summarySiteId,
          keyword,
          start,
          end,
          rawQuery,
        );
        if (summary && typeof summary.summary === 'string') {
          summaryText = summary.summary;
        }
      } catch {
      }
      const description = start || end ? describeTimeRange({ start, end }) : '';
      const node = buildResultsNode(description, result.total, result.items || []);
      if (summaryText) {
        appendMessage('assistant', `违规记录检索完成，智能整理如下：\n${summaryText}`);
        appendMessage('assistant', '以下是命中的具体记录明细：', node);
      } else {
        appendMessage('assistant', '违规记录检索完成，结果如下：', node);
      }
      return true;
    } catch (e) {
      const message =
        e instanceof Error && e.message === 'UNAUTHORIZED'
          ? '当前未登录或登录已过期，请先在页面右上角重新登录后再试。'
          : '检索时发生错误，请稍后重试或检查后端服务是否已启动。';
      appendMessage('assistant', message);
      return false;
    }
  }

  const wantsSegments = shouldUseSegmentsMode(rawQuery);
  let wantsViolations = !wantsSegments || shouldTryViolationsAlongside(rawQuery);

  if (wantsSegments && wantsViolations) {
    appendMessage('assistant', '将同时执行：片段检索 + 违规记录检索。');
  }

  let segmentsOk = false;
  if (wantsSegments) {
    segmentsOk = await runSegmentsSearch();
    if (!segmentsOk && !wantsViolations) {
      appendMessage('assistant', '将尝试按违规记录检索。');
      wantsViolations = true;
    }
  }

  if (wantsViolations) {
    await runViolationsSearch();
    return;
  }

  if (wantsSegments && segmentsOk) {
    return;
  }

  appendMessage('assistant', '未能识别要执行的检索类型，请换个说法再试。');
  return;
}

function bindSearchAssistantEvents() {
  const button = document.getElementById('search-run-button');
  const input = document.getElementById('search-query');
  if (button) {
    button.addEventListener('click', () => {
      runSearchFlow();
    });
  }
  if (input) {
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        runSearchFlow();
      }
    });
  }
}

async function initialiseSearchAssistant() {
  const select = document.getElementById('search-site');
  if (!select) {
    return;
  }
  const sites = await fetchMySitesForSearch();
  select._sitesCache = Array.isArray(sites) ? sites : [];
  renderSearchSiteOptions(select._sitesCache);
}

export async function mountSearchAssistantView() {
  if (!searchMounted) {
    bindSearchAssistantEvents();
    searchMounted = true;
  }
  const messages = document.getElementById('search-messages');
  if (messages) {
    messages.innerHTML = '';
  }
  await initialiseSearchAssistant();
  appendMessage('system', '可以直接输入自然语言，例如：查询 XX 变电站昨天下午吊车作业的视频。');
  appendMessage('system', '演示模式：可输入“开头的片段”、“最后的片段”、“吊车 作业”等来检索 test3.mp4 预计算片段。');
}
