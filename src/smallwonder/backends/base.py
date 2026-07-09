"""Backend interface: something that serves OpenAI-compatible models locally."""

from __future__ import annotations

from abc import ABC, abstractmethod

from smallwonder.config import Config


class Backend(ABC):
    name: str

    def __init__(self, cfg: Config):
        self.cfg = cfg

    @abstractmethod
    def install(self) -> None:
        """Install the runtime itself (idempotent)."""

    @abstractmethod
    def pull(self, model_ref: str) -> None:
        """Download a model (idempotent; shows progress on stdout)."""

    @abstractmethod
    def start(self) -> None:
        """Start serving on cfg.ports['backend'] (idempotent)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop serving (best-effort)."""

    @abstractmethod
    def models_on_disk(self) -> list[str]:
        """Model refs currently downloaded."""

    @abstractmethod
    def is_installed(self) -> bool: ...


def get_backend(cfg: Config) -> Backend:
    from smallwonder.backends.llamaswap import LlamaSwapBackend
    from smallwonder.backends.lmstudio import LMStudioBackend

    return {"lmstudio": LMStudioBackend, "llamaswap": LlamaSwapBackend}[cfg.backend](cfg)
