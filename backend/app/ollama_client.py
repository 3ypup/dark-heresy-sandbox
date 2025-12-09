import os
import json
from typing import Any, Dict, Optional

import httpx


# Базовые настройки Ollama берём из переменных окружения
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")  # можно поменять через env
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "1200.0"))  # большой таймаут, по умолчанию 600 сек


class OllamaError(Exception):
    """Общее исключение для ошибок вызова Ollama."""
    pass


async def generate_json(prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Вызывает локальный Ollama (/api/generate) и ожидает, что модель вернёт
    ВНУТРИ поля `response` корректную JSON-строку.

    Ожидаемый ответ от Ollama (при stream=false и format="json"):

    {
      "model": "...",
      "created_at": "...",
      "response": "{ ... здесь JSON-строка ... }",
      "done": true,
      ...
    }

    Мы берём `response`, .strip(), и делаем json.loads(...) → Dict[str, Any].
    """
    if not OLLAMA_BASE_URL:
        raise OllamaError("OLLAMA_BASE_URL is not set")
    if not OLLAMA_MODEL:
        raise OllamaError("OLLAMA_MODEL is not set")

    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",   # просим модель вернуть JSON-строку
        "stream": False,
        "options": {
            "temperature": 0.7,
        },
    }

    # если есть системный промпт — добавим его
    if system_prompt:
        # для generate можно использовать "system" как общий контекст
        payload["system"] = system_prompt

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.RequestError as e:
        raise OllamaError(f"HTTP error calling Ollama: {e}") from e

    # Ollama сама может вернуть JSON с ключом "error"
    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        text_part = (resp.text or "")[:500]
        raise OllamaError(f"Non-JSON response from Ollama: {text_part}") from e

    if resp.status_code != 200:
        raise OllamaError(f"Ollama HTTP {resp.status_code}: {data}")

    if isinstance(data, dict) and "error" in data:
        raise OllamaError(f"Ollama error: {data.get('error')}")

    raw = ""
    if isinstance(data, dict):
        raw = (data.get("response") or "").strip()

    if not raw:
        raise OllamaError(f"Ollama returned empty response field: {data}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # если модель слегка накосячила и выдала невалидный JSON —
        # можно здесь сделать доп. обработку/логирование
        raise OllamaError(f"Failed to parse JSON from Ollama response: {raw[:500]}") from e
