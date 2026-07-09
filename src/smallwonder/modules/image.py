"""Image generation module: Draw Things (official brew cask) + OpenAI-images shim.

Draw Things' HTTP server implements A1111-style txt2img but not the model
catalog, so we front it with shim/dt_openai_shim.py exposing the standard
OpenAI images contract on its own port. The Draw Things API server and model
selection must be enabled in-app (no headless toggle exists) — setup walks
the user through it.
"""

from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path

from smallwonder.config import RENDER_DIR, Config
from smallwonder.services import launchd
from smallwonder.services.stack import UV_TOOL_BIN

APP_PATH = Path("/Applications/Draw Things.app")

MANUAL_STEPS = """\
In the Draw Things app (launching it now):
  1. Model dropdown → download a model. Recommended, both Apache-2.0:
     • Z-Image Turbo (~4GB) — fast
     • FLUX.2 [klein] 4B (~10GB) — higher quality
  2. Settings → API Server → enable HTTP server on 127.0.0.1:{port}
  3. Keep the app running (menu bar/dock is fine).
The shim uses whichever model is ACTIVE in the app."""


def install_app() -> bool:
    """Install Draw Things via its official cask. Returns True if present."""
    if APP_PATH.exists():
        return True
    if not shutil.which("brew"):
        return False
    r = subprocess.run(["brew", "install", "--cask", "draw-things"])
    return r.returncode == 0 and APP_PATH.exists()


def _shim_source() -> Path:
    """Copy the shim into the render dir so launchd runs a stable path."""
    dest = RENDER_DIR / "dt_openai_shim.py"
    src = resources.files("smallwonder.shim").joinpath("dt_openai_shim.py")
    dest.write_text(src.read_text())
    return dest


def start_shim(cfg: Config) -> None:
    shim_path = _shim_source()
    # run inside the litellm uv tool env (has fastapi/uvicorn/requests)
    litellm_python = UV_TOOL_BIN.parent / "share" / "uv" / "tools" / "litellm" / "bin" / "python"
    python = str(litellm_python) if litellm_python.exists() else "python3"
    launchd.install(
        "imageshim",
        args=[
            python, "-m", "uvicorn",
            "--app-dir", str(shim_path.parent),
            "dt_openai_shim:app",
            "--host", "127.0.0.1",
            "--port", str(cfg.ports["image_shim"]),
        ],
        env={"DRAW_THINGS_URL": f"http://127.0.0.1:{cfg.ports['drawthings']}"},
    )


def enable(cfg: Config) -> list[str]:
    """Full enable flow. Returns manual steps the user still has to do."""
    steps: list[str] = []
    if not install_app():
        steps.append(
            "Install Draw Things manually: brew install --cask draw-things "
            "(or App Store), then re-run `smallwonder image enable`."
        )
        return steps
    subprocess.run(["open", "-a", "Draw Things"], check=False)
    cfg.modules["image"] = True
    cfg.save()
    start_shim(cfg)

    from smallwonder.services import launchd as _l
    from smallwonder.services.stack import render_router_configs

    render_router_configs(cfg)
    _l.kickstart("litellm")

    try:
        from smallwonder import openwebui_tool
        from smallwonder.openwebui import OpenWebUI

        ui = OpenWebUI(cfg)
        shim_base = f"http://127.0.0.1:{cfg.ports['image_shim']}/v1"
        ui.enable_image_generation(shim_base)
        # ChatGPT-style agentic image gen: models call the tool themselves
        openwebui_tool.register(ui, shim_base, ["auto", "general", "fast", "coder"])
        # tool selection/titles on the fast model, or every tool call pays
        # two slow thinking-model passes
        ui.set_task_model("fast")
    except Exception:
        steps.append(
            "Open WebUI image config could not be set automatically "
            "(is Open WebUI running?). Re-run after `smallwonder up`."
        )
    steps.append(MANUAL_STEPS.format(port=cfg.ports["drawthings"]))
    return steps
