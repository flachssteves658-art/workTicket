from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import shutil
import os
import uuid
import re
import json
from datetime import datetime
from pathlib import Path
from . import config, unified_pipeline
from . import neo4j_client
from . import hazard_dbm_client
from . import ollama_client

# 创建 FastAPI 应用实例，用于提供工作票解析相关的 HTTP 接口
app = FastAPI(
    title="Work Ticket Intelligent Parsing API",
    description="API for parsing electrical work tickets using PaddleOCR and BERT-MRC.",
    version="1.0.0"
)


def _neo4j_first_row(resp: dict) -> dict | None:
    results = resp.get("results") if isinstance(resp, dict) else None
    if not results:
        return None
    data = results[0].get("data") if isinstance(results[0], dict) else None
    if not data:
        return None
    row = data[0].get("row") if isinstance(data[0], dict) else None
    cols = results[0].get("columns") if isinstance(results[0], dict) else None
    if not row or not cols:
        return None
    return dict(zip(cols, row))


def _fetch_ticket_graph_summary(ticket_no: str) -> dict | None:
    if not ticket_no:
        return None
    cypher = """
        MATCH (t:Ticket {ticket_no: $ticket_no})
        WITH t ORDER BY coalesce(t.updated_at, 0) DESC LIMIT 1
        OPTIONAL MATCH (t)-[:HAS_ENTITY]->(e:Entity)
        RETURN
            t.ticket_id AS ticket_id,
            t.ticket_no AS ticket_no,
            collect(DISTINCT {entity_id: e.entity_id, type: e.type, name: e.name}) AS entities
    """
    resp = neo4j_client.run_cypher_http(
        uri=config.NEO4J_URI,
        user=config.NEO4J_USER,
        password=config.NEO4J_PASSWORD,
        cypher=cypher,
        parameters={"ticket_no": ticket_no},
    )
    row = _neo4j_first_row(resp)
    if not row:
        return None
    entities = row.get("entities") or []
    by_type: dict[str, list[dict]] = {}
    for e in entities:
        if not isinstance(e, dict):
            continue
        t = hazard_dbm_client.safe_str(e.get("type")).upper() or "UNKNOWN"
        by_type.setdefault(t, []).append(e)
    ticket_fields: dict[str, object] = {}
    ticket_fields["ticket_no"] = row.get("ticket_no")
    ticket_fields["work_location"] = hazard_dbm_client.first_entity_text(
        entities,
        labels={"Location"},
        types={"LOCATION"},
    )
    ticket_fields["work_content"] = hazard_dbm_client.first_entity_text(
        entities,
        labels={"Content"},
        types={"CONTENT"},
    )
    ticket_fields["time_range"] = hazard_dbm_client.first_entity_text(
        entities,
        labels={"TimeRange"},
        types={"TIMERANGE", "TIME"},
    )
    role_type_map: list[tuple[str, str]] = [
        ("responsible_person", "RESPONSIBLE_PERSON"),
        ("permitter_person", "PERMITTER_PERSON"),
        ("issuer_person", "ISSUER_PERSON"),
        ("guardian_person", "GUARDIAN_PERSON"),
    ]
    for key, type_name in role_type_map:
        items = by_type.get(type_name) or []
        ticket_fields[key] = (
            hazard_dbm_client.safe_str(items[0].get("name"))
            if items and isinstance(items[0], dict)
            else None
        )
    members = []
    for item in by_type.get("CREW_MEMBER") or []:
        if isinstance(item, dict):
            name = hazard_dbm_client.safe_str(item.get("name"))
            if name:
                members.append(name)
    ticket_fields["crew_members"] = members
    safety_measures = []
    for item in by_type.get("SAFETY") or []:
        if isinstance(item, dict):
            name = hazard_dbm_client.safe_str(item.get("name"))
            if name:
                safety_measures.append(name)
    ticket_fields["safety_measures"] = safety_measures
    status_items = by_type.get("TICKET_STATUS") or []
    ticket_fields["ticket_status"] = (
        hazard_dbm_client.safe_str(status_items[0].get("name"))
        if status_items and isinstance(status_items[0], dict)
        else None
    )
    return {
        "ticket_id": row.get("ticket_id"),
        "ticket_no": row.get("ticket_no"),
        "entities_by_type": by_type,
        "ticket_fields": ticket_fields,
    }

