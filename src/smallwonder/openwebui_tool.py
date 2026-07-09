"""The Open WebUI tool that lets chat models call image generation themselves.

Registered by `smallwonder image enable`; attached to the chat models so that
"draw me a…" in a normal conversation triggers a tool call (ChatGPT-style)
instead of a refusal. The tool body runs inside Open WebUI's python runtime.
"""

TOOL_ID = "image_studio"
TOOL_NAME = "Image Studio"

# NOTE: docstrings below become the tool spec the model sees — treat them as
# prompts. {shim_base} is filled in at registration time.
TOOL_CONTENT = '''
import requests


class Tools:
    def __init__(self):
        self.citation = False

    async def generate_image(self, prompt: str, __event_emitter__=None) -> str:
        """
        Generate an image from a text description using the local image model.
        Use this whenever the user asks you to create, draw, generate, paint,
        design, or visualize an image, picture, photo, logo, illustration,
        diagram or artwork of any kind.
        :param prompt: A detailed visual description of the image to generate — subject, style, lighting, composition.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status",
                 "data": {"description": "Generating image locally…", "done": False}}
            )
        try:
            r = requests.post(
                "{shim_base}/images/generations",
                json={"prompt": prompt, "size": "1024x1024"},
                timeout=600,
            )
            r.raise_for_status()
            b64 = r.json()["data"][0]["b64_json"]
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status",
                     "data": {"description": f"Image generation failed: {e}", "done": True}}
                )
            return (
                f"Image generation failed ({e}). Tell the user the image "
                "engine may be off — they can run `smallwonder doctor`."
            )
        if __event_emitter__:
            await __event_emitter__(
                {"type": "message",
                 "data": {"content": f"\\n![generated image](data:image/png;base64,{b64})\\n"}}
            )
            await __event_emitter__(
                {"type": "status", "data": {"description": "Image ready", "done": True}}
            )
        return (
            "The image was generated and is already displayed in the chat. "
            "Briefly (one sentence) tell the user what you created. Do NOT "
            "output the image data yourself."
        )
'''


def register(ui, shim_base: str, model_ids: list[str]) -> None:
    """Create/update the tool and attach it to the given models.

    `ui` is a smallwonder.openwebui.OpenWebUI client (admin token).
    """
    content = TOOL_CONTENT.replace("{shim_base}", shim_base)
    spec = {
        "id": TOOL_ID,
        "name": TOOL_NAME,
        "content": content,
        "meta": {"description": "Local image generation the model can invoke itself"},
        "access_control": None,  # public within this single-user instance
    }
    existing = ui.get(f"/api/v1/tools/id/{TOOL_ID}")
    if existing.status_code == 200:
        ui.post(f"/api/v1/tools/id/{TOOL_ID}/update", json=spec).raise_for_status()
    else:
        ui.post("/api/v1/tools/create", json=spec).raise_for_status()

    for model_id in model_ids:
        _attach_tool_to_model(ui, model_id)


def _attach_tool_to_model(ui, model_id: str) -> None:
    """Ensure the model's workspace entry lists our tool in meta.toolIds."""
    r = ui.get(f"/api/v1/models/model?id={model_id}")
    if r.status_code == 200 and r.json():
        model = r.json()
        meta = model.get("meta") or {}
        tool_ids = set(meta.get("toolIds") or [])
        tool_ids.add(TOOL_ID)
        meta["toolIds"] = sorted(tool_ids)
        model["meta"] = meta
        ui.post(f"/api/v1/models/model/update?id={model_id}", json=model).raise_for_status()
    else:
        ui.post(
            "/api/v1/models/create",
            json={
                "id": model_id,
                "base_model_id": None,
                "name": model_id,
                "meta": {"toolIds": [TOOL_ID]},
                "params": {},
                "access_control": None,
            },
        ).raise_for_status()
