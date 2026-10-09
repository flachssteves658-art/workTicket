import json
import urllib.request
from typing import List, Dict, Any

import config


def call_ollama(model: str, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
    """
    调用本地Ollama大模型的API接口
    
    Args:
        model: 模型名称
        messages: 对话消息列表，格式为[{"role": "user", "content": "消息内容"}, ...]
        temperature: 生成温度，默认0.1
    
    Returns:
        模型输出的内容字符串
    """
    data = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
        j = json.loads(raw)
        content = j["message"]["content"]
        return content
    except Exception as e:
        raise Exception(f"Ollama API调用失败: {str(e)}")


def call_aliyun_chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float = 0.1,
) -> str:
    """
    调用阿里云 DashScope 兼容 OpenAI Chat 的接口
    
    Args:
        messages: 对话消息列表
        model: 模型名称，默认使用配置中的模型
        temperature: 生成温度
    
    Returns:
        模型输出的内容字符串
    """
    if not getattr(config, "ALIYUN_API_KEY", None):
        raise RuntimeError("ALIYUN_API_KEY 未配置，请设置环境变量 ALIYUN_API_KEY")
    base_url = getattr(
        config,
        "ALIYUN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ).rstrip("/")
    model_name = model or getattr(config, "ALIYUN_MODEL_NAME", "qwen-max")
    url = base_url + "/chat/completions"

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.ALIYUN_API_KEY}",
    }

    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
        j = json.loads(raw)
        choices = j.get("choices") or []
        if not choices:
            raise RuntimeError(f"阿里云接口返回异常: {raw}")
        content = choices[0]["message"]["content"]
        return content
    except Exception as e:
        raise Exception(f"阿里云API调用失败: {str(e)}")


