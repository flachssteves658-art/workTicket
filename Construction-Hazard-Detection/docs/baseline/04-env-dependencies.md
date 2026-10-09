# 环境变量与基础设施依赖基线（Phase 0）

## 1. 基础设施依赖总览

| 依赖 | 当前来源 | 被哪些模块使用 | 备注 |
| --- | --- | --- | --- |
| MySQL | `.env DATABASE_URL`，部分 compose | `examples.auth` 体系下各服务；根 `main.py` 直连 | 根 `main.py` 绕过 DB Management API 直接查表 |
| Redis | `.env REDIS_HOST/REDIS_PORT/REDIS_PASSWORD`，compose | 各 FastAPI 服务共享 `examples.auth.lifespan`；流缓存与限流 | 几乎全链路依赖 |
| Neo4j | `ticket/service/config.py`（`NEO4J_URI` 等） | `ticket/service/api_server.py`、`neo4j_client.py` | 主仓库 compose 未统一托管 |
| Ollama / LLM | `src/live_stream_detection.py`、`ticket/service/ollama_client.py`、`.env` | 监控侧低置信复核、ticket 报告与关系抽取 | 默认值与实际生产期望存在偏差 |
| 模型权重目录 | `models/pt`、`ticket/paddle_models`、`ticket/mrc-for-flat-nested-ner/models` | YOLO、ticket OCR/NER | 路径耦合较强 |

## 2. 主仓库 `.env`（已出现且被代码使用）

### 2.1 数据与服务 URL

- `DATABASE_URL`
- `DETECT_API_URL`
- `FCM_API_URL`
- `VIOLATION_RECORD_API_URL`
- `STREAMING_API_URL`
- `DB_MANAGEMENT_API_URL`
- `TICKET_AGENT_API_URL`

### 2.2 认证与缓存

- `API_USERNAME`
- `API_PASSWORD`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`
- `INTEGRATION_TOKEN`

### 2.3 通知与第三方

- `FIREBASE_CRED_PATH`
- `project_id`（注意命名与 `FIREBASE_PROJECT_ID` 不一致）
- `LINE_CHANNEL_ACCESS_TOKEN`

### 2.4 LLM 相关

- `LLM_PROVIDER`
- `LLM_REFINE_ENABLED`
- `ALIYUN_API_KEY`
- `ALIYUN_BASE_URL`
- `ALIYUN_MODEL_NAME`
- `LLM_REFINE_LOW_CONF_THRESHOLD`
- `AGENT_REPORT_MODE`
- `AGENT_REPORT_MIN_INTERVAL_SECONDS`
- `AGENT_REPORT_CACHE_TTL_SECONDS`
- `AGENT_REPORT_TOP_DETECTIONS`

### 2.5 ticket 联动

- `HAZARD_DBM_BASE_URL`
- `HAZARD_INTEGRATION_TOKEN`

## 3. ticket 侧配置与变量

`ticket/service/config.py` 关键变量：

- Python 路径：
  - `PADDLE_PYTHON`
  - `BERT_PYTHON`
- Neo4j：
  - `NEO4J_DATABASE`
  - `NEO4J_URI`
  - `NEO4J_USER`
  - `NEO4J_PASSWORD`
- LLM：
  - `LLM_PROVIDER`
  - `ALIYUN_API_KEY`
  - `ALIYUN_BASE_URL`
  - `ALIYUN_MODEL_NAME`
- 监控联动：
  - `HAZARD_DBM_BASE_URL`
  - `HAZARD_INTEGRATION_TOKEN`

## 4. 变量到模块映射（关键）

| 变量 | 主要使用模块 | 用途 |
| --- | --- | --- |
| `DB_MANAGEMENT_API_URL` | `src.utils.TokenManager`、MCP violations 工具 | 登录与刷新 token |
| `DETECT_API_URL` | 根 `main.py`、`src.live_stream_detection`、MCP inference 工具 | 检测服务地址 |
| `VIOLATION_RECORD_API_URL` | 根 `main.py`、`src.violation_sender`、MCP violations 工具 | 违章写入/查询 |
| `FCM_API_URL` | 根 `main.py`、`src.notifiers.fcm_notifier` | 通知服务地址 |
| `STREAMING_API_URL` | 根 `main.py`、`src.frame_sender` | 推帧地址 |
| `TICKET_AGENT_API_URL` | 根 `main.py` | 违章报告生成地址 |
| `INTEGRATION_TOKEN` | `examples/db_management/routers/streams.py` | 验证 ticket 回写来源 |
| `HAZARD_INTEGRATION_TOKEN` | `ticket/service/hazard_dbm_client.py` | 调用回写接口用 token |

## 5. 当前命名不统一与耦合问题

1. token 命名双轨：
   - 监控侧验证用 `INTEGRATION_TOKEN`
   - ticket 侧发送用 `HAZARD_INTEGRATION_TOKEN`
2. Firebase 项目变量命名不统一：
   - 代码读取 `FIREBASE_PROJECT_ID`
   - `.env` 当前出现 `project_id`
3. 地址注入方式不统一：
   - 有的经 `.env`
   - 有的在前端 JS 中硬编码 `127.0.0.1`
4. `src/live_stream_detection.py` 中 `DETECT_API_URL` 默认回退到远端域名，不是本地默认
5. ticket pipeline Python 解释器路径在 `config.py`、`run_pipeline.bat` 双处硬编码且值不同

## 6. compose / 代码默认地址差异（要点）

- 主 compose 对 MySQL 端口映射为 `3306:3306`，而 `.env DATABASE_URL` 使用 `127.0.0.1:3307`
- compose 中部分服务命令、端口、Dockerfile 路径与当前代码入口不一致（详见 `05-startup-baseline.md`）
- Neo4j 不在主 compose 管控范围，ticket 默认访问本机 `localhost:7474`

