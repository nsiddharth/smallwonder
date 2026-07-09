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

    async def edit_image(
        self,
        prompt: str,
        strength: float = 0.75,
        __messages__=None,
        __files__=None,
        __event_emitter__=None,
    ) -> str:
        """
        Edit or transform the image the user attached to this chat, guided by
        a text instruction. Use this whenever the user asks you to modify,
        edit, change, restyle, retouch or transform a photo or image they
        uploaded (e.g. "give him a haircut", "make it night", "turn this into
        a watercolor").
        :param prompt: What the edited image should look like — describe the desired RESULT as a full scene, not just the change.
        :param strength: How much to change the image, 0.3 = subtle touch-up, 0.9 = heavy transformation. Default 0.75.
        """
        # Find the most recent image the user attached (multimodal message
        # content first, then chat file attachments).
        source = None
        for msg in reversed(__messages__ or []):
            content = msg.get("content")
            if isinstance(content, list):
                for part in reversed(content):
                    url = (part.get("image_url") or {}).get("url", "") if isinstance(part, dict) else ""
                    if url.startswith("data:image"):
                        source = url
                        break
            if source:
                break
        if not source:
            for f in reversed(__files__ or []):
                url = f.get("url", "") if isinstance(f, dict) else ""
                if url.startswith("data:image"):
                    source = url
                    break
        if not source:
            return (
                "No attached image found in this chat. Ask the user to attach "
                "the image they want edited (the + button), then try again."
            )

        if __event_emitter__:
            await __event_emitter__(
                {"type": "status",
                 "data": {"description": "Editing image locally…", "done": False}}
            )
        header, b64_in = source.split(",", 1)
        ext = "png" if "png" in header else "jpeg"
        try:
            r = requests.post(
                "{shim_base}/images/edits",
                files={"image": (f"input.{ext}", __import__("base64").b64decode(b64_in))},
                data={"prompt": prompt, "strength": strength},
                timeout=600,
            )
            r.raise_for_status()
            b64 = r.json()["data"][0]["b64_json"]
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status",
                     "data": {"description": f"Image edit failed: {e}", "done": True}}
                )
            return (
                f"Image editing failed ({e}). Tell the user the image engine "
                "may be off — they can run `smallwonder doctor`."
            )
        if __event_emitter__:
            await __event_emitter__(
                {"type": "message",
                 "data": {"content": f"\\n![edited image](data:image/png;base64,{b64})\\n"}}
            )
            await __event_emitter__(
                {"type": "status", "data": {"description": "Edit ready", "done": True}}
            )
        return (
            "The edited image was created and is already displayed in the "
            "chat. Briefly (one sentence) describe the edit you made. Do NOT "
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
