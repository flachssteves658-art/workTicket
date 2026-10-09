/* ----------------------------------
   Global Variables & Element Selectors
------------------------------------- */
import { ENDPOINTS, buildApiUrl } from './app_endpoints.js';

const configContainer = document.getElementById("config-container");
const editBtn = document.getElementById("edit-btn");
const addConfigBtn = document.getElementById("add-config-btn");
const saveBtn = document.getElementById("save-btn");
const cancelBtn = document.getElementById("cancel-btn");
const formControls = document.getElementById("form-controls");
const selectedSiteText = document.getElementById("config-selected-site");
const clearSiteBtn = document.getElementById("config-clear-site");

let allConfigData = [];
let isEditing = false;
let activeSiteFilter = "";

/* ----------------------------------
   Utility Functions
------------------------------------- */
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

function showConfigError(message) {
  if (!configContainer) return;
  configContainer.innerHTML = "";
  const error = document.createElement("div");
  error.className = "empty-text";
  error.textContent = message || "加载配置失败";
  configContainer.appendChild(error);
}

function getTodayDate() {
  // Fetch today's date in ISO format (YYYY-MM-DD)
  return new Date().toISOString().split("T")[0];
}

const detectionLabelMap = {
  detect_no_safety_vest_or_helmet: "无背心/安全帽",
  detect_near_machinery_or_vehicle: "靠近机具/车辆",
  detect_in_restricted_area: "闯入管制区",
  detect_in_utility_pole_restricted_area: "闯入电杆区",
  detect_machinery_close_to_pole: "机具靠近电杆"
};

