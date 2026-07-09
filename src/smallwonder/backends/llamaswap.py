"""Fully-open-source backend: llama-swap (MIT) fronting llama-server (MIT).

GGUF/Metal. Models are referenced as `-hf repo:quant` and cached by llama.cpp
under ~/Library/Caches/llama.cpp on first load; setup pre-warms each model so
the download cost is paid up front, not on first chat.
"""

from __future__ import annotations

import shutil
import subprocess

from jinja2 import Environment, PackageLoader

from smallwonder.backends.base import Backend
from smallwonder.config import RENDER_DIR
from smallwonder.services import launchd

_env = Environment(loader=PackageLoader("smallwonder", "templates"), keep_trailing_newline=True)


def _which(binary: str) -> str | None:
    return shutil.which(binary)


class LlamaSwapBackend(Backend):
    name = "llamaswap"

    def is_installed(self) -> bool:
        return bool(_which("llama-swap") and _which("llama-server"))

    def install(self) -> None:
        formulas = {
            "llama-server": "llama.cpp",
            "llama-swap": "mostlygeek/llama-swap/llama-swap",
        }
        missing = [formulas[b] for b in formulas if not _which(b)]
        if missing:
            subprocess.run(["brew", "install", *missing], check=True)

    def render_config(self) -> str:
        cfg_path = RENDER_DIR / "llama-swap.yaml"
        rendered = _env.get_template("llama-swap.yaml.j2").render(
            ports=self.cfg.ports,
            models=self.cfg.models,
            llama_server_bin=_which("llama-server") or "llama-server",
            context_tokens=getattr(self.cfg, "context_tokens", 65536),
        )
        cfg_path.write_text(rendered)
        return str(cfg_path)

    def pull(self, model_ref: str) -> None:
        # llama.cpp downloads -hf refs into its cache; --no-warmup + immediate
        # exit via /dev/null prompt isn't supported, so use llama-server's
        # sibling CLI to fetch: running with -no-cnv --n-predict 0 downloads
        # then exits.
        subprocess.run(
            [
                _which("llama-cli") or "llama-cli",
                "-hf", model_ref,
                "--n-predict", "0",
                "-no-cnv",
                "--no-warmup",
            ],
            check=True,
        )

    def start(self) -> None:
        config_path = self.render_config()
        launchd.install(
            "llamaswap",
            args=[_which("llama-swap") or "llama-swap", "--config", config_path],
            keep_alive=True,
        )

    def stop(self) -> None:
        launchd.uninstall("llamaswap")

    def models_on_disk(self) -> list[str]:
        # llama.cpp cache holds downloaded GGUFs; presence check is best-effort
        from pathlib import Path

        cache = Path.home() / "Library" / "Caches" / "llama.cpp"
        if not cache.exists():
            return []
        return [p.name for p in cache.glob("*.gguf")]
