# 接口基线（Phase 0）

说明：本文件覆盖 demo 主链路关键接口，不做穷举。字段以当前代码签名为准。

## 1. 认证 / 用户 / 站点 / 流配置（DB Management，端口 8005）

| 接口 | 方法 | 核心输入 | 核心输出 | 主要调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/login` | POST | `username`、`password` | `access_token`、`refresh_token`、用户角色信息 | 前端、`src.TokenManager`、MCP | 是 |
| `/refresh` | POST | `refresh_token` | 新 token 对 | 前端、`src.TokenManager` | 是 |
| `/logout` | POST | `refresh_token` + `Authorization` | `message` | 前端 | 否（建议保留） |
| `/list_sites` | GET | `Authorization` | 可访问站点列表 | 前端站点页、违章页筛选 | 是 |
| `/create_site` | POST | 站点名、group 信息 | 站点对象 | 前端管理页 | 是 |
| `/update_site` | PUT | `site_id`、`new_name` | `message` | 前端管理页 | 是 |
| `/delete_site` | DELETE | `site_id` | `message` | 前端管理页 | 是 |
| `/list_stream_configs` | GET | `site_id` | 流配置列表 | 前端配置页 | 是 |
| `/create_stream_config` | POST | `site_id`、`stream_name`、`video_url`、检测项等 | 新配置 `id` | 前端配置页 | 是 |
| `/stream_config/update/{cfg_id}` | PUT | 局部更新字段 | `message` | 前端配置页 | 是 |
| `/delete_stream_config/{cfg_id}` | DELETE | `cfg_id` | `message` | 前端配置页 | 是 |
| `/apply_ticket_to_site` | POST | Header `X-Integration-Token` + `site_name`、`ticket_no`、检测参数 | `updated_stream_config_ids` | ticket API | 是（ticket 联动关键契约） |

## 2. 检测接口（YOLO API，端口 8000）

| 接口 | 方法 | 核心输入 | 核心输出 | 主要调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/detect` | POST | multipart：`model`、`image`，JWT | `[[x1,y1,x2,y2,conf,class_id], ...]` | `main.py`（远程检测模式）、MCP | 是 |
| `/ws/detect` | WebSocket | 二进制帧 + JWT 体系 | 检测结果流 | `src.NetClient` 远程推理 | 是 |
| `/model_file_update` | POST | multipart：`model`、`file`，管理员角色 | 更新结果消息 | 模型运维端 | 否（可后置重构） |
| `/get_new_model` | POST | `model`、`last_update_time` | 模型是否更新/模型文件 | 客户端模型同步 | 否（可后置重构） |

## 3. 违章记录接口（Violation Records，脚本端口 8002）

| 接口 | 方法 | 核心输入 | 核心输出 | 主要调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/upload` | POST | multipart：`site`、`stream_name`、`detection_time`、`warnings_json`、`detections_json`、`agent_report`、`image` | `violation_id` | `main.py`、MCP record 工具 | 是 |
| `/my_sites` | GET | JWT | 站点列表 | 前端违章页、搜索助手 | 是 |
| `/violations` | GET | `site_id/keyword/start_time/end_time/limit/offset` | `total + items` | 前端违章列表、MCP | 是 |
| `/violations/{violation_id}` | GET | 路径参数 + JWT | 单条违章详情 | 前端详情、MCP | 是 |
| `/get_violation_image` | GET | `image_path` + JWT | 图片文件流 | 前端图片查看、MCP | 是 |
| `/violations/intent` | GET | `query` 等 | 意图解析结构 | 前端搜索助手 | 否（建议保留） |
| `/violations/summary` | GET | 过滤参数 | 文本摘要 | 前端搜索助手 | 否（建议保留） |
| `/violations/{violation_id}/export` | GET | `format` | markdown/json 导出 | 前端导出 | 否（建议保留） |

## 4. 通知接口（Notification，端口 8003）

| 接口 | 方法 | 核心输入 | 核心输出 | 主要调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/store_token` | POST | `user_id`、`device_token`、`device_lang` | `message` | 前端设备注册流程 | 是 |
| `/delete_token` | DELETE | `user_id`、`device_token` | `message` | 前端/客户端注销流程 | 否（建议保留） |
| `/send_fcm_notification` | POST | `site`、`stream_name`、`body`、`image_path`、`violation_id` + JWT | 发送统计结果 | `main.py`（通过 `FCMSender`） | 是 |

## 5. Ticket 解析接口（ticket API）

当前主脚本启动端口为 8011（`uvicorn ticket.service.api_server:app ... --port 8011`）。

| 接口 | 方法 | 核心输入 | 核心输出 | 主要调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/api/v1/parse_ticket` | POST | `file` + query: `enable_llm`、`llm_provider`、`enable_neo4j`、`enable_hazard_sync`、`hazard_site_name` | OCR/NER/关系抽取/可选回写结果 | ticket UI、外部调用 | 是（完整 demo） |
| `/api/v1/generate_violation_report` | POST | `ticket_no` + `violation` + LLM 参数 | `agent_report`、图摘要 | 根 `main.py` | 是（`main.py` 已硬依赖默认 URL） |

## 6. Ticket 回写站点流配置接口（跨目录契约）

| 契约链路 | 方法 | 核心输入 | 核心输出 | 调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `ticket -> db_management:/apply_ticket_to_site` | POST | Header: `X-Integration-Token`; Body: `site_name`、`ticket_no`、`active_from/active_to`、检测开关、工时 | `updated_stream_config_ids` | `ticket/service/hazard_dbm_client.py` | 是（跨系统关键契约） |

## 7. Streaming Backend 主接口（补充）

| 接口 | 方法 | 核心输入 | 核心输出 | 调用方 | 兼容期是否必须保留 |
| --- | --- | --- | --- | --- | --- |
| `/config` | GET | JWT | 当前可见流配置（含规范化字段） | 前端配置页 | 是 |
| `/config` | POST | 配置数组 | 同步数据库 + 返回状态 | 前端配置页 | 是 |
| `/frames` | POST | multipart：`label`、`key`、`file`、`warnings_json` 等 | `status/message` | `main.py` `BackendFrameSender` | 是 |
| `/ws/stream/{label}/{key}` | WS | 标签与流 key | 实时帧/告警 | 前端 camera 页 | 是 |
| `/ws/labels/{label}` | WS | label | 可用流列表 | 前端 label 页 | 是 |

