"""LM Studio (llmster headless) backend — the default; MLX, best Apple Silicon perf.

Installs via LM Studio's OFFICIAL install script (we never redistribute their
binaries; their ToS permits use, prohibits redistribution). The `lms` CLI it
installs is MIT-licensed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from smallwonder.backends.base import Backend

LMS = Path.home() / ".lmstudio" / "bin" / "lms"
INSTALL_CMD = "curl -fsSL https://lmstudio.ai/install.sh | sh"


class LMStudioBackend(Backend):
    name = "lmstudio"

    def is_installed(self) -> bool:
        return LMS.exists()

    def install(self) -> None:
        if self.is_installed():
            return
        subprocess.run(INSTALL_CMD, shell=True, check=True)

    def _lms(self, *args: str, check: bool = True, quiet: bool = False):
        return subprocess.run(
            [str(LMS), *args],
            check=check,
            capture_output=quiet,
            text=True,
        )

    def pull(self, model_ref: str) -> None:
        if model_ref in self.models_on_disk():
            return
        self._lms("get", model_ref, "--mlx", "-y")

    def _ensure_default_context(self, tokens: int = 32768) -> None:
        """Raise LM Studio's JIT default context (ships at 8192, which vision
        prompts overflow — images can't be truncated, so requests hard-fail
        with a context-overflow policy error)."""
        import json

        path = Path.home() / ".lmstudio" / "settings.json"
        try:
            settings = json.loads(path.read_text()) if path.exists() else {}
        except json.JSONDecodeError:
            return
        current = (settings.get("defaultContextLength") or {}).get("value", 0)
        if current >= tokens:
            return
        settings["defaultContextLength"] = {"type": "custom", "value": tokens}
        path.write_text(json.dumps(settings, indent=2))
        # daemon rereads settings lazily; bounce it so JIT loads pick this up
        self._lms("daemon", "stop", quiet=True, check=False)

    def start(self) -> None:
        self._ensure_default_context()
        self._lms("daemon", "up", quiet=True, check=False)
        self._lms("server", "start", "--port", str(self.cfg.ports["backend"]), quiet=True)

    def stop(self) -> None:
        self._lms("server", "stop", quiet=True, check=False)

    def models_on_disk(self) -> list[str]:
        r = self._lms("ls", "--json", quiet=True, check=False)
        if r.returncode != 0:
            return []
        import json

        try:
            return [m.get("modelKey", m.get("path", "")) for m in json.loads(r.stdout)]
        except (json.JSONDecodeError, TypeError):
            return []
