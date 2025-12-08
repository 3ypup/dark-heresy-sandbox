import os
import json
from typing import Any, Dict

import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


class OllamaError(Exception):
    pass


async def generate_json(prompt: str, system_prompt: str | None = None) -> Dict[str, Any]:
    """
    Вызов Ollama /api/generate с форматированием в JSON.
    Возвращает dict, полученный из ответа модели.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",  # просим строгий JSON
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            raise OllamaError(f"Ollama error: {resp.status_code} {resp.text}")

        data = resp.json()
        raw = data.get("response")
        if not raw:
            raise OllamaError("Empty response from Ollama")

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise OllamaError(f"Failed to parse JSON from Ollama: {e}\nRaw: {raw}") from e

