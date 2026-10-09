# Construction-Hazard-Detection · 项目 AI 快速上手手册（中文）

> 面向：新来的 AI 助手 / 新同学  
> 目的：让不了解历史上下文的智能体，在几分钟内掌握项目结构、关键代码、运行方式和注意事项。

---

## 1. 项目整体概览

**项目名称**：Construction-Hazard-Detection  
**核心目标**：对工地摄像头的实时视频流进行安全隐患检测，并通过各种后端服务进行存储、通知与展示。

**主要功能：**

- 定期从数据库拉取“当前需要监控的摄像头流配置”
- 对每路 RTSP 流启动独立子进程执行检测
- 通过 YOLO Server API / WebSocket 实时检测安全隐患
- 利用业务规则（DangerDetector）判断是否构成违章
- 将整帧证据图、检测结果、违章记录发送到对应后端服务
- 通过 FCM 等渠道推送实时告警消息
- 使用 Redis 缓存帧数据和流状态，提升实时性与健壮性
- 支持“大模型复核”：在低置信度时让 LLM 辅助判断，并输出 `evidence_ts` 等信息

---

## 2. 代码入口与运行流程

### 2.1 顶层目录结构（与本项目相关的关键路径）

根目录：`F:\项目demo\Construction-Hazard-Detection`

关键文件 / 目录：

- 主程序入口：
  - [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py)
