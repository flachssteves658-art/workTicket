import { buildStreamingWsUrl } from './app_endpoints.js';

let socket;
let heartbeatIntervalId = 0;
let tileCleanupIntervalId = 0;
const delimiterBytes = new TextEncoder().encode('--IMG--');
const headerDecoder = new TextDecoder('utf-8');
const tileLastSeen = new Map();

document.addEventListener('DOMContentLoaded', () => {
    const labelTitle = document.getElementById('label-title');
    const loadingMessage = document.getElementById('loading-message');
    const urlParams = new URLSearchParams(window.location.search);
    const label = urlParams.get('label');

    if (!validateLabel(label)) return;

    labelTitle.textContent = label;
    loadingMessage.style.display = 'block'; // Show the loading message
    initializeWebSocket(label);
    startTileCleanupLoop();

    window.addEventListener('beforeunload', closeWebSocket);
});

/**
 * Validate the label parameter and redirect if invalid.
 *
 * @param {string|null} label - The label parameter from the URL.
 * @returns {boolean} Whether the label is valid.
 */
function validateLabel(label) {
    if (!label) {
        logError('Label parameter is missing in the URL');
        window.location.href = 'index.html'; // Redirect to index.html
        return false;
    }
    return true;
}

/**
 * Initialise the WebSocket connection for live updates.
 *
 * @param {string} label - The label used to establish the WebSocket connection.
 */
function initializeWebSocket(label) {
    const token = getAccessTokenFromStorage();
    let url = buildStreamingWsUrl(`/ws/labels/${encodeURIComponent(label)}`);
    if (token) {
        url += `?token=${encodeURIComponent(token)}`;
    }
    socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';

    socket.onopen = setupWebSocketHeartbeat;
    socket.onmessage = (event) => handleMessage(event, label);
    socket.onerror = handleWebSocketError;
    socket.onclose = handleWebSocketClose;
}

/**
 * Set up a heartbeat mechanism to keep the WebSocket connection alive.
 */
function setupWebSocketHeartbeat() {
    logInfo('WebSocket connected');
    if (heartbeatIntervalId) {
        clearInterval(heartbeatIntervalId);
    }
    heartbeatIntervalId = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);
}

/**
 * Close the WebSocket connection gracefully.
 */
function closeWebSocket() {
    if (heartbeatIntervalId) {
        clearInterval(heartbeatIntervalId);
        heartbeatIntervalId = 0;
    }
    if (tileCleanupIntervalId) {
        clearInterval(tileCleanupIntervalId);
        tileCleanupIntervalId = 0;
    }
    tileLastSeen.clear();
    const cameraGrid = document.getElementById('camera-grid');
    if (cameraGrid) {
        cameraGrid.querySelectorAll('img[data-object-url]').forEach((img) => {
            const url = img.dataset.objectUrl;
            if (url) {
                URL.revokeObjectURL(url);
            }
        });
    }
    if (socket) socket.close();
}

/**
 * Handle WebSocket errors by logging the error and redirecting to the index page.
 */
function handleWebSocketError() {
    logError('WebSocket error occurred');
    window.location.href = 'index.html';
}

/**
 * Handle WebSocket closure by logging a message.
 */
function handleWebSocketClose() {
    logInfo('WebSocket connection closed');
}

function handleMessage(event, currentLabel) {
    const data = event.data;
    if (typeof data === 'string') {
        handleTextMessage(data);
        return;
    }
    if (data instanceof ArrayBuffer) {
        handleBinaryFrame(data, currentLabel);
        return;
    }
    if (data instanceof Blob) {
        data.arrayBuffer().then((buffer) => handleBinaryFrame(buffer, currentLabel));
    }
}

function handleTextMessage(text) {
    try {
        const obj = JSON.parse(text);
        if (obj && obj.error) {
            const loadingMessage = document.getElementById('loading-message');
            if (loadingMessage) {
                loadingMessage.textContent = obj.error;
            }
        }
    } catch {
    }
}

function handleBinaryFrame(buffer, currentLabel) {
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
    } catch (e) {
        logError('Failed to parse header JSON: ' + e);
        return;
    }
    const key = header.key || 'Unknown';
    const blob = new Blob([imageBytes], { type: 'image/jpeg' });
    const objectUrl = URL.createObjectURL(blob);
    updateCameraTile(currentLabel, key, objectUrl);
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

function updateCameraTile(currentLabel, key, image) {
    if (!currentLabel) {
        return;
    }
    const loadingMessage = document.getElementById('loading-message');
    const cameraGrid = document.getElementById('camera-grid');
    if (!cameraGrid) {
        return;
    }
    if (loadingMessage) {
        loadingMessage.style.display = 'none';
    }
    let cameraDiv = cameraGrid.querySelector(`.camera[data-key="${key}"]`);
    if (!cameraDiv) {
        cameraDiv = createCameraDiv(key, image);
        cameraGrid.appendChild(cameraDiv);
    } else {
        const img = cameraDiv.querySelector('img');
        if (img) {
            const previousObjectUrl = img.dataset.objectUrl;
            if (previousObjectUrl) {
                URL.revokeObjectURL(previousObjectUrl);
                delete img.dataset.objectUrl;
            }
            const src = normaliseImageSrc(image);
            img.src = src;
            if (src.startsWith('blob:')) {
                img.dataset.objectUrl = src;
            }
        }
    }
    tileLastSeen.set(key, Date.now());
}

