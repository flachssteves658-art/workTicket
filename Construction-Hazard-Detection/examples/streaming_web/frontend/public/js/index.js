import { mountViolationsView } from './violations.js';
import { mountSitesView } from './sites.js';
import { mountSearchAssistantView } from './search_assistant.js';
import { ENDPOINTS, buildApiUrl } from './app_endpoints.js';

let accessToken = '';
let refreshToken = '';
let labelsLoaded = false;
let lastKnownLabels = [];

const simulatorState = {
    running: false,
    label: '',
    keys: [],
    timers: [],
    inflight: new Map(),
    sentCount: 0,
    lastStatusAt: 0,
};

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const loginMessage = document.getElementById('login-message');
    const logoutButton = document.getElementById('logout-button');

    const stored = getStoredTokens();
    if (stored) {
        accessToken = stored.accessToken;
        refreshToken = stored.refreshToken;
        showShell();
        ensureDefaultHash();
    } else {
        showLoginOverlay();
    }

    if (loginForm) {
        loginForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const username = usernameInput?.value?.trim() || '';
            const password = passwordInput?.value || '';

            if (!username || !password) {
                setLoginMessage(loginMessage, '请输入用户名和密码');
                return;
            }

            try {
                setLoginMessage(loginMessage, '登录中...');
                const tokens = await login(username, password);
                accessToken = tokens.access_token;
                refreshToken = tokens.refresh_token;
                storeTokens(accessToken, refreshToken);
                setLoginMessage(loginMessage, '');
                labelsLoaded = false;
                showShell();
                ensureDefaultHash();
                await handleRouteChange();
            } catch (error) {
                clearTokens();
                accessToken = '';
                refreshToken = '';
                const message = error instanceof Error ? error.message : String(error);
                setLoginMessage(loginMessage, message || '登录失败，请确认账号密码');
                showLoginOverlay();
            }
        });
    }

    if (logoutButton) {
        logoutButton.addEventListener('click', () => {
            clearTokens();
            accessToken = '';
            refreshToken = '';
            labelsLoaded = false;
            const monitorFrame = document.getElementById('monitor-frame');
            if (monitorFrame) monitorFrame.src = '';
            const configFrame = document.getElementById('config-frame');
            if (configFrame) configFrame.src = '';
            showLoginOverlay();
            window.location.hash = '';
        });
    }

    window.addEventListener('hashchange', () => {
        handleRouteChange();
    });

    setupSimulatorControls();
    handleRouteChange();
});

function showShell() {
    const shell = document.getElementById('app-shell');
    const loginSection = document.getElementById('login-section');
    if (shell) {
        shell.classList.remove('hidden');
        shell.setAttribute('aria-hidden', 'false');
    }
    if (loginSection) {
        loginSection.classList.add('hidden');
    }
}

function showLoginOverlay() {
    const shell = document.getElementById('app-shell');
    const loginSection = document.getElementById('login-section');
    if (shell) {
        shell.classList.add('hidden');
        shell.setAttribute('aria-hidden', 'true');
    }
    if (loginSection) {
        loginSection.classList.remove('hidden');
    }
    setActiveNav('');
    showView('');
}

function ensureDefaultHash() {
    const hash = window.location.hash || '';
    if (!hash || hash === '#') {
        window.location.hash = '#/monitor';
    }
}

function setLoginMessage(element, text) {
    if (element) {
        element.textContent = text;
    }
}

function getStoredTokens() {
    try {
        const raw = localStorage.getItem('chd_tokens');
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (parsed.accessToken && parsed.refreshToken) {
            return {
                accessToken: parsed.accessToken,
                refreshToken: parsed.refreshToken,
            };
        }
        return null;
    } catch {
        return null;
    }
}

function storeTokens(access, refresh) {
    try {
        localStorage.setItem(
            'chd_tokens',
            JSON.stringify({
                accessToken: access,
                refreshToken: refresh,
            }),
        );
    } catch {
    }
}

