import gradio as gr
import json
import re
from datetime import datetime
from pathlib import Path
import sys

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
import unified_pipeline
import config
import hazard_dbm_client


def _unique_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _extract_key_fields(ner_data: dict) -> dict:
    entities = ner_data.get("entities", []) or []

    ticket_no = []
    time_range = []
    voltage = []
    persons = []
    locations = []
    equipment = []
    safety = []
    actions = []
    codes = []

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        text = ent.get("text", "")
        ent_type = (ent.get("type") or "").upper()
        label = ent.get("label") or ""

        if label == "TicketNo":
            ticket_no.append(text)
            continue
        if label == "TimeRange":
            time_range.append(text)
            continue
        if label == "Voltage":
            voltage.append(text)
            continue
        if ent_type == "TIME":
            time_range.append(text)
            continue

        if ent_type == "PERSON":
            persons.append(text)
        elif ent_type == "LOCATION":
            locations.append(text)
        elif ent_type == "EQUIPMENT":
            equipment.append(text)
        elif ent_type == "SAFETY":
            safety.append(text)
        elif ent_type == "ACTION":
            actions.append(text)
        elif ent_type == "CODE":
            codes.append(text)

    blocks = ner_data.get("blocks", []) or []

    return {
        "ticket_no": _unique_keep_order([x for x in ticket_no if x]),
        "time_range": _unique_keep_order([x for x in time_range if x]),
        "voltage": _unique_keep_order([x for x in voltage if x]),
        "persons": _unique_keep_order([x for x in persons if x]),
        "locations": _unique_keep_order([x for x in locations if x]),
        "equipment": _unique_keep_order([x for x in equipment if x]),
        "safety": _unique_keep_order([x for x in safety if x]),
        "actions": _unique_keep_order([x for x in actions if x]),
        "codes": _unique_keep_order([x for x in codes if x]),
        "stats": {
            "block_count": len(blocks),
            "entity_count": len(entities),
        },
    }


def _extract_relations_table(result: dict):
    rel = (result.get("llm_results") or {}).get("relationships") or {}
    parsed_ok = bool(rel.get("parsed_ok")) if isinstance(rel, dict) else False
    raw = rel.get("raw", "") if isinstance(rel, dict) else ""
    rels = rel.get("relationships", []) if isinstance(rel, dict) else []

    rows = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        rows.append([
            r.get("subject", ""),
            r.get("relation", ""),
            r.get("object", ""),
            r.get("confidence", ""),
        ])

    return rows, parsed_ok, raw


def _parse_cn_datetime(value: str) -> datetime | None:
    match = re.fullmatch(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})时(\d{1,2})分",
        (value or "").strip(),
    )
    if not match:
        return None
    return datetime(*(int(part) for part in match.groups()))


def _parse_time_range(value: str) -> tuple[datetime | None, datetime | None]:
    value = (value or "").strip()
    if "~" in value:
        start, end = value.split("~", 1)
        return _parse_cn_datetime(start), _parse_cn_datetime(end)
    match = re.search(r"自(.+?)至(.+)", value)
    if match:
        return _parse_cn_datetime(match.group(1)), _parse_cn_datetime(match.group(2))
    return None, None


def _sync_hazard_task(ner_data: dict, site_name: str) -> dict:
    entities = ner_data.get("entities", []) or []
    resolved_site = (site_name or "").strip() or hazard_dbm_client.first_entity_text(
        entities,
        labels={"Location"},
        types={"LOCATION"},
    )
    ticket_no = hazard_dbm_client.first_entity_text(
        entities,
        labels={"TicketNo"},
    ) or "gradio-upload"
    time_range = hazard_dbm_client.first_entity_text(
        entities,
        labels={"TimeRange"},
        types={"TIME"},
    )
    start_dt, end_dt = _parse_time_range(time_range)
    if not resolved_site:
        raise ValueError("未识别到站点，请在页面填写识别项目中已经创建的站点名称。")

    payload = {
        "site_name": resolved_site,
        "ticket_no": ticket_no,
        "detect_no_safety_vest_or_helmet": True,
        "detect_in_restricted_area": True,
    }
    if start_dt:
        payload["active_from"] = start_dt.isoformat()
        payload["work_start_hour"] = start_dt.hour
    if end_dt:
        payload["active_to"] = end_dt.isoformat()
        payload["work_end_hour"] = end_dt.hour
    return hazard_dbm_client.apply_ticket_to_site(
        config.HAZARD_DBM_BASE_URL,
        config.HAZARD_INTEGRATION_TOKEN,
        payload,
    )


