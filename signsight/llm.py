"""Thin wrappers around the hackathon API (assumed OpenAI-compatible).

Config comes from signsight/.env — the key is never printed or logged.
"""
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_URL = os.getenv("HACKATHON_API_URL", "").rstrip("/")
API_KEY = os.getenv("HACKATHON_API_KEY", "")
MODEL = os.getenv("HACKATHON_MODEL", "")
EMBED_MODEL = os.getenv("HACKATHON_EMBED_MODEL", "")

TIMEOUT = 90


class LLMError(RuntimeError):
    pass


def _check_config():
    missing = [name for name, val in [
        ("HACKATHON_API_URL", BASE_URL),
        ("HACKATHON_API_KEY", API_KEY),
        ("HACKATHON_MODEL", MODEL),
    ] if not val]
    if missing:
        raise LLMError(f"Missing in signsight/.env: {', '.join(missing)}")


def _post(path, payload):
    _check_config()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(2):  # one retry on rate limit / server error
        try:
            resp = requests.post(f"{BASE_URL}{path}", json=payload, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise LLMError(f"Could not reach API: {type(e).__name__}") from None
        if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            time.sleep(2)
            continue
        if not resp.ok:
            raise LLMError(f"API returned {resp.status_code}: {resp.text[:300]}")
        return resp.json()


def chat(messages, temperature=0.2, max_tokens=1024):
    """messages: [{"role": "system"|"user"|"assistant", "content": str}] -> reply text"""
    data = _post("/chat/completions", {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    })
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise LLMError(f"Unexpected chat response shape: {str(data)[:300]}") from None


def has_embeddings():
    return bool(EMBED_MODEL)


def embed(texts):
    """texts: list[str] -> list of embedding vectors (same order)."""
    if not EMBED_MODEL:
        raise LLMError("No HACKATHON_EMBED_MODEL set; use BM25 retrieval instead.")
    vectors = []
    for i in range(0, len(texts), 32):  # batch to stay under request size limits
        data = _post("/embeddings", {"model": EMBED_MODEL, "input": texts[i:i + 32]})
        try:
            items = sorted(data["data"], key=lambda d: d.get("index", 0))
            vectors.extend(item["embedding"] for item in items)
        except (KeyError, TypeError):
            raise LLMError(f"Unexpected embeddings response shape: {str(data)[:300]}") from None
    return vectors