def _build_local_agent_report(
    ticket_no: str,
    ticket_fields: dict | None,
    violation: dict,
) -> str:
    fields = ticket_fields or {}
    site = hazard_dbm_client.safe_str(violation.get("site"))
    stream_name = hazard_dbm_client.safe_str(violation.get("stream_name"))
    detection_time = hazard_dbm_client.safe_str(violation.get("detection_time"))
    work_location = hazard_dbm_client.safe_str(fields.get("work_location"))
    work_content = hazard_dbm_client.safe_str(fields.get("work_content"))
    time_range = hazard_dbm_client.safe_str(fields.get("time_range"))
    responsible_person = hazard_dbm_client.safe_str(fields.get("responsible_person"))
    permitter_person = hazard_dbm_client.safe_str(fields.get("permitter_person"))
    guardian_person = hazard_dbm_client.safe_str(fields.get("guardian_person"))
    issuer_person = hazard_dbm_client.safe_str(fields.get("issuer_person"))
    crew_members = fields.get("crew_members") if isinstance(fields.get("crew_members"), list) else []
    safety_measures = fields.get("safety_measures") if isinstance(fields.get("safety_measures"), list) else []
    ticket_status = hazard_dbm_client.safe_str(fields.get("ticket_status"))
    warnings = violation.get("warnings") if isinstance(violation, dict) else None
    warnings_json = json.dumps(warnings, ensure_ascii=False) if warnings is not None else "null"

    parts: list[str] = []
    parts.append("一、作业基本情况：")
    parts.append(f"工作票编号：{ticket_no or '未知'}；站点：{site or '未知'}；视频流：{stream_name or '未知'}；检测时间：{detection_time or '未知'}。")
    if work_location:
        parts.append(f"作业地点：{work_location}。")
    if work_content:
        parts.append(f"作业内容：{work_content}。")
    if time_range:
        parts.append(f"计划起止时间：{time_range}。")
    leader_bits = []
    if responsible_person:
        leader_bits.append(f"工作负责人：{responsible_person}")
    if permitter_person:
        leader_bits.append(f"工作许可人：{permitter_person}")
    if issuer_person:
        leader_bits.append(f"签发人：{issuer_person}")
    if guardian_person:
        leader_bits.append(f"监护人：{guardian_person}")
    if leader_bits:
        parts.append("；".join(leader_bits) + "。")
    if crew_members:
        parts.append(f"工作班成员：{('、'.join([hazard_dbm_client.safe_str(x) for x in crew_members if hazard_dbm_client.safe_str(x)]))}。")
    if ticket_status:
        parts.append(f"工作票状态：{ticket_status}。")

    parts.append("二、违章与规则匹配分析：")
    parts.append(f"视觉检测告警摘要：{warnings_json}。")
    parts.append("三、风险等级判断：")
    parts.append("当前风险等级：中。需结合现场复核与作业许可状态进一步调整。")
    parts.append("四、整改与跟进建议：")
    if safety_measures:
        parts.append(f"核对并落实安全措施：{('；'.join([hazard_dbm_client.safe_str(x) for x in safety_measures if hazard_dbm_client.safe_str(x)]))}。")
    parts.append("对检测到的违章行为立即制止并复核工作票信息与现场一致性。")
    parts.append("对关键岗位（负责人/许可人/监护人）履职情况进行抽查并留痕。")
    return "\n".join([p for p in parts if p])


@app.post("/api/v1/generate_violation_report")
async def generate_violation_report(payload: dict):
    ticket_no = (payload.get("ticket_no") or "").strip()
    violation = payload.get("violation") or {}
    graph = _fetch_ticket_graph_summary(ticket_no) if ticket_no else None
    enable_llm = bool(payload.get("enable_llm", True))
    llm_provider = payload.get("llm_provider") or None
    llm_model = payload.get("llm_model") or None
    agent_report = None
    agent_error = None
    ticket_fields = graph.get("ticket_fields") if isinstance(graph, dict) else None
    if enable_llm:
        try:
            violation_text = json.dumps(violation, ensure_ascii=False)
            graph_text = json.dumps(graph, ensure_ascii=False) if graph is not None else "null"
            fields_text = json.dumps(ticket_fields, ensure_ascii=False) if ticket_fields is not None else "null"
            prompt = (
                "你是一个电力施工现场安全分析专家，需要根据多源信息生成结构化、语义清晰的安全预警分析报告。\n\n"
                "已知信息包括：\n"
                f"1. 工作票编号: {ticket_no or '未知'}。\n"
                "2. 工作票关键信息（结构化提取）如下（JSON）：\n"
                f"{fields_text}\n\n"
                "3. 工作票关联的知识图谱摘要（按实体类型组织）如下（JSON）：\n"
                f"{graph_text}\n\n"
                "4. 视觉违章检测结果（包含工地名称、摄像头/视频流名称、检测时间、检测到的危险类型及计数等），以 JSON 给出如下：\n"
                f"{violation_text}\n\n"
                "请你综合以上信息，按照下面固定结构输出一段中文报告文本：\n"
                "一、作业基本情况：概述作业地点、设备、计划工作时间等关键信息；如图谱信息不足，可说明“信息不足”。\n"
                "二、违章与规则匹配分析：逐条描述检测到的危险事件，分别说明违反了哪些典型安全要求或规程条款（无需给出具体条款号时可概括，例如“进入受控区域”“未佩戴安全帽”等）。\n"
                "三、风险等级判断：给出整体风险等级（低/中/高），并归纳最需要优先关注的 1-3 项问题。\n"
                "四、整改与跟进建议：给出 3 条以内具体可执行的整改和现场管控建议。\n\n"
                "要求：仅输出上述四个部分的连续中文文本，可以使用分段或编号小标题，但不要输出 JSON 或表格，也不要额外解释你的推理过程。"
            )
            messages = [
                {"role": "user", "content": prompt},
            ]
            agent_report = ollama_client._call_llm(
                messages=messages,
                provider=llm_provider,
                model=llm_model,
                temperature=0.1,
            )
        except Exception as e:
            agent_error = str(e)
    if not agent_report:
        agent_report = _build_local_agent_report(
            ticket_no=ticket_no,
            ticket_fields=ticket_fields if isinstance(ticket_fields, dict) else None,
            violation=violation if isinstance(violation, dict) else {},
        )
    return JSONResponse(
        content={
            "status": "success",
            "ticket_no": ticket_no or None,
            "violation": violation,
            "graph_summary": graph,
            "agent_report": agent_report,
            "agent_error": agent_error,
        }
    )


