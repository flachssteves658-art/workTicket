# Phase 0 基线总览（系统现状冻结）

## 1. 文档目的与边界

本文件用于冻结当前 demo 的真实运行形态，作为后续重构的事实基线。  
本阶段仅做现状调研与梳理，不做重构、不迁移目录、不改业务逻辑。

调研范围包含两个目录，二者共同组成当前主链路：

- 主仓库：`F:\project\项目demo\Construction-Hazard-Detection`
- 联动目录：`F:\project\项目demo\ticket`

## 2. 当前系统的运行形态（高层）

当前系统不是“单体 API”，而是“多服务 + 调度进程 + 前端 + 工单侧联动”的组合：

1. 管理与配置侧：`examples/db_management`（用户/站点/流配置/票据回写）
2. 检测侧：`examples/YOLO_server_api`（检测与模型文件管理）
3. 违章记录侧：`examples/violation_records`（违章写入、查询、导出）
4. 通知侧：`examples/local_notification_server`（FCM token 与消息发送）
5. 可视化侧：`examples/streaming_web`（后端 + 前端）
6. 调度执行侧：根目录 `main.py`（多进程拉流检测调度器）
7. 工单侧：`ticket/service`（工单解析 API/UI + 写回监控配置）
8. Agent 工具侧：`examples/mcp_server`（FastMCP，不在默认启动脚本主链路）

## 3. 当前两种闭环定义

### 3.1 最小可运行闭环（不含工单）

基础设施：

- MySQL
- Redis

运行单元：

- `examples/db_management`（8005）
- `examples/YOLO_server_api/backend`（8000）
- `examples/violation_records`（8002）
- `examples/local_notification_server`（8003）
- `examples/streaming_web/backend`（8800）
- 根 `main.py`（无 HTTP 端口，调度进程）
- `examples/streaming_web/frontend`（8888，开发态）

业务闭环：

- 前端/DB 管理配置站点与流
- `main.py` 轮询 `stream_configs` 并按流启动子进程
- 子进程调用 YOLO、违章记录、通知、推流后端
- 前端通过 streaming backend WebSocket 展示实时结果

### 3.2 完整 demo 闭环（含工单联动）

在最小闭环基础上增加：

- `ticket/service/api_server.py`（脚本实际使用 8011）
- `ticket/service/web_ui.py`（代码端口 7861）
- `ticket/paddle_models`（OCR 脚本与模型资产）
- `ticket/mrc-for-flat-nested-ner`（NER 推理/训练工程）
- Neo4j（ticket 可选写图）
- Ollama 或阿里云兼容 LLM（ticket 与监控侧报告生成）

扩展业务闭环：

- 工单图片进入 `parse_ticket`
- 提取 ticket 字段并可写入 Neo4j
- `enable_hazard_sync` 时回写 `db_management:/apply_ticket_to_site`
- `main.py` 在违章上报时调用 ticket API 生成 `agent_report`

## 4. 根 `main.py` 的定位

根 `main.py` 不是普通 API，而是“流级任务调度器”：

- 直接查 MySQL `stream_configs`（不是经由 DB Management API）
- 对每个 `video_url` 动态启停 `multiprocessing.Process`
- 子进程内部执行完整检测链（抓流 -> 检测 -> 危险判定 -> 记录 -> 通知 -> 推流）
- 支持按 `updated_at` 热重启、按过期/删除自动回收进程

该定位决定了它是运行时主控进程，而非纯接口层。

## 5. 当前事实来源

本基线以代码/脚本/配置为准，README 仅辅助参考。核心来源：

- `start_services.bat`
- `start_frontend.bat`
- `docker-compose.yml`
- 各服务 `app.py` / `main.py` / `routers.py` / `Dockerfile`
- `ticket/service/*` 及其配置与联动客户端
- `.env` 与代码内 `os.getenv` 默认值