function startTileCleanupLoop() {
    if (tileCleanupIntervalId) {
        clearInterval(tileCleanupIntervalId);
        tileCleanupIntervalId = 0;
    }
    tileCleanupIntervalId = setInterval(() => {
        const cameraGrid = document.getElementById('camera-grid');
        if (!cameraGrid) {
            return;
        }
        const now = Date.now();
        const ttlMs = 8000;
        cameraGrid.querySelectorAll('.camera[data-key]').forEach((tile) => {
            const key = tile.getAttribute('data-key') || '';
            if (!key) {
                return;
            }
            const last = tileLastSeen.get(key) || 0;
            if (now - last <= ttlMs) {
                return;
            }
            const img = tile.querySelector('img');
            if (img) {
                const previousObjectUrl = img.dataset.objectUrl;
                if (previousObjectUrl) {
                    URL.revokeObjectURL(previousObjectUrl);
                }
            }
            tileLastSeen.delete(key);
            tile.remove();
        });
    }, 2000);
}

/**
 * Handle updates received from the WebSocket server.
 *
 * @param {Object} data - The data received from the WebSocket server.
 * @param {string} currentLabel - The label currently being displayed.
 */
function handleUpdate(data, currentLabel) {
    // If data is a string (JSON), parse it. If it's a Blob, read it.
    if (typeof data === 'string') {
        try {
            data = JSON.parse(data);
        } catch (e) {
            logError('Failed to parse WebSocket message as JSON: ' + e);
            return;
        }
        processData(data, currentLabel);
    } else if (data instanceof Blob) {
        const reader = new FileReader();
        reader.onload = function() {
            try {
                const text = reader.result;
                const jsonData = JSON.parse(text);
                processData(jsonData, currentLabel);
            } catch (e) {
                logError('Failed to parse Blob as JSON: ' + e);
            }
        };
        reader.readAsText(data);
    } else {
         // data is already an object (if WebSocket library handled it)
         processData(data, currentLabel);
    }
}

function processData(data, currentLabel) {
    const loadingMessage = document.getElementById('loading-message');
    if (data.label === currentLabel && data.images?.length > 0) {
        renderCameraGrid(data.images);
        loadingMessage.style.display = 'none';
    } else {
        logInfo('No data for the current label, redirecting to index.html');
        // window.location.href = 'index.html';
    }
}

/**
 * Render the camera grid with new images.
 *
 * @param {Array} images - An array of image data, each containing a key and base64-encoded image.
 */
function renderCameraGrid(images) {
    const cameraGrid = document.getElementById('camera-grid');
    cameraGrid.querySelectorAll('img[data-object-url]').forEach((img) => {
        const url = img.dataset.objectUrl;
        if (url) {
            URL.revokeObjectURL(url);
        }
    });
    cameraGrid.innerHTML = ''; // Clear existing content in the grid
    tileLastSeen.clear();
    images.forEach(({ key, image }) => {
        // Handle Blob object for image data
        if (image instanceof Blob) {
             const objectUrl = URL.createObjectURL(image);
             const cameraDiv = createCameraDiv(key, objectUrl);
             cameraGrid.appendChild(cameraDiv);
        } else {
             const cameraDiv = createCameraDiv(key, image);
             cameraGrid.appendChild(cameraDiv);
        }
        tileLastSeen.set(key, Date.now());
    });
}

/**
 * Create a camera div for the given key and image.
 *
 * @param {string} key - The unique key for the camera.
 * @param {string} image - The base64-encoded image data.
 * @returns {HTMLElement} The camera div element.
 */
function createCameraDiv(key, image) {
    const cameraDiv = createElementWithClass('div', 'camera');
    cameraDiv.dataset.key = key;

    const title = createElementWithText('h2', key);
    const img = setupCameraImage(key, image);

    cameraDiv.appendChild(title);
    cameraDiv.appendChild(img);

    cameraDiv.addEventListener('click', () => redirectToCameraPage(key));
    return cameraDiv;
}

/**
 * Create an element with a specific class name.
 *
 * @param {string} tagName - The HTML tag name.
 * @param {string} className - The class name to assign.
 * @returns {HTMLElement} The created element.
 */
function createElementWithClass(tagName, className) {
    const element = document.createElement(tagName);
    element.className = className;
    return element;
}

/**
 * Create an element with text content.
 *
 * @param {string} tagName - The HTML tag name.
 * @param {string} text - The text content to assign.
 * @returns {HTMLElement} The created element.
 */
function createElementWithText(tagName, text) {
    const element = document.createElement(tagName);
    element.textContent = text;
    return element;
}

/**
 * Set up the camera image element.
 *
 * @param {string} key - The unique key for the camera.
 * @param {string} image - The base64-encoded image data.
 * @returns {HTMLImageElement} The image element.
 */
function setupCameraImage(key, image) {
    const img = document.createElement('img');
    const src = normaliseImageSrc(image);
    img.src = src;
    if (src.startsWith('blob:')) {
        img.dataset.objectUrl = src;
    }
    img.alt = `${key} image`;
    return img;
}

function normaliseImageSrc(image) {
    const value = String(image || '');
    if (!value) {
        return '';
    }
    if (value.startsWith('data:') || value.startsWith('blob:') || value.startsWith('http')) {
        return value;
    }
    return `data:image/jpeg;base64,${value}`;
}

/**
 * Redirect the user to the camera page for the specified key.
 *
 * @param {string} key - The unique key for the camera.
 */
function redirectToCameraPage(key) {
    const urlParams = new URLSearchParams(window.location.search);
    const label = urlParams.get('label');
    window.location.href = `/camera.html?label=${encodeURIComponent(label)}&key=${encodeURIComponent(key)}`;
}

/**
 * Custom logging functions to replace console statements.
 */

function logInfo(message) {
    // Uncomment this for development or logging services
    // console.log(`[INFO] ${message}`);
}

function logError(message) {
    // Uncomment this for development or logging services
    // console.error(`[ERROR] ${message}`);
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
