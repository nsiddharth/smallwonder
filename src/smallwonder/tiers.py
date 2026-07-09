"""RAM-tier model presets. THE place to update as the model landscape evolves.

Each role maps to a spec with per-backend references:
- `lmstudio`: LM Studio hub id (resolves to MLX 4-bit on Apple Silicon)
- `gguf`: llama-server -hf reference (repo:quant) for the fully-OSS backend
- `ram_gb`: approximate resident size, used for sanity math in setup

Last verified against live benchmarks: 2026-07 (Mac Mini M4 Pro 48GB).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    lmstudio: str
    gguf: str
    ram_gb: float


# fmt: off
TIERS: dict[str, dict[str, ModelSpec]] = {
    "16gb": {
        "coder":   ModelSpec("qwen/qwen3.5-9b",       "unsloth/Qwen3.5-9B-GGUF:Q4_K_M", 6.0),
        "general": ModelSpec("qwen/qwen3.5-9b",       "unsloth/Qwen3.5-9B-GGUF:Q4_K_M", 6.0),
        "fast":    ModelSpec("qwen/qwen3.5-2b",       "unsloth/Qwen3.5-2B-GGUF:Q4_K_M", 1.8),
    },
    "32gb": {
        "coder":   ModelSpec("qwen/qwen3-coder-30b",  "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M", 18.6),
        "general": ModelSpec("google/gemma-4-26b-a4b", "unsloth/Gemma-4-26B-A4B-GGUF:Q4_K_M", 15.0),
        "fast":    ModelSpec("qwen/qwen3.5-4b",       "unsloth/Qwen3.5-4B-GGUF:Q4_K_M", 3.1),
    },
    "48gb": {
        "coder":   ModelSpec("qwen/qwen3.6-27b",      "unsloth/Qwen3.6-27B-GGUF:Q4_K_M", 16.1),
        "general": ModelSpec("qwen/qwen3.6-35b-a3b",  "unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M", 20.5),
        "fast":    ModelSpec("qwen/qwen3.5-4b",       "unsloth/Qwen3.5-4B-GGUF:Q4_K_M", 3.1),
    },
}
# fmt: on

EMBED = ModelSpec(
    "text-embedding-nomic-embed-text-v1.5",
    "nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0",
    0.1,
)


def machine_ram_gb() -> int:
    out = subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return int(out) // (1024**3)


def pick_tier(ram_gb: int | None = None) -> str:
    ram = ram_gb if ram_gb is not None else machine_ram_gb()
    if ram >= 40:
        return "48gb"
    if ram >= 24:
        return "32gb"
    return "16gb"


def tier_models(tier: str, backend: str) -> dict[str, str]:
    """Resolve a tier to {role: backend-specific model reference}."""
    specs = TIERS[tier]
    key = "lmstudio" if backend == "lmstudio" else "gguf"
    resolved = {role: getattr(spec, key) for role, spec in specs.items()}
    resolved["embed"] = getattr(EMBED, key)
    return resolved


def tier_disk_gb(tier: str) -> float:
    return round(sum(s.ram_gb for s in TIERS[tier].values()) + EMBED.ram_gb, 1)
