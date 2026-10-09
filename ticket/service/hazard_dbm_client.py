import json
import urllib.request
from typing import Any, Dict, Optional


def apply_ticket_to_site(
    base_url: str,
    integration_token: str,
    payload: Dict[str, Any],
    timeout_s: int = 30,
) -> Dict[str, Any]:
    if not base_url:
        raise ValueError("base_url is required")
    if not integration_token:
        raise ValueError("integration_token is required")

    url = base_url.rstrip("/") + "/apply_ticket_to_site"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("X-Integration-Token", integration_token)

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw}


def safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def first_entity_text(entities: list[dict], *, labels: set[str], types: Optional[set[str]] = None) -> str:
    for e in entities or []:
        if not isinstance(e, dict):
            continue
        label = safe_str(e.get("label")).strip()
        if label and label in labels:
            text = safe_str(e.get("text") or e.get("name")).strip()
            if text:
                return text
    if types:
        for e in entities or []:
            if not isinstance(e, dict):
                continue
            t = safe_str(e.get("type")).upper().strip()
            if t and t in types:
                text = safe_str(e.get("text") or e.get("name")).strip()
                if text:
                    return text
    return ""
