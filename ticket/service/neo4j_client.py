import base64
import urllib.request
import json
import urllib.error
import hashlib
import re
from typing import Dict, Any, List, Optional


def generate_ticket_id(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return hashlib.sha256(str(image_path).encode("utf-8")).hexdigest()


def _legacy_tx_uri(uri: str) -> str:
    if "/db/" in uri and uri.endswith("/tx/commit"):
        return re.sub(r"/db/[^/]+/tx/commit$", "/db/data/transaction/commit", uri)
    return uri


def run_cypher_http_statements(
    uri: str,
    user: str,
    password: str,
    statements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = {"statements": statements}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(uri, data=data)

    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            legacy = _legacy_tx_uri(uri)
            if legacy != uri:
                return run_cypher_http_statements(legacy, user, password, statements)
        raise Exception(f"Neo4j Cypher执行失败: HTTP {e.code}")
    except Exception as e:
        raise Exception(f"Neo4j Cypher执行失败: {str(e)}")


def run_cypher_http(
    uri: str,
    user: str,
    password: str,
    cypher: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return run_cypher_http_statements(
        uri,
        user,
        password,
        [{"statement": cypher, "parameters": parameters or {}}],
    )


def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s)
    return s


def _entity_id(ticket_id: str, ent_type: str, text: str) -> str:
    base = f"{ent_type}:{_normalize_text(text).lower()}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"{ticket_id}:{h}"


def _rel_id(ticket_id: str, subject_id: str, rel_type: str, object_id: str) -> str:
    base = f"{subject_id}:{rel_type}:{object_id}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"{ticket_id}:{h}"


def ensure_constraints(neo4j_config: Dict[str, str]) -> bool:
    statements = [
        {
            "statement": "CREATE CONSTRAINT ticket_id_unique IF NOT EXISTS FOR (t:Ticket) REQUIRE t.ticket_id IS UNIQUE",
            "parameters": {},
        },
        {
            "statement": "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
            "parameters": {},
        },
        {
            "statement": "CREATE CONSTRAINT rel_id_unique IF NOT EXISTS FOR ()-[r:REL]-() REQUIRE r.rel_id IS UNIQUE",
            "parameters": {},
        },
    ]
    try:
        run_cypher_http_statements(
            neo4j_config["uri"],
            neo4j_config["user"],
            neo4j_config["password"],
            statements,
        )
        return True
    except Exception as e:
        print(f"Neo4j 约束创建失败: {str(e)}")
        return False


def _build_entity_rows(ticket_id: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for ent in entities or []:
        if not isinstance(ent, dict):
            continue
        text = ent.get("text") or ""
        if not text:
            continue
        ent_type = ent.get("label") or ent.get("type") or "Entity"
        ent_type = str(ent_type)
        eid = _entity_id(ticket_id, ent_type, text)
        if eid in seen:
            continue
        seen.add(eid)
        rows.append(
            {
                "entity_id": eid,
                "name": text,
                "type": ent_type,
            }
        )
    return rows


def _build_relationship_rows(
    ticket_id: str,
    entities: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    entity_rows = _build_entity_rows(ticket_id, entities)
    norm_to_id: Dict[str, str] = {}
    for row in entity_rows:
        norm_to_id[_normalize_text(row["name"]).lower()] = row["entity_id"]

    rows: List[Dict[str, Any]] = []
    seen = set()
    for rel in relationships or []:
        if not isinstance(rel, dict):
            continue
        subject = rel.get("subject") or ""
        obj = rel.get("object") or ""
        rel_type = rel.get("relation") or "RELATED_TO"
        confidence = rel.get("confidence", 1.0)

        sid = norm_to_id.get(_normalize_text(subject).lower())
        oid = norm_to_id.get(_normalize_text(obj).lower())
        if not sid or not oid:
            continue

        rid = _rel_id(ticket_id, sid, str(rel_type), oid)
        if rid in seen:
            continue
        seen.add(rid)
        rows.append(
            {
                "rel_id": rid,
                "subject_id": sid,
                "object_id": oid,
                "type": str(rel_type),
                "confidence": float(confidence) if confidence is not None else 1.0,
            }
        )
    return rows


def write_full_graph_to_neo4j(
    ticket_id: str,
    ticket_no: str,
    entities: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    neo4j_config: Dict[str, str],
    overwrite: bool = True,
) -> bool:
    constraints_ok = ensure_constraints(neo4j_config)
    if not constraints_ok:
        return False

    ticket_stmt = {
        "statement": "MERGE (t:Ticket {ticket_id: $ticket_id}) SET t.ticket_no = $ticket_no, t.updated_at = timestamp()",
        "parameters": {"ticket_id": ticket_id, "ticket_no": ticket_no or ""},
    }
    delete_stmt = {
        "statement": "MATCH (t:Ticket {ticket_id: $ticket_id}) OPTIONAL MATCH (t)-[:HAS_ENTITY]->(e:Entity) DETACH DELETE e",
        "parameters": {"ticket_id": ticket_id},
    }

    entity_rows = _build_entity_rows(ticket_id, entities)
    entity_stmt = {
        "statement": """
            MATCH (t:Ticket {ticket_id: $ticket_id})
            UNWIND $entities AS ent
            MERGE (e:Entity {entity_id: ent.entity_id})
            SET e.name = ent.name, e.type = ent.type, e.ticket_id = $ticket_id, e.updated_at = timestamp()
            MERGE (t)-[:HAS_ENTITY]->(e)
        """,
        "parameters": {"ticket_id": ticket_id, "entities": entity_rows},
    }

    rel_rows = _build_relationship_rows(ticket_id, entities, relationships)
    rel_stmt = {
        "statement": """
            UNWIND $rels AS r
            MATCH (a:Entity {entity_id: r.subject_id})
            MATCH (b:Entity {entity_id: r.object_id})
            MERGE (a)-[rel:REL {rel_id: r.rel_id}]->(b)
            SET rel.type = r.type,
                rel.confidence = r.confidence,
                rel.ticket_id = $ticket_id,
                rel.updated_at = timestamp()
        """,
        "parameters": {"ticket_id": ticket_id, "rels": rel_rows},
    }

    statements: List[Dict[str, Any]] = [ticket_stmt]
    if overwrite:
        statements.append(delete_stmt)
    statements.append(entity_stmt)
    if rel_rows:
        statements.append(rel_stmt)

    try:
        run_cypher_http_statements(
            neo4j_config["uri"],
            neo4j_config["user"],
            neo4j_config["password"],
            statements,
        )
        return True
    except Exception as e:
        print(f"Neo4j 写入失败: {str(e)}")
        return False


def execute_cypher_query(
    cypher_query: str,
    neo4j_config: Dict[str, str]
) -> bool:
    """
    Executes a raw Cypher query string against the Neo4j database.
    Useful for executing complex queries generated by other tools.
    """
    if not cypher_query or not cypher_query.strip():
        return True

    # Split by newline to get individual statements if generated by kg_builder
    # kg_builder generates MERGE ... statements separated by newlines.
    lines = [line.strip() for line in cypher_query.split('\n') if line.strip()]
    
    statements = [{"statement": line} for line in lines]
    
    try:
        # Execute in batches to avoid huge payloads
        batch_size = 50
        for i in range(0, len(statements), batch_size):
            batch = statements[i : i + batch_size]
            run_cypher_http_statements(
                neo4j_config["uri"],
                neo4j_config["user"],
                neo4j_config["password"],
                batch,
            )
        return True
    except Exception as e:
        print(f"Neo4j Raw Cypher execution failed: {str(e)}")
        return False
