"""Minimal client for LM Studio's OpenAI-compatible API.

Adapted from the spark-vibe kit's `_chat` (MIT, see NOTICE). Additions: image helper,
returned usage so the bench can record tokens, and a health check for `doctor`.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import config


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _client(timeout: float = 600.0) -> httpx.Client:
    return httpx.Client(base_url=config.LMSTUDIO_URL, timeout=httpx.Timeout(timeout, connect=5.0))


def image_part(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def chat(messages: list[dict], model: str, max_tokens: int = 1200, temperature: float = 0.2) -> ChatResult:
    with _client() as c:
        r = c.post("/chat/completions", json={
            "model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "reasoning_effort": config.REASONING_EFFORT,
        })
        r.raise_for_status()
        body = r.json()
    content = body["choices"][0]["message"].get("content") or ""
    usage = body.get("usage") or {}
    return ChatResult(
        text=re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip(),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


def list_models() -> list[str]:
    with _client(timeout=10.0) as c:
        r = c.get("/models")
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
