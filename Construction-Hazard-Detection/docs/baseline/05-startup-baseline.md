# 启动链路基线（Phase 0）

## 1. 当前脚本化启动链路

## 1.1 `start_services.bat`（真实主脚本）

按脚本顺序启动：

1. YOLO API `:8000`
2. Violation Records `:8002`
3. Notification `:8003`
4. DB Management `:8005`
5. Streaming Backend `:8800`
6. Ticket API `:8011`（通过 `cd ..` 到 `ticket` 目录）

脚本最后提示：`python main.py` 需要手动启动（未自动拉起）。

## 1.2 `start_frontend.bat`

1. 切到 `examples\streaming_web\frontend`
2. 若无 `node_modules` 自动 `npm install`
3. `npm run dev`
4. 文案端口：`http://localhost:8888`

## 2. 当前最小可运行链路

在“监控主流程”意义上，最小链路为：

- MySQL + Redis
- `examples/db_management`（8005）
- `examples/YOLO_server_api/backend`（8000）
- `examples/violation_records`（8002）
- `examples/local_notification_server`（8003）
- `examples/streaming_web/backend`（8800）
- 根 `main.py`
- （可视化需要）`examples/streaming_web/frontend`（8888）

说明：

- 没有 `main.py`，仅有 API 服务不能形成“抓流检测->违章落库->通知->实时推流”闭环
- 没有 DB/Redis，多数服务在共享 lifespan 初始化阶段无法正常工作

## 3. 当前完整 demo 链路

最小链路 + ticket 侧：

- Ticket API：`uvicorn ticket.service.api_server:app --port 8011`
- Ticket UI：`python ticket/service/web_ui.py`（7861）
- ticket pipeline 资产：`ticket/paddle_models` + `ticket/mrc-for-flat-nested-ner`
- Neo4j（可选但被完整能力使用）
- LLM（Ollama 或阿里云兼容）

## 4. 当前真实启动顺序（建议按依赖）

脚本顺序并非最稳妥依赖顺序。按依赖建议顺序应为：

1. MySQL、Redis、Neo4j（如启用 ticket 图谱）
2. DB Management（8005）
3. YOLO（8000）、Violation（8002）、Notification（8003）、Streaming Backend（8800）
4. Ticket API（8011）与 Ticket UI（7861，按需）
5. 根 `main.py`
6. Frontend（8888）

原因：

- `main.py` 依赖 DB 中已有流配置与各下游服务地址
- 前端登录/配置依赖 DB Management
- ticket 回写依赖 DB Management 可用且 token 配置一致

## 5. `docker-compose.yml` 与实际代码/脚本不一致点

1. `local-notification-server` 的 `command` 指向了 `examples.streaming_web.backend.app:app`（错误）
2. `violation-records` 的 `command` 也指向了 `examples.streaming_web.backend.app:app`（错误）
3. `yolo-server-api` 的 `dockerfile` 指向 `examples/YOLO_server_api/Dockerfile`，仓库实际 Dockerfile 在 `examples/YOLO_server_api/backend/Dockerfile`
4. compose 中 `user-management` 暴露 `8001:8001`，与实际 DB Management 入口 `8005` 不一致
5. compose 暴露/注释端口语义与当前 bat 体系不一致（8000/8002/8003/8800/8011）

## 6. 各服务 Dockerfile 与运行脚本不一致点

1. `examples/YOLO_server_api/backend/Dockerfile`
   - CMD 指向 `examples.YOLO_server_api.app:app`（与实际 `...backend.app:app` 不一致）
   - 暴露端口 6000（脚本实际 8000）
2. `examples/violation_records/Dockerfile`
   - 暴露并运行 8081（脚本实际 8002）
3. `examples/streaming_web/backend/Dockerfile`
   - 默认 8000（脚本实际 8800）
4. `ticket/service/api_server.py` `__main__` 中运行 8000（脚本实际 8011）
5. `ticket/service/run_web_ui.bat` 文案 7860（`web_ui.py` 实际 7861）

## 7. 重复入口与潜在失效入口

### 7.1 重复入口

- 同一服务同时存在：
  - `app.py main()` 入口
  - bat 脚本 `uvicorn ...` 入口
  - Dockerfile CMD 入口

### 7.2 潜在失效入口

- compose 中 notification / violation 的 command 指错模块，服务行为与名称不一致
- YOLO Dockerfile 的模块路径在当前目录结构下不可直接匹配
- ticket API/UI 端口文档与代码不一致，容易误连

## 8. 启动方案中的关键问题

1. 启动方案多头并存（bat、compose、Dockerfile 默认）且互相漂移
2. 端口在多个层级重复定义，缺少单一事实来源
3. 根 `main.py` 不在 `start_services.bat` 自动序列，易导致“服务都起了但无检测产出”
4. 前端 API 访问策略混合（代理 + 直连硬编码），切换环境成本高