- 主库说明：
  - 英文 README：[README.md](file:///f:/项目demo/Construction-Hazard-Detection/README.md)
  - 繁中 README：[README-zh-tw.md](file:///f:/项目demo/Construction-Hazard-Detection/README-zh-tw.md)
- 核心模块：
  - [src](file:///f:/项目demo/Construction-Hazard-Detection/src)
- 示例 & 子服务：
  - [examples](file:///f:/项目demo/Construction-Hazard-Detection/examples)
- 测试：
  - [tests](file:///f:/项目demo/Construction-Hazard-Detection/tests)
- 日志输出：
  - [logs](file:///f:/项目demo/Construction-Hazard-Detection/logs)

### 2.2 主程序入口：main.py

主文件：[main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py)

关键结构：

- `class MainApp`
  - 职责：
    - 建立数据库连接池
    - 周期性地读取当前活动的视频流配置
    - 根据配置启动/重启/停止子进程
    - 统一清理资源（子进程、连接池、进程池等）
- `async def _run_single_stream(cfg: StreamConfig)`
  - 职责：
    - 初始化：日志、视频捕获、检测器、危险检测、发送器、Redis 管理等
    - 异步循环读取帧，执行检测、规则判断、帧缓存、发送违章记录及推送
    - 使用帧缓存 + 轨迹数据在需要时选取最优整帧证据图（与 LLM 输出的 `evidence_ts` 协同）
- `def process_single_stream(cfg: StreamConfig)`
  - 职责：
    - 在子进程中设置事件循环策略（Windows 特殊处理）
    - 调用 `asyncio.run(_run_single_stream(cfg))`
- `async def main()`
  - 职责：
    - 解析命令行参数（如 `--poll`、`--config`）
    - 决定使用 **数据库模式** 还是 **JSON 配置文件模式**
    - 数据库模式：实例化 `MainApp` 并 `await app.run()`
    - JSON 模式：为每个配置启动一个 `process_single_stream` 进程
- 模块入口：
  - 在 `if __name__ == '__main__':` 中：
    - 设置多进程启动方式为 `spawn`
    - 在 Windows 下设置 `WindowsSelectorEventLoopPolicy`
    - 调用 `asyncio.run(main())` 启动程序

典型运行命令：

```bash
# 数据库模式（推荐）
python main.py

# 使用本地 JSON 配置文件（高级用法）
python main.py --config config/configuration.json
```

### 2.3 快速启动（Windows / 本机推荐）

本节以“本机开发与联调”为目标，默认端口与启动方式以 [start_services.bat](file:///f:/项目demo/Construction-Hazard-Detection/start_services.bat) 和 [start_frontend.bat](file:///f:/项目demo/Construction-Hazard-Detection/start_frontend.bat) 为准。

1. 准备依赖与数据库表结构

   - 启动 Redis / MySQL（可用 Docker；参考 [README.md](file:///f:/项目demo/Construction-Hazard-Detection/README.md)）
   - 首次运行需导入表结构：`scripts/init.sql`（见 [README.md](file:///f:/项目demo/Construction-Hazard-Detection/README.md) 的 Import Database Schema）

2. 安装 Python 依赖

   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. 准备模型权重（如使用本地推理或检测服务需要）

   - 将 YOLO 权重放到 `models/pt/`（参考 [README.md](file:///f:/项目demo/Construction-Hazard-Detection/README.md) 的 Hugging Face 下载方式）

4. 配置环境变量

   - 根目录 `.env`（示例字段可参考 [README.md](file:///f:/项目demo/Construction-Hazard-Detection/README.md) 的 Environment Variables）
   - 关键点：
     - `DB_MANAGEMENT_API_URL` 指向 DB Management 服务（TokenManager 登录与刷新依赖它）
     - `STREAMING_API_URL` 指向 Streaming Web Backend（帧推送依赖它）
     - `DETECT_API_URL` 指向 Detection API（当 detect_with_server=True 时依赖它）
     - 若不使用 Agent 报告：设置 `AGENT_REPORT_MODE=off`

5. 启动子服务与前端

   ```bash
   .\start_services.bat
   .\start_frontend.bat
   ```

6. 启动主程序

   ```bash
   python main.py
   ```

### 2.4 服务与端口速查

默认以 [start_services.bat](file:///f:/项目demo/Construction-Hazard-Detection/start_services.bat) 为准（如果你改了端口，需同步更新 `.env`）。

| 组件                     | 启动方式（入口）                                       | 默认端口 | 关键环境变量               | 用途                               |
| ------------------------ | ------------------------------------------------------ | -------- | -------------------------- | ---------------------------------- |
| Detection API            | `uvicorn examples.YOLO_server_api.backend.app:app`     | 8000     | `DETECT_API_URL`           | YOLO 检测（HTTP/WebSocket）        |
| Violation Records API    | `uvicorn examples.violation_records.app:app`           | 8002     | `VIOLATION_RECORD_API_URL` | 违章记录与截图存储                 |
| Local Notification API   | `uvicorn examples.local_notification_server.app:app`   | 8003     | `FCM_API_URL`              | 推送通知（FCM 等）                 |
| DB Management API        | `uvicorn examples.db_management.app:app`               | 8005     | `DB_MANAGEMENT_API_URL`    | 用户/站点/流配置管理（登录与权限） |
| Streaming Web Backend    | `uvicorn examples.streaming_web.backend.app:app`       | 8800     | `STREAMING_API_URL`        | 帧上传与 WebSocket 分发            |
| Streaming Web Frontend   | `npm run dev`（见 `examples/streaming_web/frontend/`） | 8888     | 前端内配置                 | 配置页面与实时预览                 |
| Ticket Agent API（可选） | `uvicorn ticket.service.api_server:app`（外部仓库）    | 8011     | `TICKET_AGENT_API_URL`     | 生成 Agent 报告                    |
| Main Program             | `python main.py`                                       | -        | 多项                       | 拉取配置并启动各路流子进程         |

---

## 3. 核心业务链路（单路流处理）

核心逻辑在 `_run_single_stream(cfg: StreamConfig)` 中，定义在 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L333-L551)。

### 3.1 初始化阶段

1. 从 `cfg` 中读取：

   - `video_url`、`site`、`stream_name`
   - `model_key`、`detection_items`
   - `work_start_hour`、`work_end_hour`
   - `store_in_redis` 等

2. 设置日志：

   - 实例化 [LoggerConfig](file:///f:/项目demo/Construction-Hazard-Detection/src/monitor_logger.py)：
     - 流程日志写入：`logs/streams.log`
     - 控制台输出：用于实时观察

3. 初始化组件：
   - `StreamCapture`：负责从 RTSP 拉流并输出异步帧生成器
   - `LiveStreamDetector`：负责调用检测服务（YOLO API / WebSocket）
   - `DangerDetector`：负责根据检测结果判断是否构成危险
   - `FCMSender`：负责推送 FCM 通知
   - `ViolationSender`：负责发送违章记录
   - `BackendFrameSender`：负责将帧+检测结果推送到流媒体后端
   - `RedisManager`：负责对某些流的帧缓存/状态进行 Redis 存取

### 3.2 主循环阶段

循环结构（简化）：

```python
async for frame, ts in streaming_capture.execute_capture():
    # 1. 时间与工作时间判断
    # 2. 调用检测服务获取检测结果与轨迹
    # 3. 危险判定与过滤（DangerDetector + Utils.filter_warnings_by_working_hour）
    # 4. 整帧编码、帧缓存（用作 evidence_ts / 最优证据图选取）
    # 5. 如果 store_in_redis: 推送帧和检测 JSON 到后端
    # 6. 若需要告警：发送违章记录 + 推送 FCM 通知
    # 7. 动态调整采样间隔（根据处理时间）
```

重点逻辑：

- **整帧缓存**：

  - 使用 `frame_cache: deque[tuple[int, bytes]] = deque(maxlen=60)`
  - 缓存最近一段时间的 `(时间戳, 编码后的帧)`
  - 在需要发送违章记录时，根据：
    - 轨迹数据中的事件时间
    - 或 LLM 输出的 `evidence_ts`
    - 在缓存中选择最合适的一帧作为证据图

- **告警条件与 Frame 选择**：
  - 当 `warnings_filtered` 非空，且 `Utils.should_notify(ts, last_notification_time)` 返回 True 时：
    - 遍历轨迹数据，根据类别、置信度、事件时间等，选出最优事件
    - 在帧缓存中寻找对应时间戳帧，若没有，则在允许的时间窗口（例如 ±2 秒）内选取最近一帧
    - 将选中的整帧作为违章记录截图发送

### 3.3 收尾清理阶段

`finally` 里负责：

- 记录“Stopping stream process”日志
- 关闭检测器、释放视频资源、关闭帧发送器
- 若 `store_in_redis`，删除对应 Redis key
- 捕获 Redis 删除异常并以 `logger.warning` 记录

这一部分在 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L525-L537) 有完整实现。

---

## 4. 主进程：多流管理与数据库交互

相关代码主要在 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L53-L332)。

### 4.1 数据库连接与配置读取

- `MainApp._ensure_db_pool()`：

  - 从 `DATABASE_URL` 读取连接信息，使用 `asyncmy.create_pool` 创建连接池
  - 日志记录连接目标：`host:port`

- `MainApp.fetch_stream_configs()`：
  - 执行 SQL 查询，获取所有活跃流配置
  - 将结果映射到 `StreamConfig`（TypedDict），包括：
    - `video_url`、`site`、`stream_name`
    - `model_key`、`detection_items`（多个布尔字段）
    - `work_start_hour`、`work_end_hour`、`store_in_redis`
    - `expire_date`、`updated_at` 等
  - 日志中记录：
    - “Found X active streams”
    - 每个流 “Loaded stream: {site} ({video_url})”

### 4.2 流进程生命周期管理

- `MainApp.reload_configurations()`：

  - 以 `video_url` 为 key，对比当前 `running_processes` 字典和最新配置：
    - 对于“已经不在配置中”或“已过期”的流：
      - 调用 `stop_process` 停止进程
      - 如果旧配置中 `store_in_redis` 为 True，则删除对应 Redis key
      - 从 `running_processes` 中移除
    - 对于“配置中存在，但 updated_at 有变化”的流：
      - 先停止旧进程，清理 Redis
      - 启动新进程，并更新 `running_processes[video_url]`
    - 对于“新的流”（数据库有、running_processes 没有）：
      - 启动新进程，并加入 `running_processes`

- `MainApp.run()`：
  - 在一个 `while True` 循环中，周期性调用 `reload_configurations`
  - 间隔为 `poll_interval`（默认 10 秒，可通过命令行参数 `--poll` 修改）
  - 捕获异常并记录日志，保持主循环稳定

---

## 5. 环境变量一览（只列与本项目核心运行直接相关的）

### 5.1 主流程必需

在 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py) 和 [src/utils.py](file:///f:/项目demo/Construction-Hazard-Detection/src/utils.py)、[src/live_stream_detection.py](file:///f:/项目demo/Construction-Hazard-Detection/src/live_stream_detection.py) 中使用的关键环境变量：

- **数据库与主业务后端**

  - `DATABASE_URL`：MySQL 连接字符串
  - `DETECT_API_URL`：检测服务地址
  - `STREAMING_API_URL`：流媒体帧上传服务地址
  - `VIOLATION_RECORD_API_URL`：违章记录服务地址
  - `FCM_API_URL`：FCM 推送服务地址
  - `DB_MANAGEMENT_API_URL`：用户/站点/流配置管理服务地址（登录/刷新 Token）

- **认证与通用 API**

  - `API_BASE_URL`
  - `API_USERNAME`
  - `API_PASSWORD`

- **Redis**

  - `REDIS_HOST`
  - `REDIS_PORT`
  - `REDIS_PASSWORD`
  - `REDIS_URL`：部分排障脚本使用的整串连接（未配置时脚本会回退默认值）

- **大模型复核（LLM Refine）**
  - `LLM_REFINE_ENABLED`
  - `LLM_PROVIDER`
  - `ALIYUN_API_KEY`
  - `ALIYUN_BASE_URL`
  - `ALIYUN_MODEL_NAME`
  - `LLM_REFINE_LOW_CONF_THRESHOLD`
  - `LLM_REFINE_CACHE_TTL_SEC`
  - `LLM_REFINE_COOLDOWN_SEC`
  - `LLM_REFINE_MAX_CONCURRENCY`
  - `LLM_REFINE_TIMEOUT_SEC`
  - `LLM_REFINE_MIN_CROP_SIZE`
  - `LLM_REFINE_PAD_RATIO`
  - `LLM_REFINE_CLASSES`

语义与默认值（以 [LiveStreamDetector](file:///f:/项目demo/Construction-Hazard-Detection/src/live_stream_detection.py#L436-L510) 为准）：

| 变量                            | 含义                                                  | 默认值                                              |
| ------------------------------- | ----------------------------------------------------- | --------------------------------------------------- |
| `LLM_REFINE_ENABLED`            | 是否启用复核；启用后可能为 tracked 追加 `evidence_ts` | 关闭                                                |
| `LLM_PROVIDER`                  | 复核调用实现（例如 `aliyun`）                         | `aliyun`                                            |
| `ALIYUN_API_KEY`                | 复核服务 Key                                          | 空                                                  |
| `ALIYUN_BASE_URL`               | OpenAI 兼容接口 base_url                              | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `ALIYUN_MODEL_NAME`             | 视觉模型名                                            | `qwen-vl-max-2025-08-13`                            |
| `LLM_REFINE_LOW_CONF_THRESHOLD` | 低置信度触发复核阈值                                  | `0.35`                                              |
| `LLM_REFINE_CACHE_TTL_SEC`      | 同一 track_id 复核结果缓存 TTL                        | `8`                                                 |
| `LLM_REFINE_COOLDOWN_SEC`       | 同一 track_id 触发复核的最小间隔                      | `3`                                                 |
| `LLM_REFINE_MAX_CONCURRENCY`    | 并发复核任务数量                                      | `2`                                                 |
| `LLM_REFINE_TIMEOUT_SEC`        | 单次复核请求超时                                      | `10`                                                |
| `LLM_REFINE_MIN_CROP_SIZE`      | 目标裁剪最小边长（过小不复核）                        | `48`                                                |
| `LLM_REFINE_PAD_RATIO`          | 裁剪框 padding 比例                                   | `0.1`                                               |
| `LLM_REFINE_CLASSES`            | 允许复核的 class_id 列表（逗号分隔）                  | 为空表示不限制                                      |

---

### 5.2 Agent 报告（Ticket Agent / 智能文本报告）

- `AGENT_REPORT_MODE`：`off` / `mock` / `api_no_llm` / `llm`（详见 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L430-L555)）
- `AGENT_REPORT_MIN_INTERVAL_SECONDS`：同一路流最小生成间隔（秒）
- `AGENT_REPORT_CACHE_TTL_SECONDS`：相同内容缓存 TTL（秒）
- `AGENT_REPORT_TOP_DETECTIONS`：仅发送前 N 个检测摘要给 Agent
- `TICKET_AGENT_API_URL`：Agent 报告生成接口地址（默认是 `.../api/v1/generate_violation_report`）

### 5.3 系统对接（Integration Token）

- `INTEGRATION_TOKEN`：用于系统对接接口（例如 DB Management 的集成更新接口）
- `HAZARD_DBM_BASE_URL`：集成方调用 DB Management 的基地址
- `HAZARD_INTEGRATION_TOKEN`：集成方调用 Token（与 `INTEGRATION_TOKEN` 需保持一致）

---

## 6. 服务与数据对接（工程化）

### 6.1 认证与 Token（主程序如何拿到可用的 Bearer Token）

- 主程序与发送器（`BackendFrameSender` / `ViolationSender`）会通过 [TokenManager](file:///f:/项目demo/Construction-Hazard-Detection/src/utils.py#L26-L176) 向 DB Management 发起登录与刷新：
  - `POST {DB_MANAGEMENT_API_URL}/login`（使用 `API_USERNAME` / `API_PASSWORD`）
  - `POST {DB_MANAGEMENT_API_URL}/refresh`
- 各服务的受保护路由一般需要 `Authorization: Bearer <access_token>`（例如 Streaming Web 的 `/frames`、Violation Records 的 `/upload`）。

### 6.2 检测输出数据契约（datas / tracked / warnings）

检测器输出在 [generate_detections](file:///f:/项目demo/Construction-Hazard-Detection/src/live_stream_detection.py#L745-L856)：

- `datas`: `list[list[float]]`
  - 单条格式：`[x1, y1, x2, y2, confidence, class_id]`
  - 坐标系：与原始帧一致的像素坐标（xyxy）
- `tracked`: `list[list[float]]`
  - 单条格式：`[x1, y1, x2, y2, confidence, class_id, track_id, is_moving]`
  - `track_id == -1` 表示不可追踪/未分配
  - `is_moving` 只对部分机具/车辆用于“静止过滤”（见 [DangerDetector.\_filter_static_machinery](file:///f:/项目demo/Construction-Hazard-Detection/src/danger_detector.py#L355-L375)）
  - 当启用 LLM 复核（`LLM_REFINE_ENABLED=true`）时：
    - `tracked` 可能扩展为：`[x1, y1, x2, y2, confidence, class_id, track_id, is_moving, evidence_ts]`
    - `evidence_ts` 为该条复核结果对应的“证据帧时间戳”（用于从帧缓存中挑选更合适的整帧证据图）

危险规则输出在 [DangerDetector.detect_danger](file:///f:/项目demo/Construction-Hazard-Detection/src/danger_detector.py#L51-L148)：

- `warnings`: `dict[str, dict[str, int]]`
  - 例：`{"warning_no_hardhat": {"count": 2}}`
- `cone_polygons` / `pole_polygons`: 用于前端可视化的多边形坐标列表

### 6.3 Streaming Web 帧推送契约（HTTP / WebSocket）

Streaming Web Backend 关键路由在 [routers.py](file:///f:/项目demo/Construction-Hazard-Detection/examples/streaming_web/backend/routers.py#L553-L592)：

- `POST /frames`（multipart/form-data）
  - `label`: 站点名（site）
  - `key`: 流名称（stream_name）
  - `file`: 图像文件
  - 其他字段：`warnings_json` / `cone_polygons_json` / `pole_polygons_json` / `detection_items_json` / `width` / `height`
- `WS /ws/frames`
  - 发送格式为：`header_json_bytes + DELIMITER + frame_bytes`（见 [frame_sender.py](file:///f:/项目demo/Construction-Hazard-Detection/src/frame_sender.py#L271-L341)）

### 6.4 Violation Records 违章上报契约

违章发送由 [ViolationSender](file:///f:/项目demo/Construction-Hazard-Detection/src/violation_sender.py#L93-L248) 负责：

- `POST {VIOLATION_RECORD_API_URL}/upload`（multipart/form-data）
  - `image`: 整帧证据图
  - 必填：`site`、`stream_name`
  - 常用：`detection_time`、`warnings_json`、`detections_json`
  - 可选：`cone_polygon_json`、`pole_polygon_json`、`agent_report`

### 6.5 工作票/工单号对接（active_ticket_no）

主程序从 DB 读取 `active_ticket_no/active_from/active_to` 并用于 Agent 报告生成（见 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L130-L231)），生成的文本通过违章上报的 `agent_report` 字段存档。

DB Management 提供“按站点批量下发工单号”的集成接口（见 [streams.py](file:///f:/项目demo/Construction-Hazard-Detection/examples/db_management/routers/streams.py#L97-L158)）：

- `POST /apply_ticket_to_site`
  - Header：`X-Integration-Token: <INTEGRATION_TOKEN>`
  - Body：`site_name`、`ticket_no`，以及可选字段（见 [ApplyTicketToSiteRequest](file:///f:/项目demo/Construction-Hazard-Detection/examples/db_management/schemas/stream_config.py#L88-L105)）
  - 行为：
    - 将该 `site_name` 下所有 `stream_configs` 的 `active_ticket_no/active_from/active_to` 批量更新
    - 同一次调用也可下发 `work_start_hour/work_end_hour` 与各检测开关字段（用于联动“工作票生效期 + 检测策略”）

### 6.6 Agent 报告生成（可选）

主程序在需要发送违章时会调用 `_generate_agent_report`（见 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L430-L555)）：

- `AGENT_REPORT_MODE=mock`：本地生成简短文本（不请求外部服务）
- `AGENT_REPORT_MODE=api_no_llm`：调用接口但关闭大模型能力
- `AGENT_REPORT_MODE=llm`：调用接口并启用大模型能力（由 Ticket Agent 决定）
- `AGENT_REPORT_MODE=off`：完全关闭

为了避免“报警风暴”导致频繁调用，内部包含：

- “内容级”缓存（相同违章摘要复用）：`AGENT_REPORT_CACHE_TTL_SECONDS`
- “时间级”限流（同一路流最小间隔）：`AGENT_REPORT_MIN_INTERVAL_SECONDS`

接口请求体（主程序实际发送，见 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L508-L540)）：

```json
{
  "ticket_no": "WT-20260101-0001",
  "enable_llm": true,
  "violation": {
    "site": "某工地",
    "stream_name": "东门-1号机位",
    "detection_time": "2026-01-28T12:34:56.789123",
    "warnings": {
      "warning_no_hardhat": { "count": 2 }
    },
    "detections_summary": {
      "counts_by_class": { "2": 2, "5": 3 },
      "top_detections": [{ "class_id": 2, "confidence": 0.91, "track_id": 12 }]
    }
  }
}
```

接口响应（主程序消费字段）：

- JSON 中的 `agent_report`：字符串；若缺失则按无报告处理

### 6.7 FCM 推送接口（Local Notification API）

FCM 发送由 [FCMSender](file:///f:/项目demo/Construction-Hazard-Detection/src/notifiers/fcm_notifier.py#L96-L171) 负责：

- `POST {FCM_API_URL}/send_fcm_notification`（application/json）
  - Header：`Authorization: Bearer <access_token>`
  - Body：`site`、`stream_name`、`body`（warnings dict），可选 `image_path`、`violation_id`

### 6.8 类别 ID 与告警字段对照（规则依赖）

DangerDetector 内部对 class_id 有硬编码依赖（见 [danger_detector.py](file:///f:/项目demo/Construction-Hazard-Detection/src/danger_detector.py#L85-L121)），常用映射如下（以当前实现为准）：

| 语义           | class_id | 相关告警 key                                                                       |
| -------------- | -------- | ---------------------------------------------------------------------------------- |
| Person         | 5        | 参与多项规则                                                                       |
| No hardhat     | 2        | `warning_no_hardhat`                                                               |
| No safety vest | 4        | `warning_no_safety_vest`                                                           |
| Safety cone    | 6        | `warning_people_in_controlled_area`                                                |
| Machinery      | 8        | `warning_close_to_machinery`                                                       |
| Utility pole   | 9        | `warning_people_in_utility_pole_controlled_area`、`detect_machinery_close_to_pole` |
| Vehicle        | 10       | `warning_close_to_vehicle`                                                         |

---

## 7. 测试与质量保障

### 7.1 主测试文件：tests/main_test.py

文件位置：[tests/main_test.py](file:///f:/项目demo/Construction-Hazard-Detection/tests/main_test.py)

这个文件是本项目的**核心单元测试集合**，重点覆盖：

- `MainApp`：
  - 数据库连接与配置拉取
  - 进程管理（启动/停止/重启）
  - Redis 清理行为
- `process_single_stream` / `_run_single_stream`：
  - 正常异步执行逻辑
  - 帧缓存与 evidence_ts 相关逻辑
  - 框选整帧证据图并发送违章
  - Redis 删除异常时的日志行为
  - 帧发送失败时的日志行为
- 模块入口：
  - `test_main_execution`：验证 `if __name__ == '__main__'` 中是否正确设置 `multiprocessing.set_start_method` 和 `asyncio.run(main())`

运行命令：

```bash
python -m unittest tests/main_test.py
```

### 7.2 注意事项（给 AI 助手）

- 测试中大量使用 `AsyncMock` / `MagicMock` 和 `patch('main.xxx')`：
  - 修改实现时，要特别注意保持函数/类名称、模块路径不变，否则测试会找不到目标。
- 时间相关测试中使用 `mock_time.side_effect = lambda: 1000.0 + mock_time.call_count * 0.1`：
  - 避免 `StopIteration`，并保证时间递增。
- 一些测试中手动关闭协程 `coro.close()`：
  - 避免出现 `coroutine was never awaited` 的 RuntimeWarning。

---

## 8. 日志与运行状态排查

日志目录：[logs](file:///f:/项目demo/Construction-Hazard-Detection/logs)

- `monitor.log` / `monitor.log.N`：
  - 由 `MainApp` 等主流程写入
  - 包含：
    - “Connecting to DB”
    - “Found X active streams”
    - “Loaded stream: 站点名 (rtsp://...)”
    - “Launch new stream ...”
    - “Stop stream ...”
- `streams.log`：
  - 单路流处理写入
  - 包含：
    - “Starting stream process for rtsp://...”
    - 检测与帧发送中的错误
    - “Stopping stream process”
    - Redis 删除失败时的 `[WARN] Failed to delete redis key ...`

### 8.1 快速验证清单（本机联调）

- 子服务可达性：依次打开 `http://127.0.0.1:8000/docs`、`http://127.0.0.1:8002/docs`、`http://127.0.0.1:8003/docs`、`http://127.0.0.1:8005/docs`、`http://127.0.0.1:8800/docs`
- DB Management 登录验证：`POST {DB_MANAGEMENT_API_URL}/login` 能返回 `access_token/refresh_token`（主程序需要 `API_USERNAME/API_PASSWORD`）
- 违章上报链路验证：跑一次 [test_violation_api.py](file:///f:/项目demo/Construction-Hazard-Detection/tests/test_violation_api.py) 至少能连到 Violation Records 的 `/docs`

### 8.2 认证/401 问题排查

- 表现：
  - `ViolationSender` / `BackendFrameSender` / `FCMSender` 请求返回 401
  - 日志中出现 “Token expired. Attempting to refresh...” 或 “Authenticate failed...”
- 常见原因：
  - `DB_MANAGEMENT_API_URL` 不可达或指向错误环境
  - `API_USERNAME/API_PASSWORD` 不正确，或该用户无权限访问对应站点/路由
  - DB Management 的 Redis/数据库未就绪导致登录/刷新失败
- 快速定位：
  - 先确认 DB Management 服务已启动（`/docs` 可打开）
  - 再用同一套账号密码调用 `/login` 验证是否能拿到 token

### 8.3 Redis 帧缓存键排查

- 键格式：`stream_frame:{base64(site)}|{base64(stream_name)}`（编码逻辑见 [redis_service.py](file:///f:/项目demo/Construction-Hazard-Detection/examples/streaming_web/backend/redis_service.py#L242-L290) 与 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py#L278-L290)）
- 常见症状：
  - 前端能打开但看不到实时帧：通常是 `/frames` 没写入 Redis，或 key 格式/编码不一致
  - 删除流配置后仍残留旧画面：通常是 Redis key 没被清理（看 `streams.log` 中的 delete key 报错）
- 工具脚本：
  - [check_all_stream_keys.py](file:///f:/项目demo/Construction-Hazard-Detection/scripts/check_all_stream_keys.py)：扫描所有 `stream_frame:*`
  - [check_redis_keys.py](file:///f:/项目demo/Construction-Hazard-Detection/scripts/check_redis_keys.py)：按站点名定位 key 并检查类型

### 8.4 安全注意事项（联调/部署）

- 不要把真实账号密码、`INTEGRATION_TOKEN`、第三方 Key 写进仓库；统一放在 `.env` 或部署密钥系统
- `INTEGRATION_TOKEN` 为空会导致集成接口直接报 500（见 [streams.py](file:///f:/项目demo/Construction-Hazard-Detection/examples/db_management/routers/streams.py#L38-L53)）

---

## 9. 常见 AI 助手任务参考

当新开的 AI 助手接手这个项目时，可以快速从以下任务入手：

1. **阅读入口与核心流程**

   - 先看：[main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py) 的 `MainApp` 和 `_run_single_stream`
   - 辅助看：[src/stream_capture.py](file:///f:/项目demo/Construction-Hazard-Detection/src/stream_capture.py)、[src/live_stream_detection.py](file:///f:/项目demo/Construction-Hazard-Detection/src/live_stream_detection.py)、[src/danger_detector.py](file:///f:/项目demo/Construction-Hazard-Detection/src/danger_detector.py)

2. **扩展或修改大模型复核逻辑**

   - 位置：[src/live_stream_detection.py](file:///f:/项目demo/Construction-Hazard-Detection/src/live_stream_detection.py)
   - 相关环境变量：`LLM_REFINE_*` 系列
   - 注意保持：
     - 异步结构（避免阻塞 main loop）
     - 与 evidence_ts / 帧缓存逻辑的时间戳对齐

3. **排查运行时问题**
   - 优先看：
     - `logs/monitor.log`
     - `logs/streams.log`
   - 常见问题：
     - 数据库连不上（DATABASE_URL）
     - RTSP 拉流失败
     - 检测服务/流媒体服务未启动
     - 中文站点名在日志中乱码（不影响功能）

---

## 10. 贡献规范（给 AI 助手/新同学）

- 遵循项目中已有的代码风格：
  - 使用类型注解（`-> None`, `-> list[StreamConfig]` 等）
  - 使用 `async/await` 而不是同步阻塞
  - 尽量重用已有工具类（`Utils`, `RedisManager` 等）
- 修改核心逻辑时：
  - 同时更新/补充 [tests/main_test.py](file:///f:/项目demo/Construction-Hazard-Detection/tests/main_test.py) 中的对应测试
  - 修改后运行：
    ```bash
    python -m unittest tests/main_test.py
    ```
- Windows 环境：
  - 注意 `asyncio` 的事件循环策略，子进程内已用 `WindowsSelectorEventLoopPolicy` 处理
  - 注意路径与编码（日志中的中文可能显示为乱码，不代表内部数据错误）

---

> 如果你是新开对话的 AI 助手：
>
> 1. 请先阅读本手册和 [main.py](file:///f:/项目demo/Construction-Hazard-Detection/main.py)、[tests/main_test.py](file:///f:/项目demo/Construction-Hazard-Detection/tests/main_test.py)。
> 2. 确认当前运行环境（是否已有数据库、Redis、检测服务、RTSP 源）。
> 3. 在修改任何逻辑前，思考是否需要同时调整测试。
> 4. 完成修改后，务必运行 `python -m unittest tests/main_test.py` 进行回归验证。

## 11. 附录：维护 / 排查脚本（建议放在 scripts/ 目录）

为方便本地排查与环境检查，项目提供了一组独立的小工具脚本，建议统一放在项目根目录下的 scripts/ 目录中，例如：

```
Construction-Hazard-Detection/
  main.py
  src/
  tests/
  scripts/
    check_all_stream_keys.py
    check_db_stream.py
    check_db_streams.py
    check_encoding.py
    check_redis_config.py
    check_redis_keys.py
```

在项目根目录下运行时，命令格式统一为：

```
python scripts/<脚本名>.py
```

下面对每个脚本的作用做简要说明。

1.  check_all_stream_keys.py

- 作用 ：列出 Redis 中所有以 stream_frame: 开头的键，用于确认帧缓存键是否生成正确、编码是否正常。
- 逻辑摘要 ：

  - 连接： redis://:12345678@127.0.0.1:6379/0
  - 使用 SCAN 遍历 stream_frame:\*
  - 尝试按 UTF-8 解码键名并逐个打印

- 使用示例 ：

  ```bash
  python scripts/check_all_stream_keys.py
  ```

2. check_db_stream.py

- 作用 ：在 固定连接串 配置下，快速查看数据库中的 sites 和 stream_configs 表内容，适合本机固定开发环境使用。
- 逻辑摘要 ：

  - 使用硬编码的 DATABASE_URL ： mysql+asyncmy://construction_user:12345678@127.0.0.1:3307/construction_hazard_detection
  - 依次查询并打印：
    - sites
    - stream_configs

- 使用示例 ：

  ```bash
  python scripts/check_db_stream.py
  ```

3. check_db_streams.py

- 作用 ：在 尽量贴近实际部署配置 的前提下，检查数据库中的流配置情况。
- 逻辑摘要 ：

  - 优先从 .env 中读取 DATABASE_URL
  - 若未配置，则回退到默认： mysql+asyncmy://root:12345678@127.0.0.1:3306/construction_hazard_detection
  - 打印实际使用的连接串
  - 查询并打印：
    - stream_configs
    - sites

- 使用示例 ：

  ```bash
  python scripts/check_db_streams.py
  ```

4. check_encoding.py

- 作用 ：验证中文站点名在 Redis 键中的 base64 编码是否一致，常用于排查“中文乱码”或“键名不匹配”问题。
- 逻辑摘要 ：

  - 将 "武汉工程大学" 以 base64.urlsafe_b64encode 方式编码，打印结果
  - 将一个已有编码字符串（如 5q2m5rGJ5bel56iL5aSn5a2m ）解码并打印
  - 对比两者是否一致（MATCH / MISMATCH）

- 使用示例 ：

  ```bash
  python scripts/check_encoding.py
  ```

5. check_redis_config.py

- 作用 ：整体浏览当前 Redis 中的所有键，并对特定关键字（如 wit_test111 ）相关键进行类型检查。
- 逻辑摘要 ：

  - 连接： redis://:12345678@127.0.0.1:6379/0
  - 列出所有 key，打印数量和名称
  - 如果某个 key 包含特定标识（脚本中示例为 wit_test111 ），额外打印该 key 的类型（如 string、list、hash 等）

- 使用示例 ：

  ```bash
  python scripts/check_redis_config.py
  ```

6. check_redis_keys.py

- 作用 ：针对 某个具体站点名 检查其在 Redis 中对应的帧缓存键是否存在、格式是否正确。
- 逻辑摘要 ：

  - 从 .env 读取 REDIS_URL ，默认值： redis://:12345678@127.0.0.1:6379/0
  - 将目标站点名（示例为 "武汉工程大学" ）做 base64 urlsafe 编码
  - 构造 pattern： stream_frame:{encoded_label}|\*
  - 使用 keys(pattern) 查找所有匹配 key，打印数量、名称和类型

- 使用示例 ：

  ```bash
  python scripts/check_redis_keys.py
  ```
