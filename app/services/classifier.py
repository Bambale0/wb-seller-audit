from __future__ import annotations

import json
import os

import httpx

from app.models import Classification

_MARKED_KEYWORDS = ("гетр", "гамаш")


def keyword_classify(name: str) -> Classification:
    value = (name or "").lower()
    for keyword in _MARKED_KEYWORDS:
        if keyword in value:
            return Classification(
                category="legwear_marked_candidate",
                marked_candidate=True,
                confidence=0.99,
                reason=f"Название содержит ключевое слово: {keyword}",
            )
    return Classification(
        category="unknown",
        marked_candidate=False,
        confidence=0.45,
        reason="Детерминированные признаки не найдены",
    )


async def deepseek_classify(name: str) -> Classification:
    deterministic = keyword_classify(name)
    if deterministic.marked_candidate:
        return deterministic

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return deterministic

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = (
        "Классифицируй товар российского маркетплейса. "
        "Определи, похож ли он на гетры/гамаши или иной товар, для которого может требоваться маркировка. "
        "Не делай юридический вывод. Верни строго JSON с полями "
        "category, marked_candidate, confidence, reason. "
        f"Название товара: {name!r}"
    )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return Classification.model_validate(json.loads(content))
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return Classification(
            category=deterministic.category,
            marked_candidate=deterministic.marked_candidate,
            confidence=deterministic.confidence,
            reason=deterministic.reason + "; DeepSeek недоступен, использован fallback",
        )
