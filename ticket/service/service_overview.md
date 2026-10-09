# service 目录文件简要说明

本文件概览 service 目录下各脚本的职责，便于快速定位与扩展。

- api_server.py：提供 HTTP 接口，接收图片并调用统一流水线 → 返回解析结果与可选图谱写入。[api_server.py](file:///f:/方向1/service/api_server.py)
- config.py：全局配置，包含项目路径、脚本位置、输出目录与外部服务配置。避免硬编码敏感信息，推荐用环境变量覆盖。[config.py](file:///f:/方向1/service/config.py)
- core_pipeline.py：分步式流水线封装（OCR→NER→结果加载），用于早期或独立调用的管线执行。[core_pipeline.py](file:///f:/方向1/service/core_pipeline.py)
- unified_pipeline.py：统一管线入口（OCR→NER→规则→可选LLM→可选Neo4j），同时提供实体后处理与规则抽取工具函数。[unified_pipeline.py](file:///f:/方向1/service/unified_pipeline.py)
- ollama_client.py：统一的大模型调用封装，支持本地 Ollama 与阿里云 DashScope 的 Chat 接口。[ollama_client.py](file:///f:/方向1/service/ollama_client.py)
- neo4j_client.py：面向 Neo4j 的写入与约束管理，包含 Ticket/Entity/REL 的落库语句与唯一约束创建；支持批量 Cypher 执行。[neo4j_client.py](file:///f:/方向1/service/neo4j_client.py)
- seed_infrastructure.py：创建“未来一路变电站”等静态设施数据（Location/Device/Camera 与 LOCATED_AT/COVERS/PART_OF 关系）。[seed_infrastructure.py](file:///f:/方向1/service/seed_infrastructure.py)
- seed_mock_tickets.py：生成与静态设施命名完全匹配的 Mock OCR JSON，用于冷启动验证与闭环测试。[seed_mock_tickets.py](file:///f:/方向1/service/seed_mock_tickets.py)
- ingest_mock_data.py：读取 Mock OCR → 执行（真实或模拟）NER → 写入 Ticket/Entity → 实体链接到 Infrastructure，打通端到端闭环。[ingest_mock_data.py](file:///f:/方向1/service/ingest_mock_data.py)
- web_ui.py：基于 Gradio 的本地 Web 演示界面，展示关键字段、实体关系、JSON 与 Cypher 结果，并可选择写入 Neo4j。[web_ui.py](file:///f:/方向1/service/web_ui.py)

