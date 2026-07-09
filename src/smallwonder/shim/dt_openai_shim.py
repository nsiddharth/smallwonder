"""OpenAI-images-compatible shim in front of Draw Things.

Draw Things' HTTP server implements A1111-style /sdapi/v1/txt2img and
/sdapi/v1/img2img but not the model-catalog endpoints (sd-models,
sd_model_checkpoint in options) that Open WebUI's automatic1111 engine
requires. This shim exposes the standard OpenAI images contract instead —
/v1/images/generations (create) and /v1/images/edits (img2img) — so Open
WebUI (engine: openai), LiteLLM, and any script can generate and edit images
the same way they'd call DALL-E. Uses whatever model is active in the Draw
Things app.

Runs from the litellm uv venv (fastapi/uvicorn/requests already there).
"""
import base64
import os
import time

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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


def _parse_size(size: str | None) -> tuple[int | None, int | None]:
    if not size or "x" not in (size or ""):
        return None, None
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"bad size: {size!r}") from None


def _image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Width/height from PNG or JPEG headers (no imaging library needed).
    Draw Things requires the request width/height to match the init image."""
    import struct

    if data[:8] == b"\x89PNG\r\n\x1a\n":  # PNG: IHDR is the first chunk
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:2] == b"\xff\xd8":  # JPEG: scan for a SOFn marker
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return None, None


@app.post("/v1/images/edits")
async def edits(
    prompt: str = Form(...),
    image: list[UploadFile] = File(...),
    n: int = Form(1),
    size: str | None = Form(None),
    model: str | None = Form(None),           # accepted and ignored
    response_format: str | None = Form("b64_json"),
    strength: float | None = Form(None),      # non-standard: how much to change
):
    """OpenAI images-edit contract (multipart, as Open WebUI sends it),
    backed by Draw Things img2img. First image is the init image.

    strength default depends on the active model: instruction-edit models
    (FLUX klein/Kontext, Qwen-Image-Edit) read the init image as a reference
    and need 1.0; classic img2img models regenerate from noise and want a
    partial strength (0.75)."""
    active = (
        requests.get(f"{DRAW_THINGS}/sdapi/v1/options", timeout=5).json().get("model") or ""
    ).lower()
    is_edit_model = any(k in active for k in ("klein", "kontext", "edit", "flux_2"))
    if is_edit_model:
        # Instruction-edit models read the init image as a reference; any
        # denoising below 1.0 returns a near-copy of the source. Magnitude
        # is expressed in the prompt, not the strength knob.
        strength = 1.0
    elif strength is None:
        strength = 0.75
    raw = await image[0].read()
    init = base64.b64encode(raw).decode()
    payload = {
        "init_images": [init],
        "prompt": prompt,
        "batch_size": n,
        # NOTE: Draw Things errors if both "strength" and
        # "denoising_strength" are present; the A1111 name works alone.
        "denoising_strength": strength,
    }
    w, h = _parse_size(size)
    if not (w and h):
        # Draw Things rejects a canvas that doesn't match the init image,
        # so default to the source image's own dimensions.
        w, h = _image_dimensions(raw)
    if w and h:
        if w * h > 1_800_000:  # >~1.7MP renders for many minutes on this class of hardware
            raise HTTPException(
                status_code=400,
                detail=f"image is {w}x{h}; resize to ~1024px on the long side "
                "before editing (large canvases take 10+ minutes)",
            )
        payload["width"], payload["height"] = w, h
    r = requests.post(f"{DRAW_THINGS}/sdapi/v1/img2img", json=payload, timeout=600)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Draw Things error: {r.text[:200]}")
    images = r.json().get("images", [])
    if not images:
        raise HTTPException(
            status_code=502,
            detail="Draw Things returned no images (is a model selected in the app?)",
        )
    return {"created": int(time.time()), "data": [{"b64_json": b} for b in images]}
