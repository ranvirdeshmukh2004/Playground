"""
Private Model Playground — FastAPI backend.

Supports:
  • "custom"  — POST /chat  with {"message": "...", "max_tokens": N}
  • "openai"  — POST /v1/chat/completions  (standard OpenAI format)

Routes:
  • GET  /                             → frontend
  • GET  /api/models                   → list models + live status
  • POST /api/models                   → add a new model at runtime
  • DELETE /api/models/{slug}          → remove a model
  • POST /api/models/{slug}/test       → test connection to a model
  • POST /api/chat                     → chat endpoint (SSE stream)
  • POST /v1/chat/completions          → OpenAI-compatible proxy
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import MODELS, AWS_REGION

# ── Logging setup ────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
log_format = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/playground_{datetime.now().strftime('%Y%m%d')}.log"),
    ],
)
logger = logging.getLogger("playground")

# Runtime model registry (starts from config.py, can be modified via API)
_models: dict[str, dict] = dict(MODELS)
logger.info(f"Loaded {len(_models)} models from config: {list(_models.keys())}")


# ── Lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


# ── App setup ────────────────────────────────────────────────────────────
app = FastAPI(title="Private Model Playground", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_client: httpx.AsyncClient | None = None
PROXY_TIMEOUT = 300.0  # 5 minutes — needed for larger models on CPU


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(PROXY_TIMEOUT, connect=15.0))
    return _client


# ── Helpers ──────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Turn a model name into a URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _build_user_message(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[System]: {content}")
        elif role == "user":
            parts.append(f"[User]: {content}")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content}")
    return "\n".join(parts)


async def _check_model_status(slug: str) -> dict:
    cfg = _models[slug]
    base = cfg["base_url"]
    api_type = cfg.get("api_type", "custom")

    try:
        client = await _get_client()
        start = time.monotonic()

        if api_type == "openai":
            resp = await client.get(f"{base}/v1/models", timeout=8.0)
        else:
            # Use /health endpoint first (our agent_api.py supports it)
            try:
                resp = await client.get(f"{base}/health", timeout=8.0)
            except Exception:
                resp = await client.post(
                    f"{base}{cfg['endpoint']}",
                    json={"message": "ping", "max_tokens": 1},
                    timeout=10.0,
                )

        elapsed_ms = round((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            return {"status": "connected", "latency_ms": elapsed_ms}
        return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"status": "offline", "detail": "Connection refused"}
    except httpx.TimeoutException:
        return {"status": "timeout", "detail": "Health-check timed out"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ── Streaming ────────────────────────────────────────────────────────────

async def _stream_custom_api(
    base_url: str, endpoint: str, messages: list[dict], max_tokens: int = 512,
    temperature: float = 0.7, top_p: float = 0.9,
) -> AsyncGenerator[str, None]:
    client = await _get_client()
    user_message = _build_user_message(messages)
    payload = {"message": user_message, "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p}

    try:
        resp = await client.post(
            f"{base_url}{endpoint}", json=payload, timeout=PROXY_TIMEOUT,
        )

        if resp.status_code != 200:
            yield f"data: {json.dumps({'error': f'HTTP {resp.status_code}: {resp.text}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            data = resp.json()
        except Exception:
            data = {"response": resp.text}

        response_text = (
            data.get("response") or data.get("text") or data.get("content")
            or data.get("message") or data.get("output")
            or data.get("generated_text") or str(data)
        )

        chunk_size = 4
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            sse = {"choices": [{"delta": {"content": chunk}, "index": 0, "finish_reason": None}]}
            yield f"data: {json.dumps(sse)}\n\n"

        sse = {"choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]}
        yield f"data: {json.dumps(sse)}\n\n"

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Could not connect to model server. Is it running?'})}\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'Request timed out. Model may still be loading.'})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    yield "data: [DONE]\n\n"


async def _stream_openai_api(
    base_url: str, model_id: str, messages: list[dict],
    temperature: float = 0.7, max_tokens: int = 2048, top_p: float = 0.9,
) -> AsyncGenerator[str, None]:
    client = await _get_client()
    payload = {
        "model": model_id, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
        "top_p": top_p, "stream": True,
    }

    try:
        async with client.stream(
            "POST", f"{base_url}/v1/chat/completions",
            json=payload, timeout=PROXY_TIMEOUT,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                yield f"data: {json.dumps({'error': body.decode(errors='replace')})}\n\n"
                yield "data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    yield f"{line}\n\n"
    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Could not connect to model server.'})}\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'Request timed out.'})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    yield "data: [DONE]\n\n"


def _get_stream_generator(slug: str, messages: list[dict], **kwargs):
    cfg = _models[slug]
    api_type = cfg.get("api_type", "custom")

    if api_type == "openai":
        return _stream_openai_api(
            base_url=cfg["base_url"], model_id=cfg["model_id"],
            messages=messages, temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048), top_p=kwargs.get("top_p", 0.9),
        )
    else:
        return _stream_custom_api(
            base_url=cfg["base_url"], endpoint=cfg["endpoint"],
            messages=messages, max_tokens=kwargs.get("max_tokens", 512),
            temperature=kwargs.get("temperature", 0.7), top_p=kwargs.get("top_p", 0.9),
        )


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/models")
async def list_models():
    tasks = {slug: _check_model_status(slug) for slug in _models}
    statuses = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))

    result = []
    for slug, cfg in _models.items():
        result.append({
            "slug": slug,
            "name": cfg["name"],
            "model_id": cfg["model_id"],
            "description": cfg["description"],
            "size": cfg["size"],
            "context_len": cfg["context_len"],
            "api_type": cfg.get("api_type", "custom"),
            "base_url": cfg["base_url"],
            "endpoint": cfg.get("endpoint", "/chat"),
            **statuses[slug],
        })
    return result


@app.post("/api/models")
async def add_model(request: Request):
    """Add a new model at runtime via the web UI."""
    body = await request.json()

    name = body.get("name", "").strip()
    base_url = body.get("base_url", "").strip().rstrip("/")
    endpoint = body.get("endpoint", "/chat").strip()
    model_id = body.get("model_id", "").strip()
    description = body.get("description", "").strip()
    size = body.get("size", "").strip()
    context_len = int(body.get("context_len", 8192))
    api_type = body.get("api_type", "custom").strip()

    if not name:
        raise HTTPException(400, "Model name is required")
    if not base_url:
        raise HTTPException(400, "Base URL is required")

    slug = body.get("slug", "").strip() or _slugify(name)

    if slug in _models:
        raise HTTPException(409, f"Model '{slug}' already exists. Remove it first or use a different name.")

    _models[slug] = {
        "name": name,
        "base_url": base_url,
        "endpoint": endpoint,
        "model_id": model_id or name,
        "description": description or f"{name} model",
        "size": size or "?",
        "context_len": context_len,
        "api_type": api_type,
    }

    logger.info(f"MODEL ADDED: {slug} → {base_url} ({api_type})")
    return {"status": "added", "slug": slug}


@app.delete("/api/models/{slug}")
async def remove_model(slug: str):
    """Remove a model from the runtime registry."""
    if slug not in _models:
        raise HTTPException(404, f"Unknown model: {slug}")
    logger.info(f"MODEL REMOVED: {slug}")
    del _models[slug]
    return {"status": "removed", "slug": slug}


# ── Admin: IP Sync (called by Lambda) ────────────────────────────────────

@app.get("/api/admin/instances")
async def list_instances():
    """Return instance IDs for all models so Lambda knows what to query."""
    instances = {}
    for slug, cfg in _models.items():
        iid = cfg.get("instance_id")
        if iid:
            instances[slug] = {
                "instance_id": iid,
                "port": cfg.get("port", 8080),
                "current_base_url": cfg.get("base_url", ""),
            }
    return instances


@app.post("/api/admin/sync-ips")
async def sync_ips(request: Request):
    """
    Update model base_urls with fresh Public IPs.
    Called by the Lambda function after starting instances.

    Body: {"updates": {"i-xxx": "1.2.3.4", "i-yyy": "5.6.7.8", ...}}
    """
    body = await request.json()
    updates = body.get("updates", {})

    if not updates:
        raise HTTPException(400, "No updates provided")

    synced = []
    for slug, cfg in _models.items():
        iid = cfg.get("instance_id")
        if iid and iid in updates:
            new_ip = updates[iid]
            if new_ip:  # instance is running
                port = cfg.get("port", 8080)
                old_url = cfg.get("base_url", "")
                new_url = f"http://{new_ip}:{port}"
                cfg["base_url"] = new_url
                logger.info(f"IP SYNC: {slug} ({iid}) → {old_url} → {new_url}")
                synced.append({"slug": slug, "instance_id": iid, "new_url": new_url})
            else:
                logger.warning(f"IP SYNC: {slug} ({iid}) → no IP (instance stopped?)")

    return {"status": "synced", "count": len(synced), "models": synced}


@app.post("/api/models/{slug}/test")
async def test_model(slug: str):
    """Test a model's connection and return detailed results."""
    if slug not in _models:
        raise HTTPException(404, f"Unknown model: {slug}")

    status = await _check_model_status(slug)

    # If connected, try a real chat request
    if status.get("status") == "connected":
        cfg = _models[slug]
        try:
            client = await _get_client()
            if cfg.get("api_type") == "openai":
                resp = await client.post(
                    f"{cfg['base_url']}/v1/chat/completions",
                    json={"model": cfg["model_id"], "messages": [{"role": "user", "content": "Say hello in one word."}], "max_tokens": 10},
                    timeout=30.0,
                )
            else:
                resp = await client.post(
                    f"{cfg['base_url']}{cfg['endpoint']}",
                    json={"message": "Say hello in one word.", "max_tokens": 10},
                    timeout=30.0,
                )

            if resp.status_code == 200:
                data = resp.json()
                sample = (
                    data.get("response") or data.get("text")
                    or data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    or str(data)[:200]
                )
                return {**status, "test": "passed", "sample_response": sample[:200]}
            else:
                return {**status, "test": "failed", "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as exc:
            return {**status, "test": "failed", "detail": str(exc)}

    return {**status, "test": "skipped"}


@app.get("/api/models/{slug}/status")
async def model_status(slug: str):
    if slug not in _models:
        raise HTTPException(404, f"Unknown model: {slug}")
    return await _check_model_status(slug)


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    slug = body.get("model")
    if not slug or slug not in _models:
        logger.warning(f"CHAT REJECTED: unknown model '{slug}'")
        raise HTTPException(400, f"Invalid or missing model slug: {slug}")

    msgs = body.get("messages", [])
    user_msg = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "<empty>")
    max_tok = body.get("max_tokens", 512)
    logger.info(f"CHAT REQUEST: model={slug} | max_tokens={max_tok} | msg='{user_msg[:80]}'")
    t0 = time.monotonic()

    async def _logged_stream():
        gen = _get_stream_generator(
            slug=slug, messages=msgs,
            temperature=body.get("temperature", 0.7),
            max_tokens=max_tok,
            top_p=body.get("top_p", 0.9),
        )
        chunk_count = 0
        async for chunk in gen:
            chunk_count += 1
            yield chunk
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(f"CHAT COMPLETE: model={slug} | {elapsed}s | {chunk_count} chunks")

    return StreamingResponse(
        _logged_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/chat/completions")
async def openai_proxy(request: Request):
    body = await request.json()
    slug = body.get("model")
    if not slug or slug not in _models:
        raise HTTPException(400, f"Unknown model slug: {slug}. Available: {list(_models.keys())}")

    cfg = _models[slug]
    stream = body.get("stream", False)

    if stream:
        return StreamingResponse(
            _get_stream_generator(
                slug=slug, messages=body.get("messages", []),
                temperature=body.get("temperature", 0.7),
                max_tokens=body.get("max_tokens", 512),
                top_p=body.get("top_p", 0.9),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    else:
        try:
            client = await _get_client()
            if cfg.get("api_type") == "openai":
                payload = {
                    "model": cfg["model_id"], "messages": body.get("messages", []),
                    "temperature": body.get("temperature", 0.7),
                    "max_tokens": body.get("max_tokens", 512),
                    "top_p": body.get("top_p", 0.9), "stream": False,
                }
                resp = await client.post(f"{cfg['base_url']}/v1/chat/completions", json=payload, timeout=PROXY_TIMEOUT)
                return JSONResponse(status_code=resp.status_code, content=resp.json())
            else:
                user_message = _build_user_message(body.get("messages", []))
                resp = await client.post(
                    f"{cfg['base_url']}{cfg['endpoint']}",
                    json={"message": user_message, "max_tokens": body.get("max_tokens", 512)},
                    timeout=PROXY_TIMEOUT,
                )
                data = resp.json()
                response_text = (
                    data.get("response") or data.get("text") or data.get("content")
                    or data.get("message") or data.get("output") or str(data)
                )
                return JSONResponse(content={
                    "id": f"chatcmpl-{slug}-{int(time.time())}",
                    "object": "chat.completion", "model": slug,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text}, "finish_reason": "stop"}],
                })
        except httpx.ConnectError:
            raise HTTPException(502, "Could not connect to model server.")
        except httpx.TimeoutException:
            raise HTTPException(504, "Model server request timed out.")
        except Exception as exc:
            raise HTTPException(500, str(exc))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7860)

