"""Orchestrate the full stack: backend + LiteLLM router + Open WebUI (+ modules)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
from jinja2 import Environment, PackageLoader

from smallwonder.backends.base import get_backend
from smallwonder.config import OPENWEBUI_DATA, RENDER_DIR, Config, ensure_dirs

_env = Environment(loader=PackageLoader("smallwonder", "templates"), keep_trailing_newline=True)

UV_TOOL_BIN = Path.home() / ".local" / "bin"


def uv_bin(name: str) -> str:
    p = UV_TOOL_BIN / name
    return str(p) if p.exists() else name


def install_python_tools() -> None:
    """Install LiteLLM (with semantic-router for the auto-router) and Open WebUI."""
    if not shutil.which("uv"):
        raise RuntimeError(
            "smallwonder needs `uv` (https://docs.astral.sh/uv). "
            "Install with: brew install uv"
        )
    # Versions pinned to the combination verified end-to-end (see CONTRIBUTING
    # for the bump procedure). Isolated uv tool envs — no interference with
    # anything else on the machine.
    subprocess.run(
        ["uv", "tool", "install", "--python", "3.12",
         "--with", "semantic-router==0.1.15", "litellm[proxy]==1.91.0"],
        check=True,
    )
    subprocess.run(
        # numpy<2: Open WebUI's torch wheel breaks against numpy 2.x
        # ("Numpy is not available" on any RAG/knowledge operation)
        ["uv", "tool", "install", "--python", "3.12", "--with", "numpy<2",
         "open-webui==0.6.41"],
        check=True,
    )


def render_router_configs(cfg: Config) -> Path:
    ensure_dirs()
    ctx = {
        "models": cfg.models,
        "backend_base": cfg.backend_base,
        "ports": cfg.ports,
        "api_key": cfg.api_key,
        "render_dir": str(RENDER_DIR),
        "image_enabled": cfg.modules.get("image", False),
    }
    (RENDER_DIR / "litellm.yaml").write_text(
        _env.get_template("litellm.yaml.j2").render(**ctx)
    )
    (RENDER_DIR / "auto_router.json").write_text(
        _env.get_template("auto_router.json.j2").render(**ctx)
    )
    return RENDER_DIR / "litellm.yaml"


def up(cfg: Config) -> None:
    from smallwonder.services import launchd

    ensure_dirs()
    backend = get_backend(cfg)
    backend.start()

    litellm_cfg = render_router_configs(cfg)
    launchd.install(
        "litellm",
        args=[uv_bin("litellm"), "--config", str(litellm_cfg),
              "--port", str(cfg.ports["router"]), "--host", "127.0.0.1"],
        env={
            "OPENAI_API_BASE": f"{cfg.backend_base}/v1",
            "OPENAI_API_KEY": "local-backend",
        },
    )
    launchd.install(
        "openwebui",
        args=[uv_bin("open-webui"), "serve", "--host", "127.0.0.1",
              "--port", str(cfg.ports["ui"])],
        working_dir=str(OPENWEBUI_DATA),
        env={
            "DATA_DIR": str(OPENWEBUI_DATA),
            "OPENAI_API_BASE_URL": f"{cfg.router_base}/v1",
            "OPENAI_API_KEY": cfg.api_key,
            "ENABLE_OLLAMA_API": "false",
            "WEBUI_AUTH": "false",
        },
    )
    if cfg.modules.get("image"):
        from smallwonder.modules.image import start_shim

        start_shim(cfg)
    if cfg.modules.get("news"):
        from smallwonder.modules.news import install_timer

        install_timer(cfg)
    if cfg.modules.get("voice"):
        from smallwonder.modules import voice

        voice.start(cfg)


def down(cfg: Config) -> None:
    from smallwonder.services import launchd

    for name in ("news", "tts", "imageshim", "openwebui", "litellm", "llamaswap"):
        launchd.uninstall(name)
    get_backend(cfg).stop()


HEALTH_CHECKS = [
    ("backend", "{backend}/v1/models"),
    ("router", "{router}/health/liveliness"),
    ("ui", "{ui}/health"),
]


def health(cfg: Config) -> dict[str, bool]:
    urls = {
        "backend": cfg.backend_base,
        "router": cfg.router_base,
        "ui": cfg.ui_base,
    }
    out: dict[str, bool] = {}
    for name, tmpl in HEALTH_CHECKS:
        url = tmpl.format(**urls)
        try:
            out[name] = httpx.get(url, timeout=5).status_code == 200
        except httpx.HTTPError:
            out[name] = False
    extra = []
    if cfg.modules.get("image"):
        extra += [
            ("drawthings", f"http://127.0.0.1:{cfg.ports['drawthings']}/"),
            ("image_shim", f"http://127.0.0.1:{cfg.ports['image_shim']}/health"),
        ]
    if cfg.modules.get("voice"):
        extra.append(("tts", f"http://127.0.0.1:{cfg.ports['tts']}/v1/models"))
    if extra:
        for name, url in extra:
            try:
                out[name] = httpx.get(url, timeout=5).status_code == 200
            except httpx.HTTPError:
                out[name] = False
    return out


def wait_healthy(cfg: Config, service: str, timeout: int = 120) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if health(cfg).get(service):
            return True
        time.sleep(2)
    return False
