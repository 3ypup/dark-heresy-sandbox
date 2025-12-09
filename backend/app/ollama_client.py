import os
import json
from typing import Any, Dict, Optional

import httpx


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
# большой таймаут – генерация на VPS может быть медленной
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "900.0"))  # сек


class OllamaError(Exception):
    """Общее исключение для ошибок вызова Ollama."""
    pass


def _try_repair_json_prefix(raw: str) -> Dict[str, Any]:
    """
    Грубый, но практичный ремонт JSON:
    - Берём строку начиная с первого '{'
    - Идём с конца к началу и ищем самый длинный префикс, который парсится как JSON.
    Это позволит вытащить хотя бы часть структуры, если модель отрубилась на полпути.
    """
    if not raw:
        raise OllamaError("Empty JSON string, nothing to repair")

    start = raw.find("{")
    if start == -1:
        raise OllamaError(f"No '{{' in response, cannot repair. Sample: {raw[:200]}")

    trimmed = raw[start:]

    # идём с конца и ищем максимальный валидный префикс
    for end in range(len(trimmed), 1, -1):
        chunk = trimmed[:end]
        try:
            obj = json.loads(chunk)
            # небольшой лог в stdout, чтобы видеть, что сработал режим ремонта
            print("[ollama_client] JSON repaired by prefix truncation at length", end)
            return obj
        except json.JSONDecodeError:
            continue

    raise OllamaError(f"Unable to repair JSON; sample: {trimmed[:200]}")


async def generate_json(prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Вызывает локальный Ollama (/api/generate) и ожидает, что модель вернёт
    ВНУТРИ поля `response` корректную JSON-строку.

    Формат ответа от Ollama (stream=false, format=\"json\"):

    {
      "model": "...",
      "created_at": "...",
      "response": "{ ... JSON-строка ... }",
      "done": true,
      ...
    }
    """
    if not OLLAMA_BASE_URL:
        raise OllamaError("OLLAMA_BASE_URL is not set")
    if not OLLAMA_MODEL:
        raise OllamaError("OLLAMA_MODEL is not set")

    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",   # просим именно JSON-строку
        "stream": False,
        "options": {
            "temperature": 0.7,
            # даём достаточно токенов, чтобы успеть дописать JSON
            "num_predict": 2048,
        },
    }

    if system_prompt:
        payload["system"] = system_prompt

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.RequestError as e:
        detail = f"{e.__class__.__name__}: {str(e) or repr(e)}"
        raise OllamaError(f"HTTP error calling Ollama: {detail}") from e

    # пробуем читать ответ Ollama как JSON
    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        text_part = (resp.text or "")[:500]
        raise OllamaError(
            f"Non-JSON response from Ollama (status={resp.status_code}): {text_part}"
        ) from e

    if resp.status_code != 200:
        raise OllamaError(f"Ollama HTTP {resp.status_code}: {data}")

    if isinstance(data, dict) and "error" in data:
        raise OllamaError(f"Ollama error: {data.get('error')}")

    raw = ""
    if isinstance(data, dict):
        raw = (data.get("response") or "").strip()

    if not raw:
        raise OllamaError(f"Ollama returned empty response field: {data}")

    # сначала честно пытаемся распарсить как есть
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # если не получилось – пробуем "подлечить" обрезанный JSON
        repaired = _try_repair_json_prefix(raw)
        return repaired
