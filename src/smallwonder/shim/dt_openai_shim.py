"""OpenAI-images-compatible shim in front of Draw Things.

Draw Things' HTTP server implements A1111-style /sdapi/v1/txt2img but not the
model-catalog endpoints (sd-models, sd_model_checkpoint in options) that
Open WebUI's automatic1111 engine requires. This shim exposes the standard
OpenAI /v1/images/generations contract instead, so Open WebUI (engine:
openai), LiteLLM, and any script can generate images the same way they'd
call DALL-E. Uses whatever model is active in the Draw Things app.

Runs from the litellm uv venv (fastapi/uvicorn/requests already there).
"""
import os
import time

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DRAW_THINGS = os.environ.get("DRAW_THINGS_URL", "http://127.0.0.1:7860")

app = FastAPI(title="draw-things-openai-shim")


class ImageRequest(BaseModel):
    prompt: str
    n: int = 1
    size: str | None = "1024x1024"
    model: str | None = None          # accepted and ignored (app's active model)
    response_format: str | None = "b64_json"
    steps: int | None = None          # non-standard passthrough


@app.get("/health")
def health():
    r = requests.get(f"{DRAW_THINGS}/sdapi/v1/options", timeout=5)
    r.raise_for_status()
    return {"status": "ok", "active_model": r.json().get("model")}


@app.get("/v1/models")
def models():
    active = requests.get(f"{DRAW_THINGS}/sdapi/v1/options", timeout=5).json().get("model")
    return {
        "object": "list",
        "data": [{"id": active or "draw-things", "object": "model", "owned_by": "draw-things"}],
    }


@app.post("/v1/images/generations")
def generations(req: ImageRequest):
    try:
        w, h = (req.size or "1024x1024").lower().split("x")
        payload = {"prompt": req.prompt, "width": int(w), "height": int(h), "batch_size": req.n}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"bad size: {req.size!r}") from None
    if req.steps:
        payload["steps"] = req.steps
    r = requests.post(f"{DRAW_THINGS}/sdapi/v1/txt2img", json=payload, timeout=600)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Draw Things error: {r.text[:200]}")
    images = r.json().get("images", [])
    if not images:
        raise HTTPException(
            status_code=502,
            detail="Draw Things returned no images (is a model selected in the app?)",
        )
    return {"created": int(time.time()), "data": [{"b64_json": b} for b in images]}
