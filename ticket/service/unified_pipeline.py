import subprocess
import json
import sys
import os
import re
from pathlib import Path

# 添加服务目录到系统路径，以便导入其他模块
_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import config
from ollama_client import validate_low_confidence_entities, extract_entity_relationships
from neo4j_client import write_full_graph_to_neo4j, generate_ticket_id, execute_cypher_query


def _run(cmd, cwd, env=None):
    """
    """
    subprocess.run(cmd, cwd=cwd, check=True, env=env)
    return ""


def _find_bert_model_assets():
    """Return the latest complete work-ticket checkpoint, or a skip reason."""
    bert_python = Path(config.BERT_PYTHON)
    if not bert_python.is_file():
        return None, f"BERT Python not found: {bert_python}"

    bert_root = Path(config.BERT_PROJECT_ROOT)
    outputs_root = bert_root / "outputs" / "work_ticket_model"
    if not outputs_root.is_dir():
        return None, f"BERT work-ticket model directory not found: {outputs_root}"

    run_dirs = [path for path in outputs_root.iterdir() if path.is_dir()]
    if not run_dirs:
        return None, f"No trained model runs found in: {outputs_root}"

    latest_run = max(run_dirs, key=lambda path: path.stat().st_mtime)
    checkpoints = sorted(
        latest_run.glob("*.ckpt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        return None, f"No .ckpt file found in: {latest_run}"

    hparams_file = latest_run / "lightning_logs" / "version_0" / "hparams.yaml"
    if not hparams_file.is_file() or not hparams_file.read_text(encoding="utf-8").strip():
        return None, f"Missing or empty hparams.yaml: {hparams_file}"

    bert_dir = bert_root / "models" / "chinese-roberta-wwm-ext"
    if not bert_dir.is_dir():
        return None, f"Base BERT model directory not found: {bert_dir}"

    return {
        "checkpoint": checkpoints[0],
        "hparams": hparams_file,
        "bert_dir": bert_dir,
    }, None


def _collect_entities_from_ner(ner_data):
    entities = []
    blocks = ner_data.get("blocks") or []
    for block in blocks:
        for ent in block.get("entities") or []:
            entities.append(ent)
    return entities


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


def _extract_text_from_ocr_json(ocr_data) -> str:
    if isinstance(ocr_data, list):
        return " ".join([item.get("text", "") for item in ocr_data if isinstance(item, dict)])
    if isinstance(ocr_data, dict):
        if "results" in ocr_data and isinstance(ocr_data["results"], list):
            return " ".join([item.get("text", "") for item in ocr_data["results"] if isinstance(item, dict)])
        if "parsing_res_list" in ocr_data and isinstance(ocr_data["parsing_res_list"], list):
            parts = []
            for item in ocr_data["parsing_res_list"]:
                if not isinstance(item, dict):
                    continue
                content = item.get("block_content", "") or ""
                if "<" in content and ">" in content:
                    content = _strip_html(content)
                parts.append(content)
            return "\n".join(parts)
    return ""


def _normalize_entity_text(text: str) -> str:
    text = (text or "").replace("_", " ")
    text = re.sub(r"\s+", "", text)
    text = text.strip(" ,，.。;；:：'\"“”‘’()（）[]【】<>《》")
    return text


def _is_cjk(s: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", s or ""))


def _postprocess_entities(entities):
    normalized = []
    seen = set()
    for ent in entities or []:
        if not isinstance(ent, dict):
            continue
        raw_text = ent.get("text", "")
        ent_type = ent.get("type") or ent.get("label") or "Entity"
        text = _normalize_entity_text(raw_text)
        if not text:
            continue

        key = (text, ent_type)
        if key in seen:
            continue
        seen.add(key)

        item = dict(ent)
        item["text"] = text
        item["type"] = ent_type
        item["label"] = ent.get("label") or ent_type
        normalized.append(item)

    filtered = []
    for ent in normalized:
        text = ent.get("text", "")
        ent_type = (ent.get("type") or "").upper()
        label = ent.get("label") or ""
        text_len = len(text)

        if label not in {"TicketNo", "TimeRange", "Voltage"}:
            if re.fullmatch(r"\d{1,3}", text) and ent_type in {"EQUIPMENT", "LOCATION"}:
                continue

            if ent_type == "LOCATION" and re.search(r"(断路器|开关|刀闸|母线|变压器|电缆|线路|间隔|保护|GIS)", text):
                ent_type = "EQUIPMENT"
                ent["type"] = "EQUIPMENT"
                ent["label"] = ent.get("label") or "EQUIPMENT"

            if ent_type == "LOCATION" and re.search(r"(应装|应合|应拉|应拆|应挂|退出|投入|检查|确认|装设|拆除|合上|拉开)", text):
                ent_type = "ACTION"
                ent["type"] = "ACTION"
                ent["label"] = ent.get("label") or "ACTION"

            if ent_type == "EQUIPMENT" and re.search(r"(应装|应合|应拉|应拆|应挂|退出|投入|检查|确认|装设|拆除|合上|拉开)", text):
                ent_type = "ACTION"
                ent["type"] = "ACTION"
                ent["label"] = ent.get("label") or "ACTION"

            if ent_type == "EQUIPMENT" and re.search(r"\b\d{1,3}\s*(kV|KV|kv|V|v)\b", text):
                ent_type = "VOLTAGE"
                ent["type"] = "VOLTAGE"
                ent["label"] = ent.get("label") or "Voltage"

        if ent_type == "TIME":
            if text_len < 4:
                continue
        elif ent_type == "CODE":
            if text_len <= 1 and not re.fullmatch(r"[0-9A-Za-z]+", text):
                continue
        elif ent_type == "PERSON":
            if text_len < 2 or text_len > 6:
                continue
        elif ent_type == "LOCATION":
            if text_len < 3:
                continue
            if text_len > 25:
                continue
        elif ent_type in {"EQUIPMENT", "SAFETY", "ACTION"}:
            if text_len < 2:
                continue
            if ent_type == "EQUIPMENT" and text_len > 25:
                continue
            if ent_type == "ACTION" and text_len > 60:
                continue

        if re.search(r"(计划工作时间|安全措施|工作票终结|工作地点|工作内容|作业任务)", text):
            continue

        if _is_cjk(text) and text_len == 1:
            continue

        filtered.append(ent)

    return filtered


def _extract_ticket_no(entities: list[dict]) -> str:
    for ent in entities or []:
        if not isinstance(ent, dict):
            continue
        label = ent.get("label") or ""
        if label == "TicketNo":
            text = ent.get("text") or ""
            if text:
                return str(text)
    return ""


def _rule_entities_from_text(text: str):
    ents = []
    compact = (text or "").replace("_", " ")

    m = re.search(r"(?:工作票|工单)?编号\W*([0-9]{6,})", compact)
    if m:
        ents.append({"text": m.group(1), "type": "CODE", "label": "TicketNo"})

    m = re.search(r"(?:工作|作业|工单)地点\s*[:：]\s*([^\n]+)", compact)
    if m:
        value = _normalize_entity_text(m.group(1))
        if value and len(value) >= 3:
            ents.append({"text": value, "type": "LOCATION", "label": "Location"})

    m = re.search(r"(工作内容|工单内容|作业任务|工作任务)\s*[:：]\s*([^\n]+)", compact)
    if m:
        value = _normalize_entity_text(m.group(2))
        if value and len(value) >= 2:
            ents.append({"text": value, "type": "CONTENT", "label": "Content"})

    role_patterns: list[tuple[str, str]] = [
        ("工作负责人", "RESPONSIBLE_PERSON"),
        ("工单负责人", "RESPONSIBLE_PERSON"),
        ("工作许可人", "PERMITTER_PERSON"),
        ("工作票签发人", "ISSUER_PERSON"),
        ("工作签发人", "ISSUER_PERSON"),
        ("签发人", "ISSUER_PERSON"),
        ("现场监护人", "GUARDIAN_PERSON"),
        ("监护人", "GUARDIAN_PERSON"),
    ]
    for role_label, role_type in role_patterns:
        m = re.search(
            rf"{re.escape(role_label)}\s*[:：]\s*([\u4e00-\u9fff]{{2,6}})",
            compact,
        )
        if not m:
            continue
        name = _normalize_entity_text(m.group(1))
        if name:
            ents.append({"text": name, "type": "PERSON", "label": role_type})

    m = re.search(r"工作班成员\s*[:：]\s*([^\n]+)", compact)
    if m:
        value = _normalize_entity_text(m.group(1))
        names = re.split(r"[,\s，、/]+", value)
        for name in names:
            name = _normalize_entity_text(name)
            if not name:
                continue
            if not _is_cjk(name):
                continue
            if len(name) < 2 or len(name) > 6:
                continue
            ents.append({"text": name, "type": "PERSON", "label": "CREW_MEMBER"})

    for m in re.finditer(r"安全措施\s*[:：]\s*([^\n]+)", compact):
        value = m.group(1) or ""
        for part in re.split(r"[;；。\.，,、]+", value):
            measure = _normalize_entity_text(part)
            if not measure:
                continue
            if len(measure) < 2 or len(measure) > 80:
                continue
            ents.append({"text": measure, "type": "SAFETY", "label": "SAFETY"})

    m = re.search(r"(?:工作票|工单)状态\s*[:：]\s*([\u4e00-\u9fff，,]{2,30})", compact)
    if m:
        value = _normalize_entity_text(m.group(1))
        if value:
            ents.append({"text": value, "type": "TICKET_STATUS", "label": "TICKET_STATUS"})

    if re.search(r"工作票\s*终结", compact):
        ents.append({"text": "已终结", "type": "TICKET_STATUS", "label": "TICKET_STATUS"})

    for m in re.finditer(
        r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日(?:\s*\d{1,2}\s*[:时]\s*\d{1,2}(?:\s*[:分]\s*\d{1,2})?)?",
        compact,
    ):
        value = re.sub(r"\s+", "", m.group(0))
        ents.append({"text": value, "type": "TIME", "label": "TimePoint"})

    volts = set()
    for m in re.finditer(r"\b(\d{1,3})(?:\.\d+)?\s*(kV|KV|kv|v|V)\b", compact):
        volts.add(f"{m.group(1)}{m.group(2)}".upper())
    for v in sorted(volts):
        ents.append({"text": v, "type": "VOLTAGE", "label": "Voltage"})

    m = re.search(
        r"自\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*\d{1,2}\s*时\s*\d{1,2}\s*分)\s*至\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*\d{1,2}\s*时\s*\d{1,2}\s*分)",
        compact,
    )
    if m:
        start = re.sub(r"\s+", "", m.group(1))
        end = re.sub(r"\s+", "", m.group(2))
        ents.append({"text": f"{start}~{end}", "type": "TIME", "label": "TimeRange"})

    return ents


def run(
    image_path,
    enable_ollama=False,
    enable_neo4j=False,
    llm_provider: str | None = None,
    ocr_engine: str | None = None,
):
    """
    执行统一的OCR和NER流水线

    Args:
        image_path: 输入图像路径
        enable_ollama: 是否启用大模型进行低置信度实体校验和关系抽取
        enable_neo4j: 是否启用Neo4j图谱写入
        llm_provider: 大模型提供方，支持 'ollama' 或 'aliyun'，为空则使用配置
        ocr_engine: OCR 流水线；为空时读取配置，默认 PPStructureV3

    Returns:
        包含处理结果的字典
    """
    p = Path(image_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    image_path = p
    if not image_path.exists():
        return {"error": f"image not found: {image_path}"}

    filename = image_path.stem
    ocr_out = Path(config.OUTPUT_DIR) / f"{filename}.json"
    ner_out = Path(config.OUTPUT_DIR) / f"{filename}_ner.json"

    # 执行OCR处理
    ocr_cmd = [
        config.PADDLE_PYTHON,
        config.OCR_PRE_SCRIPT,
        "--image_path",
        str(image_path),
        "--output_dir",
        config.OUTPUT_DIR,
        "--ocr_engine",
        ocr_engine or config.OCR_ENGINE,
    ]
    if config.OCR_USE_OPENCV_PREPROCESS:
        ocr_cmd.append("--opencv_preprocess")
    _run(ocr_cmd, cwd=Path(config.PADDLE_PROJECT_ROOT))
    if not ocr_out.exists():
        return {"error": "ocr json not found"}

    # 执行NER处理。复制版项目可能不包含私有训练数据与checkpoint；
    # 只有在模型资产完整时才启动BERT，否则明确降级到规则提取。
    bert_assets, bert_skip_reason = _find_bert_model_assets()
    if bert_assets:
        ner_cmd = [
            config.BERT_PYTHON,
            config.NER_SCRIPT,
            "--ocr_json",
            str(ocr_out),
            "--output_json",
            str(ner_out),
        ]
        _env = dict(**os.environ)
        _env["PYTHONPATH"] = str(Path(config.BERT_PROJECT_ROOT)) + (
            ";" + _env["PYTHONPATH"] if "PYTHONPATH" in _env and _env["PYTHONPATH"] else ""
        )
        _run(ner_cmd, cwd=Path(config.BERT_PROJECT_ROOT), env=_env)
        if not ner_out.exists():
            return {"error": "ner json not found"}

        with ner_out.open("r", encoding="utf-8") as f:
            ner_data = json.load(f)
        raw_entities = _collect_entities_from_ner(ner_data)
        ner_mode = "bert_mrc"
    else:
        print(f"BERT-MRC unavailable; using rule fallback: {bert_skip_reason}")
        ner_data = {
            "mode": "rule_fallback",
            "warning": bert_skip_reason,
            "blocks": [],
            "entities": [],
            "mrc_model": None,
        }
        raw_entities = []
        ner_mode = "rule_fallback"

    # 获取OCR文本内容用于关系抽取
    with ocr_out.open("r", encoding="utf-8") as f:
        ocr_data = json.load(f)

    ocr_text = _extract_text_from_ocr_json(ocr_data)
    entities = _postprocess_entities(raw_entities)
    rule_entities = _rule_entities_from_text(ocr_text)
    entities = _postprocess_entities(entities + rule_entities)
    ner_data["entities"] = entities
    if ner_mode == "rule_fallback" and ocr_text:
        ner_data["blocks"] = [{"text": ocr_text, "entities": entities}]

    # 保存最终结构，确保规则降级模式与BERT模式都能被UI/API读取。
    ner_out.parent.mkdir(parents=True, exist_ok=True)
    ner_out.write_text(
        json.dumps(ner_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 初始化返回结果
    result = {
        "status": "success",
        "ocr_json": str(ocr_out),
        "ner_json": str(ner_out),
        "ner": ner_data,
        "ner_mode": ner_mode,
        "cypher": "",
        "llm_results": None,
        "neo4j_write_status": None,
        "stats": {
            "block_count": len(ner_data.get("blocks") or []),
            "raw_entity_count": len(raw_entities),
            "post_entity_count": len(entities),
            "rule_entity_count": len(rule_entities),
        },
    }

    # 如果启用了大模型阶段
    if enable_ollama:
        print("正在使用大模型进行低置信度实体校验...")
        validated_entities = validate_low_confidence_entities(
            entities,
            provider=llm_provider,
        )
        entities = validated_entities
        result["ner"]["entities"] = validated_entities

        print("正在使用大模型进行实体关系抽取...")
        relationships = extract_entity_relationships(
            entities,
            ocr_text,
            provider=llm_provider,
        )
        result["llm_results"] = {
            "relationships": relationships
        }
        rel_list = relationships.get("relationships", []) if isinstance(relationships, dict) else []
        print(f"抽取到 {len(rel_list)} 条关系")

    # 如果启用了Neo4j写入功能
    if enable_neo4j:
        print("正在写入实体和关系到Neo4j...")
        neo4j_config = {
            'uri': config.NEO4J_URI,
            'user': config.NEO4J_USER,
            'password': config.NEO4J_PASSWORD
        }

        rel_payload = result["llm_results"]["relationships"] if result["llm_results"] else []
        rel_list = rel_payload.get("relationships", []) if isinstance(rel_payload, dict) else (rel_payload or [])

        ticket_id = generate_ticket_id(str(image_path))
        ticket_no = _extract_ticket_no(entities) or filename
        write_success = write_full_graph_to_neo4j(
            ticket_id=ticket_id,
            ticket_no=ticket_no,
            entities=entities,
            relationships=rel_list,
            neo4j_config=neo4j_config,
            overwrite=True,
        )
        result["neo4j_write_status"] = write_success
        print(f"Neo4j写入状态: {'成功' if write_success else '失败'}")

    # 读取可能生成的Cypher文件
    cypher = Path(config.OUTPUT_DIR) / f"{filename}_ner_graph.cypher"
    cypher_str = ""
    if cypher.exists():
        cypher_str = cypher.read_text(encoding="utf-8")
    result["cypher"] = cypher_str

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--image_path", required=True, help="输入图像路径")
    parser.add_argument("--enable_ollama", action="store_true", help="启用大模型进行低置信度实体校验和关系抽取")
    parser.add_argument("--enable_neo4j", action="store_true", help="启用Neo4j图谱写入")
    parser.add_argument("--llm_provider", type=str, choices=["ollama", "aliyun"], help="大模型提供方，默认读取配置")
    parser.add_argument(
        "--ocr_engine",
        choices=["ppstructure-v3", "paddleocr-vl-1.5", "paddleocr-vl-1.6"],
        help="OCR 流水线，默认读取配置",
    )
    args = parser.parse_args()

    res = run(
        args.image_path,
        enable_ollama=args.enable_ollama,
        enable_neo4j=args.enable_neo4j,
        llm_provider=args.llm_provider,
        ocr_engine=args.ocr_engine,
    )
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