function clearTokens() {
    try {
        localStorage.removeItem('chd_tokens');
    } catch {
    }
}

async function login(username, password) {
    const response = await fetch(
        buildApiUrl(ENDPOINTS.platformApiUrl, '/login'),
        {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
        },
    );
    if (!response.ok) {
        try {
            const data = await response.json();
            const detail = data && typeof data.detail === 'string'
                ? data.detail
                : '';
            throw new Error(detail || '登录失败，请确认账号密码');
        } catch {
            throw new Error('登录失败，请确认账号密码');
        }
    }
    return response.json();
}

function parseHash(hash) {
    const cleaned = (hash || '').replace(/^#/, '');
    if (!cleaned.startsWith('/')) {
        return { route: 'monitor', query: {} };
    }
    const [path, queryString] = cleaned.split('?', 2);
    const route = (path.replace(/^\//, '') || 'monitor').trim();
    const query = {};
    if (queryString) {
        const params = new URLSearchParams(queryString);
        params.forEach((value, key) => {
            query[key] = value;
        });
    }
    return { route, query };
}

async function handleRouteChange() {
    const stored = getStoredTokens();
    if (!stored) {
        showLoginOverlay();
        return;
    }
    accessToken = stored.accessToken;
    refreshToken = stored.refreshToken;
    showShell();

    const { route, query } = parseHash(window.location.hash);
    const normalized = normalizeRoute(route);
    setActiveNav(normalized);
    showView(normalized);

    if (normalized === 'monitor') {
        await mountMonitorView(query);
        return;
    }
    if (normalized === 'violations') {
        await mountViolationsView();
        return;
    }
    if (normalized === 'sites') {
        await mountSitesView();
        return;
    }
    if (normalized === 'search') {
        await mountSearchAssistantView();
        return;
    }
    if (normalized === 'ticket') {
        mountTicketView();
        return;
    }
}

function normalizeRoute(route) {
    const key = (route || '').toLowerCase();
    if (key === 'violations' || key === 'sites' || key === 'search' || key === 'ticket') {
        return key;
    }
    if (key === 'config') {
        return 'sites';
    }
    return 'monitor';
}

function setActiveNav(route) {
    const links = document.querySelectorAll('.nav-link');
    links.forEach((link) => {
        const key = link.getAttribute('data-route') || '';
        if (key && route && key === route) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

function showView(route) {
    const views = document.querySelectorAll('.view[data-view]');
    views.forEach((view) => {
        const key = view.getAttribute('data-view') || '';
        const isActive = route && key === route;
        if (isActive) {
            view.classList.remove('hidden');
            view.setAttribute('aria-hidden', 'false');
        } else {
            view.classList.add('hidden');
            view.setAttribute('aria-hidden', 'true');
        }
    });
}

async function mountMonitorView(query) {
    const cameraGrid = document.getElementById('camera-grid');
    const monitorFrame = document.getElementById('monitor-frame');
    if (!cameraGrid) {
        return;
    }
    if (monitorFrame) {
        monitorFrame.srcdoc = buildMonitorFrameDoc({
            title: '实时预览',
            subtitle: '加载标签中...',
        });
        monitorFrame.src = 'about:blank';
    }
    if (!labelsLoaded) {
        let labels = [];
        try {
            labels = await fetchLabels();
        } catch {
            showLoginOverlay();
            return;
        }
        lastKnownLabels = Array.isArray(labels) ? labels : [];
        cameraGrid.innerHTML = '';
        renderLabels(cameraGrid, labels);
        labelsLoaded = true;
    }

    const queryLabel = typeof query.label === 'string' ? query.label : '';
    const fallbackLabel = Array.isArray(lastKnownLabels) && lastKnownLabels.length > 0
        ? String(lastKnownLabels[0] || '')
        : '';
    const label = queryLabel || fallbackLabel;

    if (!queryLabel && label) {
        window.location.hash = `#/monitor?label=${encodeURIComponent(label)}`;
        return;
    }

    highlightSelectedLabel(label);
    if (monitorFrame) {
        if (!label) {
            monitorFrame.srcdoc = buildMonitorFrameDoc({
                title: '实时预览',
                subtitle: '暂无可用标签，请先创建工地并配置串流',
            });
            monitorFrame.src = 'about:blank';
            return;
        }

        const labelExists = Array.isArray(lastKnownLabels)
            ? lastKnownLabels.some((v) => String(v) === String(label))
            : false;
        if (!labelExists) {
            monitorFrame.srcdoc = buildMonitorFrameDoc({
                title: '实时预览',
                subtitle: '所选标签不存在或无权限访问',
            });
            monitorFrame.src = 'about:blank';
            return;
        }

        if (label) {
            monitorFrame.removeAttribute('srcdoc');
            monitorFrame.src = `/label.html?label=${encodeURIComponent(label)}`;
        }
    }
}

function buildMonitorFrameDoc({ title, subtitle }) {
    const safeTitle = String(title || '');
    const safeSubtitle = String(subtitle || '');
    return `<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(safeTitle)}</title>
  <style>
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      background: radial-gradient(900px 620px at 12% 18%, rgba(59, 130, 246, 0.10) 0%, rgba(59, 130, 246, 0) 58%),
                  radial-gradient(1200px 700px at 15% 0%, rgba(251, 191, 36, 0.06) 0%, rgba(251, 191, 36, 0) 55%),
                  linear-gradient(180deg, #071a3a 0%, #02061a 100%);
      color: rgba(226, 232, 240, 0.96);
      display: grid;
      place-items: center;
      padding: 16px;
      box-sizing: border-box;
    }
    .card {
      width: min(520px, 92vw);
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: rgba(6, 18, 52, 0.86);
      padding: 14px;
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.35);
    }
    .title { font-weight: 800; font-size: 15px; margin: 0; }
    .sub { margin: 6px 0 0; font-size: 12px; color: rgba(148, 163, 184, 0.92); line-height: 1.6; }
  </style>
</head>
<body>
  <div class="card">
    <h1 class="title">${escapeHtml(safeTitle)}</h1>
    <p class="sub">${escapeHtml(safeSubtitle)}</p>
  </div>
</body>
</html>`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

async function fetchLabels() {
    const headers = {};
    if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
    }
    const response = await fetch(
        buildApiUrl(ENDPOINTS.streamingBackendApiUrl, '/labels'),
        { headers },
    );
    if (response.status === 401 || response.status === 403) {
        clearTokens();
        accessToken = '';
        refreshToken = '';
        throw new Error('未授权或登录已过期，请重新登录');
    }
    if (!response.ok) {
        throw new Error('读取标签失败');
    }
    const data = await response.json();
    return data.labels || [];
}

function renderLabels(cameraGrid, labels) {
    labels.forEach((label) => {
        const cameraDiv = createCameraDiv(label);
        cameraGrid.appendChild(cameraDiv);
    });
}

function setupSimulatorControls() {
    const toggleButton = document.getElementById('simulate-toggle');
    if (!toggleButton) {
        return;
    }
    toggleButton.addEventListener('click', async () => {
        if (simulatorState.running) {
            stopSimulator();
            return;
        }
        await startSimulator();
    });
    updateSimulatorUI();
}

function updateSimulatorUI() {
    const toggleButton = document.getElementById('simulate-toggle');
    if (toggleButton) {
        toggleButton.textContent = simulatorState.running ? '停止模拟流' : '启动模拟流';
        toggleButton.classList.toggle('primary', simulatorState.running);
        toggleButton.classList.toggle('secondary', !simulatorState.running);
    }
}

function setSimulatorStatus(text, kind = '') {
    const status = document.getElementById('simulate-status');
    if (!status) {
        return;
    }
    status.textContent = text || '';
    status.classList.remove('success', 'error');
    if (kind === 'success') {
        status.classList.add('success');
    }
    if (kind === 'error') {
        status.classList.add('error');
    }
}

function getSimulatorConfigFromUI() {
    const countInput = document.getElementById('simulate-count');
    const intervalInput = document.getElementById('simulate-interval');
    const count = Math.max(1, Math.min(12, Number(countInput && countInput.value) || 4));
    const intervalMs = Math.max(200, Math.min(5000, Number(intervalInput && intervalInput.value) || 800));
    return { count, intervalMs };
}

function getSelectedLabelFromHash() {
    const { route, query } = parseHash(window.location.hash);
    if (normalizeRoute(route) !== 'monitor') {
        return '';
    }
    return typeof query.label === 'string' ? query.label : '';
}

async function resolveSimulatorLabel() {
    const fromHash = getSelectedLabelFromHash();
    if (fromHash) {
        return fromHash;
    }
    if (Array.isArray(lastKnownLabels) && lastKnownLabels.length > 0) {
        return String(lastKnownLabels[0] || '');
    }
    try {
        const labels = await fetchLabels();
        if (Array.isArray(labels) && labels.length > 0) {
            lastKnownLabels = labels;
            return String(labels[0] || '');
        }
    } catch {
    }
    return '';
}

function buildSimulatorKeys(count) {
    const keys = [];
    for (let i = 0; i < count; i += 1) {
        keys.push(`DEMO-CAM-${String(i + 1).padStart(2, '0')}`);
    }
    return keys;
}

async function cleanupSimulatedStreams(label) {
    if (!accessToken) {
        return null;
    }
    try {
        const response = await fetch(
            `${buildApiUrl(ENDPOINTS.streamingBackendApiUrl, '/simulator/cleanup')}?label=${encodeURIComponent(label)}`,
            {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${accessToken}` },
            },
        );
        if (response.status === 401 || response.status === 403) {
            clearTokens();
            accessToken = '';
            refreshToken = '';
            showLoginOverlay();
            return null;
        }
        if (!response.ok) {
            return null;
        }
        return response.json();
    } catch {
        return null;
    }
}

async function startSimulator() {
    const stored = getStoredTokens();
    if (!stored) {
        setSimulatorStatus('未登录，无法启动模拟流', 'error');
        return;
    }
    accessToken = stored.accessToken;
    refreshToken = stored.refreshToken;

    const { count, intervalMs } = getSimulatorConfigFromUI();
    const label = await resolveSimulatorLabel();
    if (!label) {
        setSimulatorStatus('没有可用标签（label），请先创建/授权工地', 'error');
        return;
    }

    if (!getSelectedLabelFromHash()) {
        window.location.hash = `#/monitor?label=${encodeURIComponent(label)}`;
    }

    setSimulatorStatus('正在清理历史模拟流残留...', 'success');
    await cleanupSimulatedStreams(label);
    const monitorFrame = document.getElementById('monitor-frame');
    if (monitorFrame) {
        monitorFrame.src = `/label.html?label=${encodeURIComponent(label)}&r=${Date.now()}`;
    }

    simulatorState.running = true;
    simulatorState.label = label;
    simulatorState.keys = buildSimulatorKeys(count);
    simulatorState.sentCount = 0;
    simulatorState.lastStatusAt = 0;
    simulatorState.inflight = new Map();
    simulatorState.timers = [];
    updateSimulatorUI();

    setSimulatorStatus(`模拟流已启动：${label} / ${simulatorState.keys.length} 路`, 'success');

    simulatorState.keys.forEach((key, index) => {
        void pushSimulatedFrame({ label, key, keyIndex: index });
        const timer = window.setInterval(() => {
            void pushSimulatedFrame({ label, key, keyIndex: index });
        }, intervalMs);
        simulatorState.timers.push(timer);
    });
}

function stopSimulator() {
    simulatorState.running = false;
    simulatorState.timers.forEach((t) => window.clearInterval(t));
    simulatorState.timers = [];
    simulatorState.keys = [];
    simulatorState.label = '';
    simulatorState.inflight = new Map();
    updateSimulatorUI();
    setSimulatorStatus('模拟流已停止', '');
}

function updateSimulatorProgress() {
    const now = Date.now();
    if (now - simulatorState.lastStatusAt < 800) {
        return;
    }
    simulatorState.lastStatusAt = now;
    const label = simulatorState.label;
    const count = simulatorState.keys.length;
    setSimulatorStatus(`模拟流运行中：${label} / ${count} 路，已发送 ${simulatorState.sentCount} 帧`, 'success');
}

async function pushSimulatedFrame({ label, key, keyIndex }) {
    if (!simulatorState.running) {
        return;
    }
    if (!accessToken) {
        setSimulatorStatus('未登录，无法推送帧', 'error');
        stopSimulator();
        return;
    }
    if (simulatorState.inflight.get(key)) {
        return;
    }
    simulatorState.inflight.set(key, true);
    try {
        const frame = await buildSimulatedFrame({ label, key, keyIndex });
        const form = new FormData();
        form.append('label', label);
        form.append('key', key);
        form.append('file', frame.blob, `${key}.jpg`);
        form.append('warnings_json', frame.warningsJson);
        form.append('cone_polygons_json', frame.conePolygonsJson);
        form.append('pole_polygons_json', frame.polePolygonsJson);
        form.append('detection_items_json', frame.detectionItemsJson);
        form.append('width', String(frame.width));
        form.append('height', String(frame.height));

        const response = await fetch(
            buildApiUrl(ENDPOINTS.streamingBackendApiUrl, '/frames'),
            {
            method: 'POST',
            headers: { Authorization: `Bearer ${accessToken}` },
            body: form,
            },
        );
        if (response.status === 401 || response.status === 403) {
            clearTokens();
            accessToken = '';
            refreshToken = '';
            setSimulatorStatus('登录已过期，已停止模拟流', 'error');
            stopSimulator();
            showLoginOverlay();
            return;
        }
        if (!response.ok) {
            setSimulatorStatus(`推送失败：${response.status} ${response.statusText}`, 'error');
            return;
        }
        simulatorState.sentCount += 1;
        updateSimulatorProgress();
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error || '');
        setSimulatorStatus(`推送异常：${message}`, 'error');
    } finally {
        simulatorState.inflight.set(key, false);
    }
}

function pickWarningPayload(keyIndex, tick) {
    const pool = [
        'warning_close_to_machinery',
        'warning_close_to_vehicle',
        'warning_people_in_controlled_area',
        'warning_people_in_utility_pole_controlled_area',
        'detect_machinery_close_to_pole',
        'warning_no_hardhat',
        'warning_no_safety_vest',
    ];
    const primary = pool[keyIndex % pool.length];
    const secondary = pool[(keyIndex + 3) % pool.length];
    const obj = {};
    obj[primary] = { count: 1 + (tick % 2) };
    if (tick % 3 === 0) {
        obj[secondary] = { count: 1 };
    }
    return JSON.stringify(obj);
}

function buildDetectionItems({ width, height, keyIndex, tick }) {
    const items = [];
    const base = (keyIndex * 97 + tick * 13) % 1000;
    const count = 2 + ((base % 3) || 0);
    const classes = [5, 2, 4, 8, 10];
    for (let i = 0; i < count; i += 1) {
        const seed = base + i * 71;
        const w = 140 + (seed % 180);
        const h = 180 + ((seed * 3) % 220);
        const x1 = Math.max(0, Math.min(width - w - 1, (seed * 7) % width));
        const y1 = Math.max(0, Math.min(height - h - 1, (seed * 11) % height));
        const x2 = x1 + w;
        const y2 = y1 + h;
        const conf = 0.55 + ((seed % 35) / 100);
        const cls = classes[(seed + keyIndex) % classes.length];
        items.push([x1, y1, x2, y2, conf, cls]);
    }
    return items;
}

async function buildSimulatedFrame({ label, key, keyIndex }) {
    const width = 960;
    const height = 540;
    const tick = Math.floor(Date.now() / 1000);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        throw new Error('无法创建画布');
    }

    const hue = (keyIndex * 53 + tick * 7) % 360;
    const grad = ctx.createLinearGradient(0, 0, width, height);
    grad.addColorStop(0, `hsl(${hue}, 68%, 14%)`);
    grad.addColorStop(1, `hsl(${(hue + 40) % 360}, 72%, 10%)`);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = 'rgba(2, 6, 23, 0.55)';
    ctx.fillRect(30, 28, width - 60, 110);

    ctx.font = '700 38px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
    ctx.fillStyle = 'rgba(248, 250, 252, 0.96)';
    ctx.fillText(key, 50, 72);

    ctx.font = '600 16px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
    ctx.fillStyle = 'rgba(226, 232, 240, 0.9)';
    const timeText = new Date().toLocaleString();
    ctx.fillText(label, 50, 102);
    ctx.fillText(timeText, 50, 126);

    const detectionItems = buildDetectionItems({ width, height, keyIndex, tick });

    const blob = await new Promise((resolve, reject) => {
        canvas.toBlob(
            (b) => (b ? resolve(b) : reject(new Error('生成图片失败'))),
            'image/jpeg',
            0.86,
        );
    });

    return {
        blob,
        warningsJson: pickWarningPayload(keyIndex, tick),
        detectionItemsJson: JSON.stringify(detectionItems),
        conePolygonsJson: '[]',
        polePolygonsJson: '[]',
        width,
        height,
    };
}

function createCameraDiv(label) {
    const cameraDiv = createDivElement('camera');
    cameraDiv.dataset.label = String(label);
    const link = createLinkElement(`#/monitor?label=${encodeURIComponent(label)}`, [
        createTitleElement(label),
        createDescriptionElement('点击查看实时画面'),
    ]);
    link.classList.add('camera-link');
    cameraDiv.appendChild(link);
    return cameraDiv;
}

function highlightSelectedLabel(label) {
    const tiles = document.querySelectorAll('.camera[data-label]');
    tiles.forEach((tile) => {
        const v = tile.getAttribute('data-label') || '';
        if (label && v === label) {
            tile.classList.add('selected');
        } else {
            tile.classList.remove('selected');
        }
    });
}

function mountConfigView() {
    const configFrame = document.getElementById('config-frame');
    if (configFrame && !configFrame.src) {
        configFrame.src = '/config.html';
    }
}

function mountTicketView() {
    const ticketFrame = document.getElementById('ticket-frame');
    if (ticketFrame) {
        const current = ticketFrame.getAttribute('src') || '';
        if (!current) {
            ticketFrame.setAttribute('src', ENDPOINTS.ticketUiUrl);
        }
    }
    const ticketOpenLink = document.getElementById('ticket-open-link');
    if (ticketOpenLink) {
        ticketOpenLink.setAttribute('href', ENDPOINTS.ticketUiUrl);
    }
}

function createDivElement(className) {
    const div = document.createElement('div');
    div.className = className;
    return div;
}

function createLinkElement(href, children = []) {
    const link = document.createElement('a');
    link.href = href;
    children.forEach((child) => link.appendChild(child));
    return link;
}

function createTitleElement(text) {
    const title = document.createElement('h2');
    title.textContent = text;
    return title;
}

function createDescriptionElement(text) {
    const description = document.createElement('p');
    description.textContent = text;
    return description;
}
