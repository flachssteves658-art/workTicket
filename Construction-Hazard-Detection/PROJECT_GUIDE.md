# Construction Hazard Detection 项目说明书

## 1. 项目简介

本项目是一个 AI 驱动的工地安全监控系统，利用 **YOLO11** 模型和自定义算法实时检测施工现场的潜在危险。系统支持多语言通知（Line, Telegram 等）、实时流媒体监控、违规记录管理以及 MCP (Model Context Protocol) 扩展。

## 2. 核心功能

- **危险检测**: 未戴头盔/安全背心、靠近机械、进入禁区等。
- **实时监控**: 支持 RTSP/HTTP 视频流实时分析与 Web 展示。
- **通知告警**: 集成 Line, Telegram, FCM 等多渠道即时报警。
- **数据管理**: 基于 MySQL 和 Redis 的配置与状态管理。
- **微服务架构**: 包含检测、记录、通知、数据管理等多个独立服务。

## 3. 目录结构说明

- **`examples/`**: 核心功能模块与微服务代码。
  - `YOLO_server_api/`: **[核心]** 检测服务后端 (Port 8000) 与前端。
  - `streaming_web/`: **[核心]** 流媒体 Web 后端 (Port 8800) 与前端。
  - `db_management/`: 数据库管理 API (Port 8005)。
  - `local_notification_server/`: 本地通知服务 (Port 8003)。
  - `violation_records/`: 违规记录管理 API (Port 8002)。
  - `mcp_server/`: MCP Agent 工具服务。
  - `YOLO_train/` & `YOLO_evaluation/`: 模型训练与评估脚本。
- **`src/`**: 主程序核心逻辑 (检测器、发送器、流捕获等)。
- **`scripts/`**: 数据库初始化 SQL 等脚本。
- **`assets/`**: 项目资源文件（图片、模型权重等）。

## 4. 环境依赖

- **OS**: Windows / Linux
- **Python**: 3.12+
- **Database**: MySQL (Port 3306/3307), Redis (Port 6379)
- **Docker**: 推荐使用 Docker 部署数据库。

## 5. 启动与运行

### 5.1 快速启动 (Windows)

项目提供了便捷的批处理脚本：

1.  **启动后端服务**: 运行 `start_services.bat`
    - 自动启动 Detection, Violation, Notification, DB, Streaming 五个微服务。
2.  **启动前端界面**: 运行 `start_frontend.bat`
    - 启动 Vue+Vite 前端 (http://localhost:8888)。
3.  **启动主程序**: 运行 `python main.py`
    - 负责读取流配置、调度检测进程与核心逻辑。

### 5.2 部署参考

详细部署步骤请参考根目录下的：
`Construction-Hazard-Detection 项目 Windows 完整部署步骤（全密码统一为 12345678，可直接粘贴运行）.md`
