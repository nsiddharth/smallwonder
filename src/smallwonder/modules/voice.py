"""Voice output module: local TTS via mlx-audio (MIT, MLX-native).

Serves an OpenAI-compatible /v1/audio/speech on the tts port and wires Open
WebUI's TTS engine to it — read-aloud on any reply plus hands-free Call mode
(STT stays on Open WebUI's built-in local Whisper). Fully offline after the
one-time model download (~350MB Kokoro).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import httpx

from smallwonder.config import STATE_DIR, Config
from smallwonder.services import launchd
from smallwonder.services.stack import UV_TOOL_BIN

TTS_MODEL = "mlx-community/Kokoro-82M-bf16"  # Apache 2.0 weights, 54 voices
TTS_VOICE = "af_heart"

TOOL_PYTHON = UV_TOOL_BIN.parent / "share" / "uv" / "tools" / "mlx-audio" / "bin" / "python"


def is_installed() -> bool:
    return TOOL_PYTHON.exists()


def install() -> None:
    if is_installed():
        return
    if not shutil.which("uv"):
        raise RuntimeError("uv is required: brew install uv")
    subprocess.run(
        # arch-pinned python: an Intel-prefix (Rosetta) uv resolves x86_64
        # wheels and mlx has none — explicit aarch64 sidesteps it
        ["uv", "tool", "install", "--python", "cpython-3.12-macos-aarch64",
         "--prerelease=allow", "--with", "misaki[en]",   # Kokoro text frontend
         "mlx-audio[server]"],
        check=True,
    )


def tts_base(cfg: Config) -> str:
    return f"http://127.0.0.1:{cfg.ports['tts']}/v1"


def start(cfg: Config) -> None:
    launchd.install(
        "tts",
        args=[str(TOOL_PYTHON), "-m", "mlx_audio.server",
              "--host", "127.0.0.1", "--port", str(cfg.ports["tts"])],
        # the server mkdirs a relative ./logs — launchd default cwd is /
        working_dir=str(STATE_DIR),
    )


def stop() -> None:
    launchd.uninstall("tts")


def wait_healthy(cfg: Config, timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{tts_base(cfg)}/models", timeout=3).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2)
    return False


def prewarm(cfg: Config) -> Path | None:
    """First request downloads Kokoro (~350MB) and loads it; do that now so
    the first chat reply isn't the one that pays. Returns the sample file."""
    r = httpx.post(
        f"{tts_base(cfg)}/audio/speech",
        json={"model": TTS_MODEL, "input": "smallwonder voice is ready.",
              "voice": TTS_VOICE, "response_format": "wav"},
        timeout=600,
    )
    r.raise_for_status()
    sample = Path.home() / ".smallwonder" / "voice-sample.wav"
    sample.write_bytes(r.content)
    return sample


def enable(cfg: Config) -> list[str]:
    """Full enable flow. Returns any manual follow-ups."""
    steps: list[str] = []
    install()
    cfg.modules["voice"] = True
    cfg.save()
    start(cfg)
    if not wait_healthy(cfg):
        steps.append("TTS server did not come up — check ~/.smallwonder/logs/tts.log")
        return steps
    prewarm(cfg)
    try:
        from smallwonder.openwebui import OpenWebUI

        OpenWebUI(cfg).enable_tts(tts_base(cfg), model=TTS_MODEL, voice=TTS_VOICE)
    except Exception:
        steps.append(
            "Open WebUI audio config could not be set automatically "
            "(is Open WebUI running?). Re-run after `smallwonder up`."
        )
    return steps