function formatDetectionItemName(key) {
  // Replace underscores with spaces and capitalise each word's first letter
  return detectionLabelMap[key] || key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function getNoExpireDateTextInput(item) {
  return item.querySelector(".expire-date-container input[type='text']");
}

// Custom logging function to avoid direct console usage
function logError(error) {
  // Example: Send error to external logging service or remove for production
  // console.error(error);
}

/* ----------------------------------
   Fetch & Render
------------------------------------- */
async function fetchConfig() {
  try {
    const headers = authHeaders();
    if (!headers.Authorization) {
      showConfigError("未登录");
      return;
    }
    const response = await fetch(
      buildApiUrl(ENDPOINTS.streamingBackendApiUrl, '/config'),
      { headers },
    );
    if (!response.ok) {
      const detail = await readErrorDetail(response);
      throw new Error(detail || "加载配置失败");
    }
    const data = await response.json();

    allConfigData = (data.config || []).map((cfg) => {
      const rawNotifications = cfg && typeof cfg === "object" ? cfg.notifications : undefined;
      let notifications = [];
      if (Array.isArray(rawNotifications)) {
        notifications = rawNotifications
          .map((n) => ({
            token: (n && typeof n === "object" ? n.token : "") || "",
            language: (n && typeof n === "object" ? n.language : "") || "en"
          }))
          .filter((n) => n.token || n.language);
      } else if (rawNotifications && typeof rawNotifications === "object") {
        notifications = Object.entries(rawNotifications).map(([token, language]) => ({
          token,
          language
        }));
      }
      return {
        ...cfg,
        notifications
      };
    });

    renderConfigForm();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    showConfigError(message);
    logError(error); // Replaces console.error
  }
}

/**
 * Render the entire configuration form
 */
function renderConfigForm() {
  configContainer.innerHTML = ""; // Clear existing config items

  const visibleConfigs = allConfigData
    .map((config, index) => ({ config, index }))
    .filter(({ config }) => !activeSiteFilter || config.site === activeSiteFilter);

  if (visibleConfigs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = activeSiteFilter
      ? `当前工地「${activeSiteFilter}」没有配置`
      : "暂无配置";
    configContainer.appendChild(empty);
    return;
  }

  visibleConfigs.forEach(({ config, index }) => {
    const container = createConfigItem(config, index);
    configContainer.appendChild(container);
  });
}

/**
 * Create a single config item DOM node
 */
function createConfigItem(config, index) {
  const configItemTemplate = document.getElementById("config-item-template");
  const container = configItemTemplate.content.cloneNode(true);
  const item = container.querySelector(".config-item");
  item.dataset.configIndex = String(index);

  initFormFields(item, config);
  setupLLMEvents(item);
  initNotifications(item, config, index);
  handleExpireDateEditMode(item, config);
  toggleEditButtons(item);
  toggleFormFields(item);
  initCollapsibleToggle(item);

  return container;
}

/* ----------------------------------
   Collapsible Toggle
------------------------------------- */
/**
 * Initialize collapsible toggle for a config item
 */
function initCollapsibleToggle(item) {
  const toggleBtn = item.querySelector('.toggle-config-btn');
  const configDetails = item.querySelector('.config-details');
  
  if (toggleBtn && configDetails) {
    const icon = toggleBtn.querySelector('i');
    
    // Default to collapsed
    configDetails.classList.add('collapsed');
    toggleBtn.setAttribute('aria-expanded', 'false');
    if (icon) {
      icon.classList.remove('fa-chevron-down');
      icon.classList.add('fa-chevron-right');
    }

    toggleBtn.addEventListener('click', () => {
      const isCollapsed = configDetails.classList.contains('collapsed');
      
      if (isCollapsed) {
        configDetails.classList.remove('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'true');
        if (icon) {
          icon.classList.remove('fa-chevron-right');
          icon.classList.add('fa-chevron-down');
        }
      } else {
        configDetails.classList.add('collapsed');
        toggleBtn.setAttribute('aria-expanded', 'false');
        if (icon) {
          icon.classList.remove('fa-chevron-down');
          icon.classList.add('fa-chevron-right');
        }
      }
    });
  }
}

/* ----------------------------------
   Form Field Initialisation
------------------------------------- */
/**
 * Initialise form fields with default or existing config values
 */
function initFormFields(item, config) {
  setBasicFields(item, config);
  setWorkHours(item, config);
  setExpireDateUI(item, config);
  setDetectAndRedisFlags(item, config);
  setLLMFields(item, config);
  setDetectionItemsUI(item, config);
}

/**
 * Set basic text/select fields like site, stream_name, video_url, model_key
 */
function setBasicFields(item, config) {
  const siteInput = item.querySelector("input[name='site']");
  const streamNameInput = item.querySelector("input[name='stream_name']");
  const videoUrlInput = item.querySelector("input[name='video_url']");
  const modelKeySelect = item.querySelector("select[name='model_key']");

  siteInput.value = config.site || "";
  streamNameInput.value = config.stream_name || "";
  videoUrlInput.value = config.video_url || "";
  modelKeySelect.value = config.model_key || "yolo11n";
}

/**
 * Set work hours (start/end)
 */
function setWorkHours(item, config) {
  const workStartHourSelect = item.querySelector("select[name='work_start_hour']");
  const workEndHourSelect = item.querySelector("select[name='work_end_hour']");

  workStartHourSelect.value =
    config.work_start_hour !== undefined ? config.work_start_hour : 7;
  workEndHourSelect.value =
    config.work_end_hour !== undefined ? config.work_end_hour : 18;
}

/**
 * Set expire date UI (text input vs. "No Expire Date" text)
 */
function setExpireDateUI(item, config) {
  const expireDateInput = item.querySelector("input[name='expire_date']");
  const noExpireDateText = getNoExpireDateTextInput(item);

  if (config.expire_date === "No Expire Date") {
    expireDateInput.value = "";
    expireDateInput.style.display = "none";
    if (noExpireDateText) noExpireDateText.style.display = "";
  } else {
    expireDateInput.value = config.expire_date || getTodayDate();
    expireDateInput.style.display = "";
    if (noExpireDateText) noExpireDateText.style.display = "none";
  }
}

/**
 * Set detect_with_server & store_in_redis checkboxes
 */
function setDetectAndRedisFlags(item, config) {
  const detectWithServerCheckbox = item.querySelector("input[name='detect_with_server']");
  const storeInRedisCheckbox = item.querySelector("input[name='store_in_redis']");

  detectWithServerCheckbox.checked = !!config.detect_with_server;
  storeInRedisCheckbox.checked = !!config.store_in_redis;
}

function setLLMFields(item, config) {
  const llmEnabledCheckbox = item.querySelector("input[name='llm_refine_enabled']");
  const llmProviderSelect = item.querySelector("select[name='llm_provider']");
  const llmBaseUrlInput = item.querySelector("input[name='llm_base_url']");
  const llmModelInput = item.querySelector("input[name='llm_model']");
  const llmLowConfInput = item.querySelector("input[name='llm_low_conf_threshold']");

  if (llmEnabledCheckbox) {
    llmEnabledCheckbox.checked = !!config.llm_refine_enabled;
  }
  if (llmProviderSelect) {
    const provider = config.llm_provider || "aliyun";
    llmProviderSelect.value = provider;
    if (llmBaseUrlInput) {
      const baseUrl = config.llm_base_url || getLLMBaseUrlForProvider(provider);
      llmBaseUrlInput.value = baseUrl || "";
    }
  }
  if (llmModelInput) {
    llmModelInput.value = config.llm_model || "qwen-vl-max-2025-08-13";
  }
  if (llmLowConfInput) {
    const lowConf = config.llm_low_conf_threshold;
    llmLowConfInput.value =
      typeof lowConf === "number" && Number.isFinite(lowConf) ? String(lowConf) : "0.25";
  }
}

function getLLMBaseUrlForProvider(provider) {
  if (provider === "ollama") {
    return "http://localhost:11434";
  }
  if (provider === "aliyun") {
    return "https://dashscope.aliyuncs.com/compatible-mode/v1";
  }
  return "";
}

function setupLLMEvents(item) {
  const llmProviderSelect = item.querySelector("select[name='llm_provider']");
  const llmBaseUrlInput = item.querySelector("input[name='llm_base_url']");

  if (llmProviderSelect && llmBaseUrlInput) {
    llmProviderSelect.addEventListener("change", () => {
      const provider = llmProviderSelect.value;
      llmBaseUrlInput.value = getLLMBaseUrlForProvider(provider);
    });
  }
}

/**
 * Set detection items (checkboxes + label)
 */
function setDetectionItemsUI(item, config) {
  const detectionMap =
    (config && typeof config === "object" && config.detection_items && typeof config.detection_items === "object")
      ? config.detection_items
      : {};
  const detectionItems = item.querySelectorAll(
    "input[type='checkbox'][name^='detect_']:not([name='detect_with_server']):not([name='store_in_redis'])"
  );

  detectionItems.forEach((checkbox) => {
    const fromMap = detectionMap[checkbox.name];
    if (fromMap !== undefined) {
      checkbox.checked = !!fromMap;
    } else if (config && typeof config === "object") {
      checkbox.checked = !!config[checkbox.name];
    } else {
      checkbox.checked = false;
    }
    // Update label text
    const label = checkbox.parentElement;
    label.lastChild.textContent = formatDetectionItemName(checkbox.name);
  });
}

/* ----------------------------------
   Notifications
------------------------------------- */
function initNotifications(item, config, index) {
  const notificationItemTemplate = document.getElementById("notification-item-template");
  const notificationsContainer = item.querySelector(".notifications-container");

  notificationsContainer.innerHTML = "";

  const notifications = Array.isArray(config.notifications) ? config.notifications : [];
  notifications.forEach((notification, notifIndex) => {
    const notifEl = notificationItemTemplate.content.cloneNode(true);
    const notifItem = notifEl.querySelector(".notification-item");
    const lineTokenInput = notifItem.querySelector("input[name='line_token']");
    const languageSelect = notifItem.querySelector("select[name='language']");
    const deleteNotifBtn = notifItem.querySelector(".delete-notification");

    lineTokenInput.value = notification.token;
    languageSelect.value = notification.language;
    lineTokenInput.setAttribute("data-notif-index", notifIndex);
    languageSelect.setAttribute("data-notif-index", notifIndex);

    deleteNotifBtn.style.display = isEditing ? "block" : "none";
    notificationsContainer.appendChild(notifEl);
  });

  setupNotificationEvents(notificationsContainer, index);
}

/**
 * Set up notification event listeners
 *
 * @param {HTMLElement} notificationsContainer - The container for notifications.
 * @param {number} configIndex - The index of the config in configData.
 */
function setupNotificationEvents(notificationsContainer, configIndex) {
  // Delete notification event
  notificationsContainer.addEventListener("click", (event) => {
    if (event.target.closest(".delete-notification")) {
      const notificationItem = event.target.closest(".notification-item");
      const notifIndex = parseInt(
        notificationItem.querySelector("input[name='line_token']").getAttribute("data-notif-index"),
        10
      );
      removeNotification(configIndex, notifIndex);
    }
  });

  // Add notification event
  const addNotificationBtn = notificationsContainer.parentElement.querySelector(".add-notification");
  addNotificationBtn.addEventListener("click", () => {
    addNotification(configIndex);
  });
}

/**
 * Add a new notification
 *
 * @param {number} configIndex - The index of the config in configData.
 */
function addNotification(configIndex) {
  updateAllConfigDataFromForm();
  const target = allConfigData[configIndex];
  if (!target) return;
  if (!Array.isArray(target.notifications)) target.notifications = [];
  target.notifications.push({ token: "", language: "en" });
  renderConfigForm();
}

/**
 * Remove a notification
 *
 * @param {number} configIndex - The index of the config in configData.
 * @param {number} notifIndex - The index of the notification to remove.
 */
function removeNotification(configIndex, notifIndex) {
  updateAllConfigDataFromForm();
  const target = allConfigData[configIndex];
  if (!target || !Array.isArray(target.notifications)) return;
  target.notifications.splice(notifIndex, 1);
  renderConfigForm();
}

/* ----------------------------------
   Expire Date Edit Mode
------------------------------------- */
function handleExpireDateEditMode(item, config) {
  if (isEditing) {
    createNoExpireDateCheckbox(item, config);
  } else {
    handleNonEditExpireDate(item, config);
  }
}

/**
 * Create & handle "No Expire Date" checkbox in edit mode
 */
function createNoExpireDateCheckbox(item, config) {
  const expireDateContainer = item.querySelector(".expire-date-container");
  const expireDateInput = item.querySelector("input[name='expire_date']");
  const noExpireDateText = getNoExpireDateTextInput(item);

  const noExpireDateCheckbox = document.createElement("input");
  noExpireDateCheckbox.type = "checkbox";
  noExpireDateCheckbox.name = "no_expire_date";
  noExpireDateCheckbox.checked = config.expire_date === "No Expire Date";
  noExpireDateCheckbox.id = `no-expire-date-${Math.random()}`; // or other unique ID

  const noExpireDateLabel = document.createElement("label");
  noExpireDateLabel.htmlFor = noExpireDateCheckbox.id;
  noExpireDateLabel.appendChild(noExpireDateCheckbox);
  noExpireDateLabel.appendChild(document.createTextNode(" 无过期时间"));

  expireDateContainer.appendChild(document.createElement("br"));
  expireDateContainer.appendChild(noExpireDateLabel);

  // Initial state
  toggleNoExpireDate(expireDateInput, noExpireDateText, noExpireDateCheckbox.checked);

  noExpireDateCheckbox.addEventListener("change", () => {
    toggleNoExpireDate(expireDateInput, noExpireDateText, noExpireDateCheckbox.checked);
    // If the expire_date is empty, set it to today
    if (!config.expire_date || config.expire_date === "No Expire Date") {
      expireDateInput.value = getTodayDate();
      config.expire_date = getTodayDate();
    }
  });
}

/**
 * Toggle visibility of expire date input and "No Expire Date" text
 *
 * @param {HTMLInputElement} expireDateInput - The expire date input field.
 * @param {HTMLInputElement} noExpireDateText - The "No Expire Date" text input.
 * @param {boolean} isNoExpire - Whether "No Expire Date" is selected.
 */
function toggleNoExpireDate(expireDateInput, noExpireDateText, isNoExpire) {
  if (isNoExpire) {
    expireDateInput.value = "";
    expireDateInput.style.display = "none";
    if (noExpireDateText) noExpireDateText.style.display = "";
  } else {
    expireDateInput.style.display = "";
    if (noExpireDateText) noExpireDateText.style.display = "none";
  }
}

/**
 * Show/hide "No Expire Date" text for non-edit mode
 */
function handleNonEditExpireDate(item, config) {
  const expireDateInput = item.querySelector("input[name='expire_date']");
  const noExpireDateText = getNoExpireDateTextInput(item);

  toggleNoExpireDate(expireDateInput, noExpireDateText, config.expire_date === "No Expire Date");
}

/* ----------------------------------
   Buttons & Edit Mode
------------------------------------- */
function toggleEditButtons(item) {
  const deleteConfigBtn = item.querySelector(".delete-config-btn");
  const addNotificationBtn = item.querySelector(".add-notification");

  if (isEditing) {
    deleteConfigBtn.style.display = "block";
    addNotificationBtn.style.display = "inline-block";
  } else {
    deleteConfigBtn.style.display = "none";
    addNotificationBtn.style.display = "none";
  }

  deleteConfigBtn.addEventListener("click", () => handleDeleteConfig(item));
}

/**
 * Handle delete config
 */
function handleDeleteConfig(item) {
  updateAllConfigDataFromForm();
  const idx = Number(item.dataset.configIndex);
  if (!Number.isFinite(idx)) return;
  allConfigData.splice(idx, 1);
  renderConfigForm();
}

/**
 * Enable or disable input fields based on edit mode
 */
function toggleFormFields(item) {
  const fields = item.querySelectorAll("input, select");
  fields.forEach((f) => {
    if (!isEditing) {
      f.setAttribute("disabled", "true");
    } else {
      f.removeAttribute("disabled");
    }
  });
}

/* ----------------------------------
   Update & Validation
------------------------------------- */
function updateAllConfigDataFromForm() {
  const items = configContainer ? Array.from(configContainer.querySelectorAll(".config-item")) : [];
  items.forEach((item) => {
    const idx = Number(item.dataset.configIndex);
    if (!Number.isFinite(idx)) return;
    allConfigData[idx] = buildSingleConfigFromDOM(item);
  });
}

/**
 * Build a single config object from DOM elements
 */
function buildSingleConfigFromDOM(container) {
  const inputs = container.querySelectorAll("input, select");
  const cfg = {
    notifications: [],
    detection_items: {}
  };

  inputs.forEach((input) => processInputField(input, cfg));
  handleNoExpireCheckbox(container, cfg);

  // Remove empty notifications
  cfg.notifications = cfg.notifications.filter((notif) => notif.token);
  // Ensure store_in_redis is boolean
  cfg.store_in_redis = !!cfg.store_in_redis;

  return cfg;
}

/**
 * Process each input/select field
 */
function processInputField(input, cfg) {
  const { name } = input;
  if (!name) return;

  switch (name) {
    case "line_token":
    case "language":
      updateNotificationField(input, cfg);
      break;
    case "expire_date":
      cfg.expire_date = input.value.trim() || "No Expire Date";
      break;
    case "detect_with_server":
      cfg.detect_with_server = input.checked;
      break;
    case "store_in_redis":
      cfg.store_in_redis = input.checked;
      break;
    case "llm_refine_enabled":
      cfg.llm_refine_enabled = input.checked;
      break;
    case "llm_low_conf_threshold": {
      const val = parseFloat(input.value);
      cfg.llm_low_conf_threshold = Number.isFinite(val) ? val : undefined;
      break;
    }
    default:
      if (name.startsWith("detect_")) {
        cfg.detection_items[name] = input.checked;
      } else if (name === "work_start_hour") {
        cfg.work_start_hour = parseInt(input.value, 10);
      } else if (name === "work_end_hour") {
        cfg.work_end_hour = parseInt(input.value, 10);
      } else {
        // site, stream_name, video_url, model_key, etc.
        cfg[name] = input.value.trim();
      }
  }
}

/**
 * Update notifications array (line_token / language)
 */
function updateNotificationField(input, cfg) {
  const notifIndex = input.getAttribute("data-notif-index");
  if (!cfg.notifications[notifIndex]) {
    cfg.notifications[notifIndex] = { token: "", language: "en" };
  }
  if (input.name === "line_token") {
    cfg.notifications[notifIndex].token = input.value.trim();
  } else {
    cfg.notifications[notifIndex].language = input.value;
  }
}

/**
 * Handle "No Expire Date" checkbox
 */
function handleNoExpireCheckbox(container, cfg) {
  const noExpireDateCheckbox = container.querySelector("input[name='no_expire_date']");
  if (noExpireDateCheckbox) {
    if (noExpireDateCheckbox.checked) {
      cfg.expire_date = "No Expire Date";
    } else if (!cfg.expire_date || cfg.expire_date === "No Expire Date") {
      cfg.expire_date = getTodayDate();
    }
  }
}

/**
 * Validate each config item and return the final array
 */
function validateAndProcessUpdatedConfig() {
  let isValid = true;
  const invalidIndexes = new Set();

  function setDefaultExpireDate(cfg) {
    if (cfg.expire_date !== "No Expire Date" && !cfg.expire_date) {
      cfg.expire_date = "No Expire Date";
    }
  }

  allConfigData.forEach((cfg, idx) => {
    const container = configContainer
      ? configContainer.querySelector(`.config-item[data-config-index='${idx}']`)
      : null;
    ["site", "stream_name", "video_url"].forEach((field) => {
      if (!cfg[field]) {
        isValid = false;
        invalidIndexes.add(idx);
        markFieldError(container, field, "This field is required.");
      }
    });
    if (cfg.work_start_hour >= cfg.work_end_hour) {
      isValid = false;
      invalidIndexes.add(idx);
      markWorkHourError(container, "Work Start Hour cannot be greater than or equal to Work End Hour.");
    }
    setDefaultExpireDate(cfg);
  });

  const invalid = Array.from(invalidIndexes).filter((n) => Number.isFinite(n));
  return { updatedConfig: allConfigData, isValid, invalidIndexes: invalid };
}

/**
 * Mark a specific field as error
 */
function markFieldError(container, fieldName, message) {
  if (!container) return;
  const input = container.querySelector(`input[name='${fieldName}']`);
  if (!input) return;

  input.classList.add("error");
  if (!input.previousElementSibling || !input.previousElementSibling.classList.contains("error-message")) {
    const errorMessage = document.createElement("div");
    errorMessage.className = "error-message";
    errorMessage.textContent = message;
    input.parentNode.insertBefore(errorMessage, input);
  }
}

/**
 * Mark work hour fields as error
 */
function markWorkHourError(container, message) {
  if (!container) return;
  const workStartHourSelect = container.querySelector("select[name='work_start_hour']");
  const workEndHourSelect = container.querySelector("select[name='work_end_hour']");
  if (!workStartHourSelect || !workEndHourSelect) return;
  workStartHourSelect.classList.add("error");
  workEndHourSelect.classList.add("error");

  if (
    !workEndHourSelect.previousElementSibling ||
    !workEndHourSelect.previousElementSibling.classList.contains("error-message")
  ) {
    const errorMessage = document.createElement("div");
    errorMessage.className = "error-message";
    errorMessage.textContent = message;
    workEndHourSelect.parentNode.insertBefore(errorMessage, workEndHourSelect);
  }
}

/* ----------------------------------
   Save Config
------------------------------------- */
async function saveConfig() {
  // Erase previous error messages
  document.querySelectorAll(".error-message").forEach((el) => el.remove());
  document.querySelectorAll(".error").forEach((el) => el.classList.remove("error"));

  try {
    const headers = {
      "Content-Type": "application/json",
      ...authHeaders(),
    };
    if (!headers.Authorization) {
      showConfigError("未登录");
      return;
    }
    updateAllConfigDataFromForm();
    const { updatedConfig, isValid, invalidIndexes } = validateAndProcessUpdatedConfig();

    if (!isValid) {
      const hasInvisibleInvalid =
        !!activeSiteFilter &&
        invalidIndexes.some((idx) => !allConfigData[idx] || allConfigData[idx].site !== activeSiteFilter);
      if (hasInvisibleInvalid) {
        setActiveSiteFilter("");
        validateAndProcessUpdatedConfig();
      }
      return; // Stop if validation fails
    }

    console.log("Saving config payload:", JSON.stringify({ config: updatedConfig }, null, 2));

    const finalConfig = convertNotificationsArrayToObj(updatedConfig);
    removeUndefinedFields(finalConfig);

    // Save to backend
    const response = await fetch(buildApiUrl(ENDPOINTS.streamingBackendApiUrl, '/config'), {
      method: "POST",
      headers,
      body: JSON.stringify({ config: finalConfig })
    });

    if (!response.ok) {
      const detail = await readErrorDetail(response);
      throw new Error(detail || "保存配置失败");
    }
    toggleEditMode(false);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    showConfigError(message);
    logError(error); // Replaces console.error
  }
}

/**
 * Convert notifications array to object for each config
 */
function convertNotificationsArrayToObj(configArray) {
  return configArray.map((cfg) => {
    const notificationsObj = {};
    const notifications = Array.isArray(cfg.notifications) ? cfg.notifications : [];
    notifications.forEach((notif) => {
      if (!notif || typeof notif !== "object") return;
      const token = typeof notif.token === "string" ? notif.token : "";
      if (!token) return;
      notificationsObj[token] = notif.language || "en";
    });
    return {
      ...cfg,
      notifications: notificationsObj,
      no_expire_date: undefined // remove the "no_expire_date" from final JSON
    };
  });
}

/**
 * Remove undefined fields from final config
 */
function removeUndefinedFields(finalConfig) {
  for (const cfg of finalConfig) {
    for (const key in cfg) {
      if (cfg[key] === undefined) {
        delete cfg[key];
      }
    }
  }
}

/* ----------------------------------
   Edit Mode Toggle
------------------------------------- */
function toggleEditMode(enable) {
  isEditing = enable;
  renderConfigForm();

  editBtn.classList.toggle("hidden", enable);
  addConfigBtn.classList.toggle("hidden", !enable);
  formControls.classList.toggle("hidden", !enable);

  if (!enable) {
    fetchConfig(); // Re-fetch to ensure we have the latest data
  }
}

function setActiveSiteFilter(siteName) {
  if (isEditing) {
    updateAllConfigDataFromForm();
  }
  activeSiteFilter = siteName || "";
  if (selectedSiteText) {
    selectedSiteText.textContent = activeSiteFilter || "全部";
  }
  if (clearSiteBtn) {
    clearSiteBtn.classList.toggle("hidden", !activeSiteFilter);
  }
  renderConfigForm();
}

/* ----------------------------------
   Event Listeners
------------------------------------- */
editBtn.addEventListener("click", () => toggleEditMode(true));
cancelBtn.addEventListener("click", () => toggleEditMode(false));
saveBtn.addEventListener("click", saveConfig);
addConfigBtn.addEventListener("click", () => {
  updateAllConfigDataFromForm();
  if (!isEditing) {
    toggleEditMode(true);
  }

  allConfigData.push({
    site: activeSiteFilter || "",
    stream_name: "",
    video_url: "",
    model_key: "yolo11n",
    expire_date: "No Expire Date",
    detect_with_server: false,
    store_in_redis: false,
    llm_refine_enabled: false,
    llm_provider: "ollama",
    llm_base_url: "http://localhost:11434",
    llm_model: "",
    llm_low_conf_threshold: 0.35,
    work_start_hour: 7,
    work_end_hour: 18,
    notifications: [],
    detection_items: {
      detect_no_safety_vest_or_helmet: true,
      detect_near_machinery_or_vehicle: true,
      detect_in_restricted_area: true,
      detect_in_utility_pole_restricted_area: true,
      detect_machinery_close_to_pole: true
    }
  });

  renderConfigForm();
});

if (clearSiteBtn) {
  clearSiteBtn.addEventListener("click", () => setActiveSiteFilter(""));
}

window.addEventListener("chd:site-selected", (event) => {
  const detail = event && typeof event === "object" ? event.detail : null;
  const siteName = detail && typeof detail === "object" ? detail.siteName : "";
  setActiveSiteFilter(siteName || "");
});

// Automatically fetch config on page load
document.addEventListener("DOMContentLoaded", fetchConfig);
