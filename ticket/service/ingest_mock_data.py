import sys
import json
import os
import traceback
from pathlib import Path

# Add service directory to path
_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

# Add BERT project root to path for NER imports
_BERT_ROOT = _SERVICE_DIR.parent / "mrc-for-flat-nested-ner"
if str(_BERT_ROOT) not in sys.path:
    sys.path.insert(0, str(_BERT_ROOT))

print(f"Debug: Added {_BERT_ROOT} to sys.path")

import config  # noqa: E402
from neo4j_client import write_full_graph_to_neo4j, generate_ticket_id, run_cypher_http_statements  # noqa: E402
from unified_pipeline import (
    _collect_entities_from_ner, 
    _postprocess_entities, 
    _rule_entities_from_text, 
    _extract_ticket_no, 
    _extract_text_from_ocr_json
)  # noqa: E402

# Import NER function dynamically
run_ner_on_ocr_json = None
try:
    # Try importing as a module from the root
    from inference.work_ticket_ner_from_ocr_json import run_ner_on_ocr_json  # type: ignore
except ImportError:
    print("ImportError details:")
    traceback.print_exc()
    print("\nAttempting alternative import...")
    try:
        # Fallback: append inference to path directly
        sys.path.append(str(_BERT_ROOT / "inference"))
        import work_ticket_ner_from_ocr_json as ner_module  # type: ignore
        run_ner_on_ocr_json = ner_module.run_ner_on_ocr_json
    except ImportError:
        print("Fatal Error: Could not import NER module.")
        traceback.print_exc()
        run_ner_on_ocr_json = None  # Mark as unavailable

def mock_run_ner(ocr_path: str, output_path: str):
    """
    Mock NER inference for cold-start simulation.
    Returns predefined entities based on filename to simulate model output.
    """
    print(f"   ⚠️ 使用 Mock NER 模式 (无需 GPU/环境)")
    base_name = Path(ocr_path).stem
    
    entities = []
    if "mock_ticket_001" in base_name:
        entities = [
            {"text": "#2主变区域", "type": "LOCATION", "label": "LOCATION"},
            {"text": "#2主变A相套管", "type": "EQUIPMENT", "label": "EQUIPMENT"},
            {"text": "油位检查", "type": "Content", "label": "Content"}
        ]
    elif "mock_ticket_002" in base_name:
        entities = [
            {"text": "#2主变", "type": "EQUIPMENT", "label": "EQUIPMENT"},
            {"text": "220kV", "type": "Voltage", "label": "Voltage"},
            {"text": "预防性试验", "type": "Content", "label": "Content"}
        ]

    # Construct result in the format expected by _collect_entities_from_ner
    result = {
        "blocks": [
            {
                "entities": entities
            }
        ]
    }

    # Save mock result to file to simulate real output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result

