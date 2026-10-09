import sys
import json
from pathlib import Path

# Add service directory to path
_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import config
from neo4j_client import run_cypher_http_statements

def seed_virtual_station():
    """
    构建一个逻辑自洽的“虚拟变电站”基础设施数据。
    包含：区域 -> 设备 -> 摄像头 的完整映射。
    """
    print("正在构建【未来一路变电站】虚拟数据...")

    neo4j_config = {
        'uri': config.NEO4J_URI,
        'user': config.NEO4J_USER,
        'password': config.NEO4J_PASSWORD
    }

    # ==========================================
    # 1. 定义上帝视角的“标准资产库”
    # ==========================================
    
    # 场景 A：室外主变区（高危区域，重点监控）
    area_transformer = {
        "id": "loc_xfmr_002", 
        "name": "#2主变区域", 
        "type": "OutdoorArea", 
        "risk_level": "High"
    }
    
    devices_transformer = [
        {"id": "dev_xfmr_002_main", "name": "#2主变", "type": "Transformer"},
        {"id": "dev_xfmr_002_bushing", "name": "#2主变A相套管", "type": "Component"},
        {"id": "dev_xfmr_002_cooler", "name": "#2主变冷却器", "type": "Component"},
    ]
    
    cameras_transformer = [
        # 枪机，覆盖全景
        {"id": "cam_001_fixed", "name": "主变全景监控", "rtsp": "rtsp://sim/cam1", "type": "Fixed"},
        # 球机，细节特写
        {"id": "cam_002_dome", "name": "主变高点球机", "rtsp": "rtsp://sim/cam2", "type": "Dome"},
    ]

    # 场景 B：室内开关室（封闭空间，登高易违章）
    area_switchgear = {
        "id": "loc_room_10kv", 
        "name": "10kV开关室", 
        "type": "IndoorRoom", 
        "risk_level": "Medium"
    }
    
    devices_switchgear = [
        {"id": "dev_sw_10kv_01", "name": "10kV #1开关柜", "type": "Switchgear"},
        {"id": "dev_sw_10kv_bus", "name": "10kV I段母线", "type": "Busbar"},
    ]
    
    cameras_switchgear = [
        {"id": "cam_003_room", "name": "开关室全景", "rtsp": "rtsp://sim/cam3", "type": "Fixed"},
    ]

    # ==========================================
    # 2. 生成 Cypher 语句
    # ==========================================
    statements = []

    # 2.1 清理旧数据 (可选，为了演示纯净环境)
    # statements.append({"statement": "MATCH (n:Infrastructure) DETACH DELETE n", "parameters": {}})

    # 2.2 创建区域
    for area in [area_transformer, area_switchgear]:
        statements.append({
            "statement": "MERGE (l:Location:Infrastructure {id: $id}) SET l.name = $name, l.type = $type, l.risk_level = $risk_level",
            "parameters": area
        })

    # 2.3 创建主变区设备与监控
    for dev in devices_transformer:
        statements.append({
            "statement": """
                MERGE (d:Device:Infrastructure {id: $id}) SET d.name = $name, d.type = $type
                WITH d MATCH (l:Location {id: $loc_id}) MERGE (d)-[:LOCATED_AT]->(l)
            """,
            "parameters": {**dev, "loc_id": area_transformer["id"]}
        })
    
    for cam in cameras_transformer:
        statements.append({
            "statement": """
                MERGE (c:Camera:Infrastructure {id: $id}) SET c.name = $name, c.rtsp = $rtsp, c.type = $type
                WITH c MATCH (l:Location {id: $loc_id}) MERGE (c)-[:COVERS]->(l)
            """,
            "parameters": {**cam, "loc_id": area_transformer["id"]}
        })

    # 2.4 创建开关室设备与监控
    for dev in devices_switchgear:
        statements.append({
            "statement": """
                MERGE (d:Device:Infrastructure {id: $id}) SET d.name = $name, d.type = $type
                WITH d MATCH (l:Location {id: $loc_id}) MERGE (d)-[:LOCATED_AT]->(l)
            """,
            "parameters": {**dev, "loc_id": area_switchgear["id"]}
        })

    for cam in cameras_switchgear:
        statements.append({
            "statement": """
                MERGE (c:Camera:Infrastructure {id: $id}) SET c.name = $name, c.rtsp = $rtsp, c.type = $type
                WITH c MATCH (l:Location {id: $loc_id}) MERGE (c)-[:COVERS]->(l)
            """,
            "parameters": {**cam, "loc_id": area_switchgear["id"]}
        })
        
    # 2.5 建立设备间的层级关系 (Components)
    statements.append({
        "statement": """
            MATCH (parent:Device {name: '#2主变'})
            MATCH (child:Device) WHERE child.name CONTAINS '#2主变' AND child.name <> '#2主变'
            MERGE (child)-[:PART_OF]->(parent)
        """,
        "parameters": {}
    })

    # ==========================================
    # 3. 执行写入
    # ==========================================
    try:
        run_cypher_http_statements(
            neo4j_config['uri'],
            neo4j_config['user'],
            neo4j_config['password'],
            statements
        )
        print("✅ 虚拟变电站基础设施构建完成！")
        print(f"   - 区域: {area_transformer['name']}, {area_switchgear['name']}")
        print(f"   - 设备: {len(devices_transformer) + len(devices_switchgear)} 台")
        print(f"   - 监控: {len(cameras_transformer) + len(cameras_switchgear)} 个")
        
    except Exception as e:
        print(f"❌ 数据写入失败: {e}")

if __name__ == "__main__":
    seed_virtual_station()