def process_image(
    image_path,
    enable_llm,
    llm_provider,
    enable_neo4j,
    enable_hazard_sync,
    hazard_site_name,
):
    if image_path is None:
        return None, None, None, None, None, None, None

    # 调用统一流水线，启用/关闭大模型和Neo4j阶段
    result = unified_pipeline.run(
        image_path,
        enable_ollama=enable_llm,
        enable_neo4j=enable_neo4j,
        llm_provider=llm_provider or None,
    )

    if "error" in result:
        err = json.dumps(result, indent=2, ensure_ascii=False)
        return err, "Error", "Error", {}, [], "Error", {"status": "未同步"}

    # NER结果结构与原先保持一致，嵌套在 result["ner"] 中
    ner_data = result.get("ner", {}) or {}

    # 实体解析结果 JSON 展示
    json_output = json.dumps(ner_data, indent=2, ensure_ascii=False)

    # 知识图谱 Cypher 展示
    cypher_output = result.get("cypher", "")

    # 简要摘要：按 block 统计实体
    blocks = ner_data.get("blocks", []) or []
    summary_lines = [f"发现 {len(blocks)} 个文本块（blocks），包含实体信息。"]
    for i, block in enumerate(blocks[:5]):  # 只展示前5个
        text = block.get("text", "")
        entities = block.get("entities", [])
        summary_lines.append(
            f"\n--- Block {i+1} ---\nText: {text[:50]}...\nEntities: {entities}\n"
        )
    if len(blocks) > 5:
        summary_lines.append("\n...")

    summary = "".join(summary_lines)

    key_fields = _extract_key_fields(ner_data)
    relations_rows, rel_parsed_ok, rel_raw = _extract_relations_table(result)
    relations_status = "OK" if rel_parsed_ok else ("Disabled" if not enable_llm else "ParseFailed")

    hazard_status = {"status": "未启用"}
    if enable_hazard_sync:
        try:
            hazard_status = {
                "status": "同步成功",
                "result": _sync_hazard_task(ner_data, hazard_site_name),
            }
        except Exception as exc:
            hazard_status = {"status": "同步失败", "error": str(exc)}

    return (
        json_output,
        cypher_output,
        summary,
        key_fields,
        relations_rows,
        relations_status,
        hazard_status,
    )


# Create Gradio Interface
with gr.Blocks(title="电力工作票智能解析系统") as demo:
    gr.Markdown("# ⚡ 电力工作票智能解析与时空关联系统")
    gr.Markdown(
        "上传工作票图片（支持扫描件/拍照件），系统将自动执行：图像增强 -> OCR版面分析 -> 文本清洗 -> BERT实体抽取 -> 大模型关系抽取 -> 知识图谱构建。"
    )

    with gr.Row():
        with gr.Column(scale=1):
            input_image = gr.Image(type="filepath", label="上传工作票图片")
            enable_llm = gr.Checkbox(
                value=True,
                label="启用大模型阶段（实体校验 + 关系抽取）",
            )
            llm_provider = gr.Radio(
                choices=["ollama", "aliyun"],
                value="ollama",
                label="大模型提供方",
            )
            enable_neo4j = gr.Checkbox(
                value=False,
                label="写入 Neo4j 图谱（需提前配置好 Neo4j 连接）",
            )
            enable_hazard_sync = gr.Checkbox(
                value=True,
                label="将工作票同步到实时视频识别项目",
            )
            hazard_site_name = gr.Textbox(
                label="视频识别站点名称",
                placeholder="必须与识别项目前端 Sites 中的名称完全一致",
            )
            submit_btn = gr.Button("开始解析", variant="primary")

        with gr.Column(scale=1):
            with gr.Tabs():
                with gr.TabItem("关键字段"):
                    key_fields_output = gr.JSON(label="Key Fields")
                with gr.TabItem("实体关系"):
                    relations_output = gr.Dataframe(
                        headers=["subject", "relation", "object", "confidence"],
                        label="Relations",
                        interactive=False,
                    )
                    relations_status_output = gr.Textbox(label="Relations Status")
                with gr.TabItem("实体解析结果 (JSON)"):
                    json_output = gr.Code(language="json", label="Structured Output")
                with gr.TabItem("知识图谱语句 (Cypher)"):
                    cypher_output = gr.Code(language="sql", label="Neo4j Import Query")
                with gr.TabItem("摘要预览"):
                    summary_output = gr.Textbox(label="Parsing Summary")
                with gr.TabItem("视频识别同步"):
                    hazard_status_output = gr.JSON(label="Hazard Sync Status")

    submit_btn.click(
        fn=process_image,
        inputs=[
            input_image,
            enable_llm,
            llm_provider,
            enable_neo4j,
            enable_hazard_sync,
            hazard_site_name,
        ],
        outputs=[
            json_output,
            cypher_output,
            summary_output,
            key_fields_output,
            relations_output,
            relations_status_output,
            hazard_status_output,
        ],
    )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7861, share=False, ssr_mode=False)
