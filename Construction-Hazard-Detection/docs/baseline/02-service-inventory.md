# 服务清单基线（Phase 0）

## 1. 运行单元总表

| 运行单元 | 实际入口文件 | 启动命令（当前脚本/代码） | 默认端口 | 外部依赖 | 主要调用关系 | 是否主链路 |
| --- | --- | --- | --- | --- | --- | --- |
| detection / YOLO API | `examples/YOLO_server_api/backend/app.py` | `uvicorn examples.YOLO_server_api.backend.app:app --host 127.0.0.1 --port 8000 --workers 1` | 8000 | MySQL、Redis、模型目录 `models/pt` | 被 `main.py`、MCP 工具调用 | 是 |
| db management | `examples/db_management/app.py` | `uvicorn examples.db_management.app:app --host 127.0.0.1 --port 8005 --workers 1` | 8005 | MySQL、Redis | 被前端登录/站点流配置调用；被 ticket 回写调用 | 是 |
| violation records | `examples/violation_records/app.py` | `uvicorn examples.violation_records.app:app --host 127.0.0.1 --port 8002 --workers 1` | 脚本用 8002（`app.py main()` 为 8081） | MySQL、Redis、静态文件目录、可选 LLM | 被 `main.py` 写入，前端查询 | 是 |
| notification | `examples/local_notification_server/app.py` | `uvicorn examples.local_notification_server.app:app --host 127.0.0.1 --port 8003 --workers 1` | 8003 | MySQL、Redis、Firebase 凭据（可选） | 被 `main.py` 调用发送通知 | 是 |
| streaming backend | `examples/streaming_web/backend/app.py` | `uvicorn examples.streaming_web.backend.app:app --host 127.0.0.1 --port 8800 --workers 1` | 8800 | MySQL、Redis | 被前端（HTTP+WS）调用；被 `main.py` 推帧 | 是 |
| streaming frontend | `examples/streaming_web/frontend`（Vite root=`public`） | `cd examples\streaming_web\frontend && npm run dev` | 8888 | Node.js/npm | 调用 streaming backend、db management、violation、ticket UI | 是 |
| MCP server | `examples/mcp_server/main.py` | `python -m examples.mcp_server.main` | 默认 8092（streamable-http） | 依赖下游服务 URL、可选静态 Bearer | 工具化调用 YOLO/Violation/DB 等 | 否（默认不启动） |
| 根调度进程 | `main.py` | `python main.py` | 无 HTTP 端口 | MySQL（直连）、下游 API URL、Redis（间接） | 启停每路流子进程，驱动检测主流程 | 是（核心） |
| ticket API | `ticket/service/api_server.py` | `uvicorn ticket.service.api_server:app --host 127.0.0.1 --port 8011 --workers 1` | 脚本用 8011（`__main__` 里是 8000） | PaddleOCR/BERT 运行环境、Neo4j、LLM、DB Management URL+Token | 接收工单解析；回写监控流配置；给 `main.py` 产出报告 | 是（完整闭环） |
| ticket UI | `ticket/service/web_ui.py` | `python web_ui.py` | 代码 7861（`run_web_ui.bat` 文案 7860） | 同 ticket pipeline | 前端 iframe / 新窗口访问 | 是（完整闭环） |
| ticket pipeline（OCR+NER） | `ticket/service/unified_pipeline.py`（由 API/UI 调用） | `run_pipeline.bat` 或 API/UI 间接调用 | 无固定 HTTP 端口 | `ticket/paddle_models`、`ticket/mrc-for-flat-nested-ner`、本机 Python 环境路径 | 为 ticket API/UI 提供解析能力 | 是（完整闭环） |

## 2. 目录职责归类（服务逻辑 vs 共享逻辑）

### 2.1 服务逻辑目录

- `examples/db_management`
- `examples/YOLO_server_api`
- `examples/violation_records`
- `examples/local_notification_server`
- `examples/streaming_web`
- `examples/mcp_server`
- `ticket/service`

### 2.2 共享平台能力目录

- `examples/auth`：数据库连接、ORM、JWT、Redis、全局 lifespan、权限依赖
- `examples/shared`：WebSocket 认证/发送/超时等通用辅助
- `src`：检测主流程公共能力（TokenManager、推帧、写违章、通知、危险判定、拉流）

## 3. 直接依赖关系（代码导入层）

### 3.1 直接依赖 `examples.auth` 的模块

- `examples/db_management/*`
- `examples/YOLO_server_api/backend/*`
- `examples/violation_records/*`
- `examples/local_notification_server/*`
- `examples/streaming_web/backend/*`

### 3.2 直接依赖 `src.*` 的模块

- 根 `main.py`
- `examples/mcp_server/tools/*`
- `examples/violation_records/routers.py`（`src.llm_utils`）

### 3.3 ticket 与监控侧联动路径

1. `ticket/service/api_server.py` 解析工单
2. `ticket/service/hazard_dbm_client.py` 调用 `POST {HAZARD_DBM_BASE_URL}/apply_ticket_to_site`
3. `examples/db_management/routers/streams.py` 接口写回 `stream_configs`（检测开关、工单号、生效时段）

## 4. 目录级职责与耦合（按调研要求逐项）

| 目录 | 现状定位 | 关键事实（耦合/依赖） |
| --- | --- | --- |
| `examples/auth` | 共享平台能力 | 提供 DB engine/session、ORM、JWT、Redis、全局 lifespan；被多个服务直接依赖 |
| `examples/shared` | 共享平台能力 | 提供 WS helper；被 YOLO WS 与 streaming backend WS 直接使用 |
| `examples/db_management` | 服务逻辑 | 管理认证、用户、站点、流配置；对 ticket 提供 `/apply_ticket_to_site` |
| `examples/violation_records` | 服务逻辑 | 违章写入与查询导出；`/upload` 被 `main.py` 直接调用 |
| `examples/local_notification_server` | 服务逻辑 | 设备 token 与 FCM 下发；被 `main.py` 调用 |
| `examples/streaming_web` | 服务逻辑 | backend 处理配置与帧/WS；frontend 提供 UI，且存在对 8005/8002/7861 的直连 |
| `examples/YOLO_server_api` | 服务逻辑 | 提供 `/detect` 与模型文件管理；依赖 `examples.auth` 的 JWT/限流体系 |
| `examples/mcp_server` | 服务逻辑（工具网关） | FastMCP 包装多类工具，调用 YOLO/Violation/DB 等下游 |
| `src` | 共享平台能力 | 调度与检测核心库（TokenManager、FrameSender、ViolationSender、DangerDetector 等） |
| 根 `main.py` | 调度器（非普通 API） | 轮询 DB 表、多进程启停每路流，驱动“抓流->检测->告警->回写”主流程 |
| `ticket/service` | 服务逻辑 | 工单解析 API/UI、Neo4j/LLM 编排、回写监控配置客户端 |
| `ticket/paddle_models` | pipeline 能力资产 | OCR 与预处理脚本/模型目录，由 `ticket/service/unified_pipeline.py` 调用 |
| `ticket/mrc-for-flat-nested-ner` | pipeline 能力资产 | NER 推理/训练工程，由 `ticket/service/unified_pipeline.py` 调用 |
