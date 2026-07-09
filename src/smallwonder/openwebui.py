"""Minimal Open WebUI API client (single-user mode, WEBUI_AUTH=false)."""

from __future__ import annotations

import httpx

from smallwonder.config import Config


class OpenWebUI:
    def __init__(self, cfg: Config):
        self.base = cfg.ui_base
        self._token: str | None = None

    @property
    def token(self) -> str:
        if self._token is None:
            r = httpx.post(
                f"{self.base}/api/v1/auths/signin",
                json={"email": "", "password": ""},
                timeout=15,
            )
            r.raise_for_status()
            self._token = r.json()["token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str, **kw) -> httpx.Response:
        return httpx.get(f"{self.base}{path}", headers=self._headers(), timeout=30, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        timeout = kw.pop("timeout", 120)
        return httpx.post(
            f"{self.base}{path}", headers=self._headers(), timeout=timeout, **kw
        )

    # --- image config ------------------------------------------------------
    def enable_image_generation(self, shim_base: str) -> None:
        """Point Open WebUI's image engine at the OpenAI-images shim."""
        current = self.get("/api/v1/images/config").json()
        current.update(
            ENABLE_IMAGE_GENERATION=True,
            IMAGE_GENERATION_ENGINE="openai",
            IMAGE_GENERATION_MODEL="draw-things",
            IMAGE_SIZE="1024x1024",
            IMAGE_STEPS=8,
            IMAGES_OPENAI_API_BASE_URL=shim_base,
            IMAGES_OPENAI_API_KEY="none",
        )
        r = self.post("/api/v1/images/config/update", json=current)
        r.raise_for_status()

    # --- knowledge (RAG collections) ----------------------------------------
    def find_or_create_knowledge(self, name: str, description: str) -> str:
        r = self.get("/api/v1/knowledge/list")
        r.raise_for_status()
        for item in r.json():
            if item.get("name") == name:
                return item["id"]
        r = self.post(
            "/api/v1/knowledge/create",
            json={"name": name, "description": description},
        )
        r.raise_for_status()
        return r.json()["id"]

    def upload_text(self, filename: str, text: str) -> str:
        r = self.post(
            "/api/v1/files/",
            files={"file": (filename, text.encode(), "text/markdown")},
        )
        r.raise_for_status()
        return r.json()["id"]

    def add_file_to_knowledge(self, knowledge_id: str, file_id: str) -> None:
        r = self.post(
            f"/api/v1/knowledge/{knowledge_id}/file/add", json={"file_id": file_id}
        )
        r.raise_for_status()

    def knowledge_files(self, knowledge_id: str) -> list[dict]:
        r = self.get(f"/api/v1/knowledge/{knowledge_id}")
        r.raise_for_status()
        return r.json().get("files", [])

    def remove_file_from_knowledge(self, knowledge_id: str, file_id: str) -> None:
        self.post(
            f"/api/v1/knowledge/{knowledge_id}/file/remove", json={"file_id": file_id}
        )
