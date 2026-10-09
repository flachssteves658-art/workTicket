# 数据说明书（工作票→知识图谱）

本说明书用于快速理解本项目的数据结构与处理流程，聚焦“工作票上传到知识图谱”的最小可用闭环。内容覆盖静态设施、动态票据、感知链接三层数据，以及关键ID与约束策略。

## 数据分层与核心概念
- 静态基建层：以 Infrastructure 为统一标签，包含以下节点与关系
  - 节点
    - Location：例如“#2主变区域”“10kV开关室”
    - Device：例如“#2主变”“#2主变A相套管”“10kV #1开关柜”
    - Camera：监控设备，含 rtsp/type 等属性
  - 关系
    - LOCATED_AT：Device → Location
    - COVERS：Camera → Location
    - PART_OF：子部件 → 父设备（层级关系）
- 动态单据层：表示一次工作任务的识别结果
  - 节点
    - Ticket：票据唯一标识，含 ticket_id、ticket_no
    - Entity：结构化实体，含 name、type、ticket_id
  - 关系
    - HAS_ENTITY：Ticket → Entity
    - REL：实体间抽取的语义关系（可选）
- 感知链接层：把票据实体与物理世界对齐
  - 关系
    - REFERS_TO_ASSET：Entity → Device
    - REFERS_TO_LOC：Entity → Location

## 关键数据来源与产物
- 基建种子：[seed_infrastructure.py](file:///f:/方向1/service/seed_infrastructure.py)
  - 构建“未来一路变电站”拓扑：区域、设备、摄像头以及层级关系
  - 写入 Neo4j 后作为“标准答案”支撑后续关联
- 模拟票据：[seed_mock_tickets.py](file:///f:/方向1/service/seed_mock_tickets.py)
  - 在输出目录生成 mock_ticket_001.json / mock_ticket_002.json（模拟 OCR 输出）
  - 使用与基建完全一致的命名实现冷启动期间的“答案预埋”
- 数据入库与链接：[ingest_mock_data.py](file:///f:/方向1/service/ingest_mock_data.py)
  - 读取 mock OCR → 执行 NER（若缺环境自动降级为 Mock NER）
  - 写入 Ticket/Entity → 执行实体链接（匹配到 Device/Location）
- 输出目录
  - config.OUTPUT_DIR 指向 pipeline_output（自动创建）
  - 文件包括：mock_ticket_*.json、*_ner.json、以及可选的图谱写入中间产物

## ID 与约束策略
- 票据 ID（ticket_id）
  - 由输入文件内容或路径经 SHA-256 生成，保证稳定性
  - 生成逻辑在 [neo4j_client.py](file:///f:/方向1/service/neo4j_client.py#L10-L16)
- 实体 ID（entity_id）
  - 组合 ticket_id + 规范化文本 + 类型，经 SHA1 取前16位
  - 构建逻辑在 [neo4j_client.py](file:///f:/方向1/service/neo4j_client.py#L113-L135)
- 关系 ID（rel_id）
  - 组合 subject_id + relation + object_id，经 SHA1 取前16位
  - 构建逻辑在 [neo4j_client.py](file:///f:/方向1/service/neo4j_client.py#L138-L176)
- Neo4j 约束
  - Ticket.ticket_id 唯一、Entity.entity_id 唯一、REL.rel_id 唯一
  - 创建逻辑在 [neo4j_client.py](file:///f:/方向1/service/neo4j_client.py#L85-L111)

## 处理流程（冷启动最小闭环）
1. 初始化基建：运行 seed_infrastructure.py，生成 Location/Device/Camera 与关系
2. 生成票据：运行 seed_mock_tickets.py，在输出目录生成两个 OCR JSON
3. 入库与链接：运行 ingest_mock_data.py
   - 执行 NER（环境不足时降级为 Mock NER）
   - 统一后处理与规则补充（见 [unified_pipeline.py](file:///f:/方向1/service/unified_pipeline.py#L68-L152)）
   - 写入 Ticket/Entity（见 [neo4j_client.py](file:///f:/方向1/service/neo4j_client.py#L179-L245)）
   - 执行实体链接（见 [ingest_mock_data.py](file:///f:/方向1/service/ingest_mock_data.py#L78-L137)）

## 查询与验证提示
- 以票据为起点，查看实体与资产的映射：
  - MATCH (t:Ticket)-[:HAS_ENTITY]->(e:Entity) RETURN t,e LIMIT 20
  - MATCH (e:Entity)-[:REFERS_TO_ASSET]->(d:Device) RETURN e,d LIMIT 20
  - MATCH (e:Entity)-[:REFERS_TO_LOC]->(l:Location) RETURN e,l LIMIT 20
- 以地点为起点，查看摄像头覆盖：
  - MATCH (l:Location)<-[:COVERS]-(c:Camera) RETURN l,c

## 安全与配置建议
- 连接与密钥通过环境变量覆盖，避免在代码中硬编码真实敏感信息
- Neo4j 写入需显式开启（API或Web UI勾选），数据库名默认 neo4j-rag

