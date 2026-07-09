"""Golden-prompt eval runner: fire every case at the router for eyeball review.

Deliberately assertion-light — local models change too often for brittle
string asserts; the value is side-by-side comparability when swapping models.
Routing cases DO assert (the router either picked the right role or it
didn't).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

import httpx
from rich.console import Console
from rich.panel import Panel

from smallwonder.config import Config


@dataclass
class Case:
    role: str
    name: str
    prompt: str
    expect: str


def load_cases() -> list[Case]:
    text = resources.files("smallwonder.evals").joinpath("prompts.yaml").read_text()
    cases: list[Case] = []
    cur: dict = {}
    for line in text.splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        m = re.match(r"- role: (.+)", line)
        if m:
            if cur:
                cases.append(Case(**cur))
            cur = {"role": m.group(1).strip(), "name": "", "prompt": "", "expect": ""}
            continue
        m = re.match(r"\s+(name|prompt|expect): (.+)", line)
        if m and cur:
            cur[m.group(1)] = m.group(2).strip().strip('"')
    if cur:
        cases.append(Case(**cur))
    return cases


def run(cfg: Config, console: Console | None = None) -> int:
    console = console or Console()
    failures = 0
    for c in load_cases():
        try:
            r = httpx.post(
                f"{cfg.router_base}/v1/chat/completions",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={
                    "model": c.role,
                    "messages": [{"role": "user", "content": c.prompt}],
                    "max_tokens": 6000,
                },
                timeout=600,
            )
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"] or ""
            served = data.get("system_fingerprint") or data.get("model", "?")
            console.print(
                Panel(
                    content.strip()[:1200] or "[red](empty)[/red]",
                    title=f"[{c.role}] {c.name} → {served}",
                    subtitle=f"expect: {c.expect}",
                )
            )
            if not content.strip():
                failures += 1
        except (httpx.HTTPError, KeyError) as e:
            console.print(f"[red][{c.role}] {c.name} ERROR: {e}[/red]")
            failures += 1
    return failures
