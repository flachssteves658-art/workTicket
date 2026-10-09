import json
import httpx
import os
from typing import List, Dict, Any, Optional

async def call_ollama(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.1,
    base_url: str = "http://localhost:11434"
) -> str:
    """
    Call Ollama API asynchronously.
    Supports images in messages via the 'images' key (list of base64 strings).
    """
    url = f"{base_url}/api/chat"
    data = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, json=data)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Ollama API call failed: {e}")

async def call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.1,
    max_tokens: int = 1024
) -> str:
    """
    Call OpenAI-compatible API (including Aliyun DashScope).
    """
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "max_tokens": max_tokens,
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("No choices in response")
            return choices[0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenAI/Aliyun API call failed: {e}")