def perform_entity_linking(ticket_id, neo4j_config):
    """
    执行实体链接：将工作票中的 Entity 链接到 Infrastructure 节点。
    这是“知识图谱作为基石”的核心体现。
    """
    print(f"🔗 正在为票据 {ticket_id[:8]}... 执行实体链接...")

    # 逻辑 1: 设备名称匹配 (Device Name Matching)
    # 查找票据中的 EQUIPMENT 实体，尝试匹配 Infrastructure 中的 Device
    # 注意：我们放宽匹配条件，只要包含即可
    link_device_stmt = """
        MATCH (t:Ticket {ticket_id: $ticket_id})-[:HAS_ENTITY]->(e:Entity)
        WHERE e.type IN ['EQUIPMENT', 'Device', 'Voltage']
        MATCH (d:Device:Infrastructure)
        WHERE d.name = e.name OR e.name CONTAINS d.name OR d.name CONTAINS e.name
        MERGE (e)-[:REFERS_TO_ASSET]->(d)
        RETURN count(d) as linked_count
    """

    # 逻辑 2: 地点名称匹配 (Location Name Matching)
    link_location_stmt = """
        MATCH (t:Ticket {ticket_id: $ticket_id})-[:HAS_ENTITY]->(e:Entity)
        WHERE e.type IN ['LOCATION', 'Location']
        MATCH (l:Location:Infrastructure)
        WHERE l.name = e.name OR e.name CONTAINS l.name OR l.name CONTAINS e.name
        MERGE (e)-[:REFERS_TO_LOC]->(l)
        RETURN count(l) as linked_count
    """

    try:
        res1 = run_cypher_http_statements(
            neo4j_config['uri'], neo4j_config['user'], neo4j_config['password'],
            [{"statement": link_device_stmt, "parameters": {"ticket_id": ticket_id}}]
        )

        res2 = run_cypher_http_statements(
            neo4j_config['uri'], neo4j_config['user'], neo4j_config['password'],
            [{"statement": link_location_stmt, "parameters": {"ticket_id": ticket_id}}]
        )

        # 简单解析一下返回结果，给用户一些正反馈
        count_dev = 0
        if res1 and 'results' in res1 and res1['results']:
            data = res1['results'][0].get('data', [])
            if data:
                count_dev = data[0].get('row', [0])[0]

        count_loc = 0
        if res2 and 'results' in res2 and res2['results']:
            data = res2['results'][0].get('data', [])
            if data:
                count_loc = data[0].get('row', [0])[0]

        if count_dev > 0 or count_loc > 0:
            print(f"   ✅ 链接成功！关联了 {count_dev} 个设备，{count_loc} 个地点。")
        else:
            print(f"   ⚠️ 未找到匹配的设备或地点。请检查名称是否一致。")

    except Exception as e:
        print(f"❌ 实体链接失败: {e}")

def ingest_mock_data():
    print("开始处理模拟数据入库...")

    output_dir = Path(config.OUTPUT_DIR)
    mock_files = sorted(output_dir.glob("mock_ticket_*.json"))

    if not mock_files:
        print("没有找到 mock_ticket_*.json 文件，请先运行 seed_mock_tickets.py")
        return

    neo4j_config = {
        'uri': config.NEO4J_URI,
        'user': config.NEO4J_USER,
        'password': config.NEO4J_PASSWORD
    }

    for ocr_json_path in mock_files:
        # 跳过已经生成的 NER 结果文件，只处理原始 Mock OCR 文件
        if "_ner.json" in ocr_json_path.name:
            continue

        print(f"\n📄 处理文件: {ocr_json_path.name}")
        base_name = ocr_json_path.stem
        ner_json_path = output_dir / f"{base_name}_ner.json"

        # 1. Run NER
        print("   Running NER (Model Inference)...")
        try:
            if run_ner_on_ocr_json:
                ner_result = run_ner_on_ocr_json(
                    str(ocr_json_path),
                    str(ner_json_path),
                    # model_ckpt=...
                )
            else:
                ner_result = mock_run_ner(str(ocr_json_path), str(ner_json_path))

        except Exception as e:
            print(f"   ❌ NER 运行失败: {e}")
            traceback.print_exc()
            continue

        # 2. Process Entities (Post-processing)
        raw_entities = _collect_entities_from_ner(ner_result)

        # 读取 OCR 文本用于规则提取
        with open(ocr_json_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
        ocr_text = _extract_text_from_ocr_json(ocr_data)
        
        entities = _postprocess_entities(raw_entities)
        rule_entities = _rule_entities_from_text(ocr_text)
        final_entities = _postprocess_entities(entities + rule_entities)
        
        print(f"   提取到 {len(final_entities)} 个实体 (NER+Rule)")

        # 3. Write to Neo4j
        print(f"   Writing to Neo4j...")
        ticket_id = generate_ticket_id(str(ocr_json_path)) 
        ticket_no = _extract_ticket_no(final_entities) or base_name
        
        write_success = write_full_graph_to_neo4j(
            ticket_id=ticket_id,
            ticket_no=ticket_no,
            entities=final_entities,
            relationships=[], 
            neo4j_config=neo4j_config,
            overwrite=True
        )
        
        if write_success:
            # 4. Perform Entity Linking
            perform_entity_linking(ticket_id, neo4j_config)
        else:
            print("   ❌ 写入失败")

    print("\n🎉 所有模拟数据处理完成！")
    print("现在您的图谱中已经具备了【静态资源】与【动态单据】的强关联。")

if __name__ == "__main__":
    ingest_mock_data()
