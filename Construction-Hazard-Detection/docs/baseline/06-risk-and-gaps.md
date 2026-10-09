# 风险与缺口基线（Phase 0）

## 1. 后续重构最不能先动的部分

以下部分属于“高耦合运行基线”，不建议在 Phase 1 早期直接改：

1. 根 `main.py` 与 `stream_configs` 的调度契约（字段、轮询、进程生命周期）
2. `db_management:/apply_ticket_to_site` 接口契约（含 `X-Integration-Token`）
3. 前端当前依赖的端口与路径（`8005/8002/8800/7861`）
4. `examples.auth.lifespan` 共享初始化行为（所有服务共同依赖）
5. `violation_records:/upload` 表单字段契约（`main.py` 直接调用）

## 2. 当前主要结构性问题（10 项）

1. 启动入口分裂：bat、compose、Dockerfile 三套定义长期漂移
2. compose 存在明显错误入口（notification、violation 指错 app）
3. 服务端口定义不统一（如 8002 vs 8081、8800 vs 8000、8011 vs 8000）
4. 前端 API 访问混合代理与硬编码直连，环境切换和迁移成本高
5. `main.py` 直连数据库，绕过 DB Management，形成双写/双读路径风险
6. 共享 `examples.auth.lifespan` 在服务启动时自动执行 DDL，副作用跨服务扩散
7. ticket pipeline 运行环境强绑定本机绝对路径（`PADDLE_PYTHON/BERT_PYTHON`）
8. ticket 与主仓库之间 token 命名双轨（`INTEGRATION_TOKEN` vs `HAZARD_INTEGRATION_TOKEN`）
9. 关键外部依赖未统一编排（Neo4j、LLM），部署一致性不足
10. 目录职责混合：服务逻辑与平台共享能力边界不清（`examples.auth`、`src` 被多服务直接耦合）

## 3. 可独立服务化程度评估

### 3.1 已具备独立服务形态（相对）

- `examples/db_management`
- `examples/YOLO_server_api/backend`
- `examples/violation_records`
- `examples/local_notification_server`
- `examples/streaming_web/backend`
- `ticket/service/api_server.py`
- `examples/mcp_server/main.py`

### 3.2 本质仍是共享平台能力（不宜直接拆散）

- `examples/auth`（共享鉴权、数据连接、生命周期）
- `examples/shared`（WS 公共能力）
- `src`（被调度器、MCP、部分服务共用的基础逻辑）

## 4. 已核实项与未验证项

## 4.1 已通过代码核实

- 所有主运行单元入口文件、启动命令、默认端口（含不一致处）
- `start_services.bat`、`start_frontend.bat`、`docker-compose.yml` 的真实内容
- 主链路关键接口路径、请求方式、核心输入输出字段
- `ticket -> db_management` 回写契约与 token 校验机制
- 环境变量使用位置与默认值来源（`.env` + `os.getenv`）
- 目录职责与直接依赖关系（`examples.auth` / `src`）

## 4.2 未做运行态验证（原因）

- 未逐一启动全部服务做联调冒烟
- 未实际执行 OCR/NER/Neo4j/LLM 全链路任务
- 未实际执行 docker compose 编排运行

原因：

- Phase 0 目标是“冻结现状和基线文档”，本次采取静态代码/脚本/配置核查，不做重构或全量运行压测

## 5. 建议作为重构输入的固定事实（Phase 0 结论）

1. 旧链路存在并行入口，需先统一“单一启动真相”再谈拆分
2. 先保持接口兼容，再逐步收敛端口与变量命名
3. 优先保护跨目录契约（`main.py`、`/upload`、`/apply_ticket_to_site`）
4. ticket 与监控侧在当前阶段必须按“一个系统”处理，不能只看主仓库

