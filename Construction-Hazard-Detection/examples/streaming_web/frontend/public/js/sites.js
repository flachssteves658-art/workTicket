import { ENDPOINTS, buildApiUrl } from './app_endpoints.js';

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

async function readErrorDetail(response) {
  try {
    const data = await response.json();
    if (data && typeof data.detail === 'string' && data.detail) {
      return data.detail;
    }
    if (data && typeof data.message === 'string' && data.message) {
      return data.message;
    }
  } catch {
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function requestOrThrow(url, options) {
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      const detail = await readErrorDetail(response);
      throw new Error(detail);
    }
    return response;
  } catch (error) {
    if (error instanceof Error && /Failed to fetch/i.test(error.message)) {
      throw new Error('无法连接到后端服务，请确认后端已启动');
    }
    throw error;
  }
}

async function fetchSites() {
  const headers = authHeaders();
  if (!headers.Authorization) {
    throw new Error('未登入');
  }
  const response = await requestOrThrow(buildApiUrl(ENDPOINTS.platformApiUrl, '/list_sites'), {
    headers,
  });
  return response.json();
}

async function createSite(name) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeaders(),
  };
  if (!headers.Authorization) {
    throw new Error('未登录');
  }
  await requestOrThrow(buildApiUrl(ENDPOINTS.platformApiUrl, '/create_site'), {
    method: 'POST',
    headers,
    body: JSON.stringify({ name }),
  });
}

async function updateSite(id, newName) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeaders(),
  };
  if (!headers.Authorization) {
    throw new Error('未登入');
  }
  await requestOrThrow(buildApiUrl(ENDPOINTS.platformApiUrl, '/update_site'), {
    method: 'PUT',
    headers,
    body: JSON.stringify({ site_id: id, new_name: newName }),
  });
}

async function deleteSite(id) {
  const headers = {
    'Content-Type': 'application/json',
    ...authHeaders(),
  };
  if (!headers.Authorization) {
    throw new Error('未登入');
  }
  await requestOrThrow(buildApiUrl(ENDPOINTS.platformApiUrl, '/delete_site'), {
    method: 'DELETE',
    headers,
    body: JSON.stringify({ site_id: id }),
  });
}

let selectedSiteId = null;

function emitSelectedSite(site) {
  window.dispatchEvent(
    new CustomEvent('chd:site-selected', {
      detail: site
        ? { siteId: site.id, siteName: site.name }
        : { siteId: null, siteName: '' },
    }),
  );
}

function updateSelectedSiteUI() {
  const items = document.querySelectorAll('.site-item');
  items.forEach((item) => {
    const id = parseInt(item.dataset.siteId || '', 10);
    const isSelected = Number.isFinite(id) && selectedSiteId === id;
    item.classList.toggle('selected', isSelected);
  });
}

function renderSites(sites) {
  const container = document.getElementById('site-list');
  container.innerHTML = '';
  if (!sites || sites.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-text';
    empty.textContent = '目前没有工地资料';
    container.appendChild(empty);
    selectedSiteId = null;
    emitSelectedSite(null);
    return;
  }
  const selectedExists = sites.some((s) => s.id === selectedSiteId);
  if (!selectedExists) {
    selectedSiteId = null;
    emitSelectedSite(null);
  }
  sites.forEach((site) => {
    const item = document.createElement('div');
    item.className = 'site-item';
    item.dataset.siteId = String(site.id);
    if (selectedSiteId === site.id) {
      item.classList.add('selected');
      emitSelectedSite(site);
    }

    const name = document.createElement('div');
    name.className = 'site-name';
    name.textContent = `工地: ${site.name}`;

    const group = document.createElement('div');
    group.className = 'site-group';
    const groupName = site.group_name || '未设定群组';
    group.textContent = `群组: ${groupName}`;

    const actions = document.createElement('div');
    actions.className = 'site-actions';

    const renameButton = document.createElement('button');
    renameButton.type = 'button';
    renameButton.className = 'site-action-button';
    renameButton.textContent = '重命名';
    renameButton.addEventListener('click', async (event) => {
      event.stopPropagation();
      const newName = window.prompt('输入新的工地名称', site.name);
      if (!newName) return;
      try {
        await updateSite(site.id, newName.trim());
        await refreshSites();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        showFormError(message);
      }
    });

    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'site-action-button danger';
    deleteButton.textContent = '删除';
    deleteButton.addEventListener('click', async (event) => {
      event.stopPropagation();
      const confirmed = window.confirm(`确定删除工地「${site.name}」？`);
      if (!confirmed) return;
      try {
        await deleteSite(site.id);
        await refreshSites();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        showFormError(message);
      }
    });

    actions.appendChild(renameButton);
    actions.appendChild(deleteButton);

    item.appendChild(name);
    item.appendChild(group);
    item.appendChild(actions);

    item.addEventListener('click', () => {
      selectedSiteId = site.id;
      emitSelectedSite(site);
      updateSelectedSiteUI();
    });

    container.appendChild(item);
  });
}

function showFormError(message) {
  const errorEl = document.getElementById('site-form-error');
  errorEl.textContent = message;
}

async function refreshSites() {
  try {
    const sites = await fetchSites();
    renderSites(sites);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    showFormError(message);
    renderSites([]);
  }
}

function bindCreateSite() {
  const input = document.getElementById('site-name');
  const button = document.getElementById('create-site-button');
  button.addEventListener('click', async () => {
    const name = input.value.trim();
  if (!name) {
    showFormError('请输入工地名称');
    return;
  }
    showFormError('');
    try {
      await createSite(name);
      input.value = '';
      await refreshSites();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      showFormError(message);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  mountSitesView();
});

let sitesMounted = false;

export async function mountSitesView() {
  if (!sitesMounted) {
    bindCreateSite();
    sitesMounted = true;
  }
  await refreshSites();
}
