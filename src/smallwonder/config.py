"""User configuration and paths. State lives under ~/.smallwonder/."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STATE_DIR = Path.home() / ".smallwonder"
CONFIG_PATH = STATE_DIR / "config.yaml"
LOG_DIR = STATE_DIR / "logs"
RENDER_DIR = STATE_DIR / "rendered"
OPENWEBUI_DATA = STATE_DIR / "openwebui"

LAUNCHD_PREFIX = "ai.smallwonder"

DEFAULT_FEEDS = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://hnrss.org/frontpage?points=100",
    "https://feeds.arstechnica.com/arstechnica/index",
]


@dataclass
class Config:
    backend: str = "lmstudio"  # lmstudio | llamaswap
    tier: str = "48gb"
    api_key: str = field(default_factory=lambda: f"sk-smallwonder-{secrets.token_hex(8)}")
    ports: dict = field(
        default_factory=lambda: {
            "backend": 1234,
            "router": 4000,
            "ui": 8080,
            "image_shim": 7861,
            "drawthings": 7860,
        }
    )
    # role -> model spec name; resolved from tier at setup, editable afterwards
    models: dict = field(default_factory=dict)
    modules: dict = field(default_factory=lambda: {"image": False, "news": False})
    news: dict = field(default_factory=lambda: {"feeds": list(DEFAULT_FEEDS), "hour": 6})

    @classmethod
    def load(cls) -> Config:
        if not CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"No config at {CONFIG_PATH}. Run `smallwonder setup` first."
            )
        data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    @classmethod
    def load_or_default(cls) -> Config:
        try:
            return cls.load()
        except FileNotFoundError:
            return cls()

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(yaml.safe_dump(self.__dict__, sort_keys=False))

    @property
    def router_base(self) -> str:
        return f"http://127.0.0.1:{self.ports['router']}"

    @property
    def backend_base(self) -> str:
        return f"http://127.0.0.1:{self.ports['backend']}"

    @property
    def ui_base(self) -> str:
        return f"http://127.0.0.1:{self.ports['ui']}"


def ensure_dirs() -> None:
    for d in (STATE_DIR, LOG_DIR, RENDER_DIR, OPENWEBUI_DATA):
        d.mkdir(parents=True, exist_ok=True)
