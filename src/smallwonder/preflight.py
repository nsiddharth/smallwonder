"""Hard compatibility gates. Refuse cleanly rather than fail halfway through.

Every check here exists because failing it means a broken install, not a
degraded one. Checks that merely reduce functionality belong in `doctor`.
"""

from __future__ import annotations

import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass


@dataclass
class Failure:
    what: str
    detail: str
    remedy: str


def _macos_major() -> int:
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return 0


def _is_apple_silicon() -> bool:
    """True on Apple Silicon hardware, even when Python runs under Rosetta
    (platform.machine() lies there — it reports the process arch, x86_64)."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True
        ).stdout.strip()
        return out == "1"
    except OSError:
        return platform.machine() == "arm64"


def _port_free_or_ours(port: int) -> tuple[bool, str]:
    """True if nothing listens on the port, or the listener is one of ours."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return True, ""
    r = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fc"],
        capture_output=True,
        text=True,
    )
    procs = {line[1:] for line in r.stdout.splitlines() if line.startswith("c")}
    OURS = {"llmster", "llama-swap", "llama-serve", "Python", "python3.12", "uvicorn", "DrawThing"}
    if procs and not procs & OURS:
        return False, ", ".join(sorted(procs))
    return True, ""


def check(ports: dict, min_ram_gb: int = 16) -> list[Failure]:
    failures: list[Failure] = []

    if platform.system() != "Darwin":
        failures.append(
            Failure("Operating system", f"{platform.system()} detected",
                    "smallwonder only supports macOS.")
        )
        return failures  # nothing else is meaningful

    if not _is_apple_silicon():
        failures.append(
            Failure("CPU", "Intel Mac detected",
                    "smallwonder requires Apple Silicon (M1 or newer) — "
                    "local models need the unified-memory GPU.")
        )

    if _macos_major() < 14:
        failures.append(
            Failure("macOS version", f"{platform.mac_ver()[0]} detected",
                    "macOS 14 (Sonoma) or newer is required.")
        )

    ram = 0
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, check=True).stdout
        ram = int(out) // (1024**3)
    except (subprocess.CalledProcessError, ValueError):
        pass
    if ram < min_ram_gb:
        failures.append(
            Failure("Memory", f"{ram}GB RAM detected",
                    f"At least {min_ram_gb}GB unified memory is required to run "
                    "useful local models.")
        )

    if not shutil.which("uv"):
        failures.append(
            Failure("uv", "not found on PATH",
                    "Install with: brew install uv  "
                    "(https://docs.astral.sh/uv)")
        )

    for name in ("backend", "router", "ui"):
        port = ports[name]
        ok, holder = _port_free_or_ours(port)
        if not ok:
            failures.append(
                Failure(f"Port {port}", f"in use by: {holder}",
                        f"Stop that process or change ports.{name} in "
                        "~/.smallwonder/config.yaml.")
            )

    return failures