def _call_llm(
    messages: List[Dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
) -> str:
    """
    统一的LLM调用入口，根据provider选择Ollama或阿里云
    """
    provider = provider or getattr(config, "LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        # 默认使用本地已存在的 qwen3:8b 模型
        ollama_model = model or "qwen3:8b"
        return call_ollama(ollama_model, messages, temperature=temperature)
    if provider == "aliyun":
        return call_aliyun_chat(messages, model=model, temperature=temperature)
    raise ValueError(f"不支持的LLM提供方: {provider}")


def validate_low_confidence_entities(
    entities: List[Dict[str, Any]],
    provider: str | None = None,
    model: str | None = None,
) -> List[Dict[str, Any]]:
    """
    使用大模型对低置信度实体进行校验
    
    Args:
        entities: 实体列表，包含文本、类型、位置等信息
        provider: LLM提供方，支持 'ollama' 或 'aliyun'，默认读取配置
        model: 模型名称，可选
    
    Returns:
        校验后的实体列表
    """
    # 筛选出可能需要校验的低置信度实体
    low_confidence_entities = []
    high_confidence_entities = []
    
    for entity in entities:
        # 根据实体长度和类型判断是否需要校验
        text_length = len(entity.get('text', ''))
        entity_type = (entity.get('type') or entity.get('label') or '')
        
        # 启发式规则：短文本或特定类型实体可能需要校验
        needs_validation = (
            text_length <= 2 or  # 短文本容易误识别
            str(entity_type).lower() in ['person', 'org', 'loc', 'location']  # 特定类型实体
        )
        
        if needs_validation:
            low_confidence_entities.append(entity)
        else:
            high_confidence_entities.append(entity)
    
    # 如果没有需要校验的实体，直接返回原列表
    if not low_confidence_entities:
        return entities
    
    # 构建校验提示词
    validation_prompt = f"""
你是一个专业的实体识别校验助手。请检查以下从图像中提取的实体信息是否准确：

实体列表：
{json.dumps(low_confidence_entities, ensure_ascii=False, indent=2)}

请确认这些实体是否正确识别，如果有错误请指出并提供正确的实体信息。
如果实体识别正确，请确认。
"""
    
    messages = [
        {"role": "user", "content": validation_prompt}
    ]
    
    try:
        validation_result = _call_llm(
            messages,
            provider=provider,
            model=model,
            temperature=0.1,
        )

        # 这里可以根据大模型的返回结果进一步处理实体校验
        # 为了简化，我们暂时只记录校验结果
        print(f"实体校验结果: {validation_result}")

        # 返回原始实体列表（实际应用中可根据校验结果调整实体）
        return entities
    except Exception as e:
        print(f"实体校验失败: {str(e)}")
        # 校验失败时返回原始实体列表
        return entities


def extract_entity_relationships(
    entities: List[Dict[str, Any]],
    context: str,
    provider: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    """
    使用大模型从上下文中提取实体关系

    Args:
        entities: 已识别的实体列表
        context: 上下文文本（如OCR结果）
        provider: LLM提供方，支持 'ollama' 或 'aliyun'
        model: 模型名称，可选

    Returns:
        字典，包含：
        - relationships: 实体关系列表，格式为[{'subject': '主体', 'relation': '关系', 'object': '客体'}]
        - raw: 大模型原始输出字符串
        - parsed_ok: 是否成功解析为JSON
    """
    if not entities:
        return {"relationships": [], "raw": "", "parsed_ok": True}

    # 构建关系提取提示词
    relationship_prompt = f"""
你是一个专业的实体关系抽取助手。请从以下上下文中提取实体之间的关系。

上下文：
{context}

实体列表（JSON）：
{json.dumps(entities, ensure_ascii=False, indent=2)}

请识别这些实体之间的关系，并“只输出”一个JSON数组，不能包含任何额外文本或解释。
格式要求如下（注意是数组，而不是对象）：
[
  {{
    "subject": "主体实体",
    "relation": "关系类型",
    "object": "客体实体",
    "confidence": 0.95
  }}
]

如果在上下文中没有任何可以确定的关系，请严格输出一个空数组：
[]

注意：
1. 只提取在上下文中明确表达的关系，不要推测不存在的关系。
2. 不要在JSON前后输出说明文字、注释或多余内容。
"""

    messages = [
        {"role": "user", "content": relationship_prompt}
    ]

    raw_output = ""
    parsed_ok = False
    relationships: List[Dict[str, Any]] = []

    try:
        relationships_raw = _call_llm(
            messages,
            provider=provider,
            model=model,
            temperature=0.1,
        )
        raw_output = relationships_raw

        # 尝试直接解析为JSON
        try:
            data = json.loads(relationships_raw)
            if isinstance(data, dict) and "relationships" in data:
                rels = data.get("relationships", [])
            else:
                rels = data

            if isinstance(rels, dict):
                relationships = [rels]
            elif isinstance(rels, list):
                relationships = rels
            else:
                relationships = []

            parsed_ok = True
        except json.JSONDecodeError:
            trimmed = relationships_raw.strip()
            start = trimmed.find("[")
            end = trimmed.rfind("]")
            if start != -1 and end != -1 and end > start:
                candidate = trimmed[start : end + 1]
                try:
                    data = json.loads(candidate)
                    if isinstance(data, dict) and "relationships" in data:
                        rels = data.get("relationships", [])
                    else:
                        rels = data

                    if isinstance(rels, dict):
                        relationships = [rels]
                    elif isinstance(rels, list):
                        relationships = rels
                    else:
                        relationships = []

                    parsed_ok = True
                except json.JSONDecodeError:
                    print(f"无法解析关系数据: {relationships_raw}")
                    relationships = []
                    parsed_ok = False
            else:
                print(f"无法解析关系数据: {relationships_raw}")
                relationships = []
                parsed_ok = False

        return {
            "relationships": relationships,
            "raw": raw_output,
            "parsed_ok": parsed_ok,
        }
    except Exception as e:
        print(f"关系抽取失败: {str(e)}")
        return {
            "relationships": [],
            "raw": raw_output,
            "parsed_ok": False,
        }