@app.post("/api/v1/parse_ticket")
async def parse_ticket(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str | None = None,
    enable_neo4j: bool = False,
    enable_hazard_sync: bool = False,
    hazard_site_name: str | None = None,
):
    """
    上传一张工作票图片（JPG/PNG），调用统一流水线进行解析，返回实体识别、
    关系抽取以及可选的图谱写入结果。

    Args:
        file: 上传的工作票图片文件（multipart/form-data）
        enable_llm: 是否启用大模型阶段（实体校验 + 关系抽取）
        llm_provider: 大模型提供方（如 "ollama"、"aliyun"），为空则走默认配置
        enable_neo4j: 是否在解析完成后写入 Neo4j 图数据库
    """
    # 校验上传文件类型，要求为图片（例如 image/png, image/jpeg）
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    # 为本次请求生成一个会话 ID，避免并发请求之间的文件名冲突
    session_id = uuid.uuid4().hex
    temp_filename = f"upload_{session_id}_{file.filename}"
    temp_file_path = Path(config.OUTPUT_DIR) / temp_filename

    try:
        # 将上传的文件流落地保存到本地临时目录，供后续 OCR / NER 使用
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 调用统一流水线：
        # 1. 图像预处理 + PaddleOCR
        # 2. BERT-MRC 实体抽取
        # 3. 可选：大模型实体校验 + 关系抽取
        # 4. 可选：写入 Neo4j 图数据库
        result = unified_pipeline.run(
            str(temp_file_path),
            enable_ollama=enable_llm,
            enable_neo4j=enable_neo4j,
            llm_provider=llm_provider or None,
        )

        # 统一流水线如果返回 error 字段，视为内部错误，向前端抛 500
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        if enable_hazard_sync:
            try:
                entities = (result.get("ner") or {}).get("entities") or []
                site_name = (hazard_site_name or "").strip() or hazard_dbm_client.first_entity_text(
                    entities,
                    labels={"Location"},
                    types={"LOCATION"},
                )
                ticket_no = hazard_dbm_client.first_entity_text(entities, labels={"TicketNo"}) or Path(
                    str(temp_file_path)
                ).stem
                time_range = hazard_dbm_client.first_entity_text(
                    entities,
                    labels={"TimeRange"},
                    types={"TIME"},
                )
                start_dt, end_dt = _parse_time_range(time_range)

                if not site_name:
                    raise ValueError("site_name not found from entities")

                payload: dict = {
                    "site_name": site_name,
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

                resp = hazard_dbm_client.apply_ticket_to_site(
                    config.HAZARD_DBM_BASE_URL,
                    config.HAZARD_INTEGRATION_TOKEN,
                    payload,
                )
                result["hazard_sync"] = resp
            except Exception as sync_exc:
                result["hazard_sync"] = {"error": str(sync_exc)}

        # 将完整结果以 JSON 返回，包含 OCR/NER/关系抽取/图谱写入状态等
        return JSONResponse(content=result)

    except Exception as e:
        # 捕获所有异常并转为 HTTP 500，方便前端统一处理错误信息
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 可选：在这里删除临时文件
        # 当前保留文件，便于排查问题或复现同一张票据
        pass


def _parse_cn_datetime(s: str) -> datetime | None:
    s = (s or "").strip()
    m = re.fullmatch(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})时(\d{1,2})分",
        s,
    )
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi)


def _parse_time_range(s: str) -> tuple[datetime | None, datetime | None]:
    s = (s or "").strip()
    if "~" in s:
        a, b = s.split("~", 1)
        return _parse_cn_datetime(a), _parse_cn_datetime(b)
    m = re.search(r"自(.+?)至(.+)", s)
    if m:
        return _parse_cn_datetime(m.group(1).strip()), _parse_cn_datetime(m.group(2).strip())
    return None, None


if __name__ == "__main__":
    # 直接运行该文件时，启动一个简单的 Uvicorn 开发服务器
    import uvicorn

    print("Starting API Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
