# Phase 1: streaming_web 前后端分离（边界清晰化）

## 1. 目标与范围

本阶段只处理 `examples/streaming_web`，目标是先把 demo 子系统变成清晰的前后端边界：

- 前端只通过 HTTP / WebSocket 访问后端服务
- 统一前端对后端地址、端口、路径的依赖方式
- 收敛前端开发代理配置
- 不做平台大合并，不改 `main.py` 调度，不动 ticket 契约，不改 DB 结构

## 2. Phase 0 现状确认（本次改造前）

### 2.1 frontend 实际调用 API

- Streaming backend (`:8800`)
  - `GET /labels`
  - `POST /frames`
  - `DELETE /simulator/cleanup`
  - `GET /config`
  - `POST /config`
- DB Management (`:8005`)
  - `POST /login`
  - `GET /list_sites`
  - `POST /create_site`
  - `PUT /update_site`
  - `DELETE /delete_site`
- Violation records (`:8002`)
  - `GET /my_sites`
  - `GET /violations`
  - `GET /get_violation_image`
  - `GET /violations/intent`
  - `GET /violations/summary`
  - `GET /violations/{id}/export`
  - `GET /segments/intent`
  - `GET /segments`
  - `GET /segments/clips`
- Ticket UI (`:7861`)
  - iframe 与新窗口跳转

### 2.2 websocket 连接方式（改造前）

- `label.js`：`ws(s)://<当前host>/api/ws/labels/{label}`
- `camera.js`：`ws(s)://<当前host>/api/ws/stream/{label}/{key}`

### 2.3 硬编码与边界问题（改造前）

- 硬编码地址散落在多个 JS：
  - `http://127.0.0.1:8005`
  - `http://127.0.0.1:8002`
  - `http://127.0.0.1:7861`
- 前端调用策略混合：
  - 部分接口走 `/api` 代理
  - 部分接口直连硬编码主机端口
- `index.html` 里有 ticket UI 直写链接

### 2.4 backend 依赖现状

- `examples/streaming_web/backend` 直接依赖：
  - `examples.auth`（JWT / DB / Redis / lifespan）
  - `examples.shared`（WS helper / ws utils）
- backend 只承担 API + WS，不承担页面模板或静态资源构建/托管逻辑

## 3. Phase 1 实际改造

## 3.1 新增统一前端地址配置层

- 新增 `frontend/public/js/app_endpoints.js`
  - 统一管理四类地址：
    - `platformApiUrl`
    - `streamingBackendApiUrl`
    - `violationApiUrl`
    - `ticketUiUrl`
  - 提供统一 URL 构建函数：
    - `buildApiUrl(...)`
    - `buildStreamingWsUrl(...)`
- 新增 `frontend/public/static/runtime-config.js`
  - 提供运行时配置入口 `window.__CHD_RUNTIME_CONFIG__`
  - 支持不改代码切换后端地址
- 新增 `frontend/.env.example`
  - 统一 `VITE_*` 变量示例

地址优先级：
1. 运行时配置 `window.__CHD_RUNTIME_CONFIG__`
2. `VITE_*` 环境变量
3. 默认值（兼容本地 demo）

## 3.2 前端调用改造（去散落硬编码）

以下脚本已接入统一配置层：

- `public/js/index.js`
  - 登录、标签拉取、模拟流上传/清理、ticket iframe/new-window 地址
- `public/js/config.js`
  - `/config` 读取与保存
- `public/js/sites.js`
  - 站点 CRUD 调用
- `public/js/violations.js`
  - 违章列表、图片、导出
- `public/js/search_assistant.js`
  - 违章检索 + segments 相关调用
- `public/js/label.js`
  - label WS 连接地址统一构建
- `public/js/camera.js`
  - stream WS 连接地址统一构建

## 3.3 前端开发代理统一

`frontend/vite.config.js` 调整为分类代理：

- `/api/platform -> :8005`
- `/api/streaming -> :8800`（含 WS）
- `/api/violation -> :8002`

同时保留兼容代理：
- `/api -> :8800`（兼容旧调用）

## 3.4 页面层改造

以下页面新增运行时配置脚本注入：

- `public/index.html`
- `public/label.html`
- `public/camera.html`
- `public/config.html`
- `public/sites.html`
- `public/violations.html`

并移除 `index.html` 内 ticket UI 硬编码 href（改为由 JS 统一设置）。

## 4. 当前前后端边界定义（Phase 1 后）

- Frontend (`examples/streaming_web/frontend`)
  - 纯静态页面 + JS 逻辑
  - 通过统一配置层访问后端
  - 不依赖 backend 代码模块
- Streaming backend (`examples/streaming_web/backend`)
  - 仅提供 HTTP/WS API
  - 继续复用 `examples.auth.lifespan` 与共享鉴权/Redis/DB能力
  - 不承担前端构建与页面托管职责

## 5. 保留的兼容行为

- backend API/WS 路径保持不变（`/config`、`/labels`、`/frames`、`/ws/*`）
- Vite 中保留旧 `/api` 代理（指向 streaming backend）
- `main.py` 调度契约未改
- `/upload` 与 `/apply_ticket_to_site` 契约未改
- ticket 联动目录与 token 校验机制未改

## 6. 启动方式收敛（本地最小闭环）

## 6.1 backend 单独启动

```powershell
uvicorn examples.streaming_web.backend.app:app --host 127.0.0.1 --port 8800 --workers 1
```

backend 依赖环境变量（通过 `examples.auth`）：

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`

## 6.2 frontend 单独启动

```powershell
cd examples\streaming_web\frontend
npm install
npm run dev
```

默认端口：`8888`

frontend 地址配置方式：

- 开发期：`VITE_PLATFORM_API_URL`、`VITE_STREAMING_BACKEND_API_URL`、`VITE_VIOLATION_API_URL`、`VITE_TICKET_UI_URL`
- 运行期：`public/static/runtime-config.js` 中 `window.__CHD_RUNTIME_CONFIG__`

## 6.3 本地最小 streaming 开发闭环

1. 启动 MySQL + Redis
2. 启动 `db_management` (`:8005`)
3. 启动 `violation_records` (`:8002`)
4. 启动 `streaming_web/backend` (`:8800`)
5. 启动 `streaming_web/frontend` (`:8888`)
6. 浏览器访问 `http://127.0.0.1:8888`

## 7. 本阶段明确不做

- 不进行 `platform` / `ticket` / `orchestrator` 目录级大搬迁
- 不改共享库结构（`examples.auth` / `examples.shared` / `src`）
- 不收口所有历史端口到单端口网关
- 不改跨系统关键契约（`main.py`、`/upload`、`/apply_ticket_to_site`）
