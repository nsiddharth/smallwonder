"""Render and manage launchd agents (labels: ai.smallwonder.*)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from jinja2 import Environment, PackageLoader

from smallwonder.config import LAUNCHD_PREFIX, LOG_DIR

AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"

_env = Environment(loader=PackageLoader("smallwonder", "templates"), keep_trailing_newline=True)


def _uid() -> int:
    return os.getuid()


def label(name: str) -> str:
    return f"{LAUNCHD_PREFIX}.{name}"


def plist_path(name: str) -> Path:
    return AGENTS_DIR / f"{label(name)}.plist"


def install(
    name: str,
    args: list[str],
    env: dict | None = None,
    keep_alive: bool = True,
    working_dir: str | None = None,
    calendar: dict | None = None,
) -> None:
    """Write the agent plist and (re)load it."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rendered = _env.get_template("launchd.plist.j2").render(
        label=label(name),
        args=args,
        env=env,
        keep_alive=keep_alive,
        working_dir=working_dir,
        calendar=calendar,
        log_path=str(LOG_DIR / f"{name}.log"),
    )
    path = plist_path(name)
    uninstall(name)  # bootout stale instance before overwriting
    path.write_text(rendered)
    # bootout is asynchronous: an immediate bootstrap can fail with EIO (5)
    # while the old instance is still terminating. Retry briefly.
    import time

    last = None
    for _ in range(10):
        last = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{_uid()}", str(path)],
            capture_output=True,
        )
        if last.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError(
        f"launchctl bootstrap {label(name)} failed after retries: "
        f"{(last.stderr or b'').decode().strip()}"
    )


def uninstall(name: str) -> None:
    subprocess.run(
        ["launchctl", "bootout", f"gui/{_uid()}/{label(name)}"],
        capture_output=True,
    )
    plist_path(name).unlink(missing_ok=True)


def is_loaded(name: str) -> bool:
    r = subprocess.run(
        ["launchctl", "print", f"gui/{_uid()}/{label(name)}"], capture_output=True
    )
    return r.returncode == 0


def kickstart(name: str) -> None:
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{_uid()}/{label(name)}"],
        capture_output=True,
    )
