"""smallwonder CLI — a troupe of small local models that act like one big one."""

from __future__ import annotations

import shutil

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smallwonder import tiers as tiers_mod
from smallwonder.config import Config, ensure_dirs

app = typer.Typer(no_args_is_help=True, add_completion=False)
image_app = typer.Typer(no_args_is_help=True)
news_app = typer.Typer(no_args_is_help=True)
models_app = typer.Typer(no_args_is_help=True)
app.add_typer(image_app, name="image", help="Image generation module (Draw Things)")
app.add_typer(news_app, name="news", help="Daily news brief module")
app.add_typer(models_app, name="models", help="Manage models behind the roles")

console = Console()


TUTORIAL = """\
[bold]Endpoints[/bold]
  Chat UI     http://localhost:{ui}
  API         http://localhost:{router}/v1   (key: {key})
  Models      coder | general | fast | auto | local-embed{image_line}
              or any downloaded model as local/<id>

[bold]Tips[/bold]
  • add "reasoning_effort": "none" to a request for instant (less careful) answers
  • first request after switching models loads it (~5-20s), then it's warm
  • smallwonder status / doctor / evals when things look off"""


def _tutorial(cfg: Config) -> str:
    return TUTORIAL.format(
        ui=cfg.ports["ui"],
        router=cfg.ports["router"],
        key=cfg.api_key,
        image_line=" | image" if cfg.modules.get("image") else "",
    )


@app.command()
def setup(
    tier: str = typer.Option(None, help="16gb | 32gb | 48gb (default: auto-detect)"),
    backend: str = typer.Option("lmstudio", help="lmstudio (MLX, default) | llamaswap (fully OSS)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept all defaults, no prompts"),
):
    """Install and configure the full stack (idempotent — rerun anytime)."""
    from smallwonder import preflight
    from smallwonder.backends.base import get_backend
    from smallwonder.services import stack

    ensure_dirs()
    failures = preflight.check(Config.load_or_default().ports)
    if failures:
        console.print("[red bold]This system can't run smallwonder:[/red bold]")
        for f in failures:
            console.print(f"  ❌ {f.what}: {f.detail}\n     [yellow]{f.remedy}[/yellow]")
        raise typer.Exit(2)

    ram = tiers_mod.machine_ram_gb()
    chosen_tier = tier or tiers_mod.pick_tier(ram)
    disk = tiers_mod.tier_disk_gb(chosen_tier)

    console.print(
        Panel(
            f"Machine: {ram}GB RAM → tier [bold]{chosen_tier}[/bold]\n"
            f"Backend: [bold]{backend}[/bold]"
            + (" (MLX via LM Studio — freeware runtime)\n" if backend == "lmstudio"
               else " (llama.cpp + llama-swap — fully open source)\n")
            + 
            f"Models to download: ~{disk}GB disk",
            title="smallwonder setup",
        )
    )
    if not yes and not typer.confirm("Proceed?", default=True):
        raise typer.Abort()

    free_gb = shutil.disk_usage("/").free / 1e9
    if free_gb < disk + 20:
        console.print(f"[red]Only {free_gb:.0f}GB free; need ~{disk + 20:.0f}GB.[/red]")
        raise typer.Exit(1)

    cfg = Config.load_or_default()
    cfg.tier, cfg.backend = chosen_tier, backend
    cfg.models = tiers_mod.tier_models(chosen_tier, backend)
    cfg.save()

    be = get_backend(cfg)
    console.print("[bold]1/4[/bold] Installing runtime + python tools…")
    be.install()
    stack.install_python_tools()

    console.print("[bold]2/4[/bold] Downloading models (resumable; rerun setup if interrupted)…")
    for role, ref in cfg.models.items():
        console.print(f"  • {role}: {ref}")
        be.pull(ref)

    console.print("[bold]3/4[/bold] Starting services…")
    stack.up(cfg)
    for svc in ("backend", "router", "ui"):
        ok = stack.wait_healthy(cfg, svc, timeout=180)
        console.print(f"  {'✅' if ok else '❌'} {svc}")
        if not ok:
            console.print(f"[red]{svc} failed to start — see ~/.smallwonder/logs/[/red]")
            raise typer.Exit(1)

    console.print("[bold]4/4[/bold] Smoke test…")
    import httpx

    r = httpx.post(
        f"{cfg.router_base}/v1/chat/completions",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        json={
            "model": "fast",
            "messages": [{"role": "user", "content": "Say 'ready' and nothing else."}],
            "max_tokens": 200,
            "reasoning_effort": "none",
        },
        timeout=300,
    )
    r.raise_for_status()
    console.print(Panel(_tutorial(cfg), title="🎭 smallwonder is up", border_style="green"))


@app.command()
def up():
    """Start all services (and regenerate configs from config.yaml)."""
    from smallwonder.services import stack

    cfg = Config.load()
    stack.up(cfg)
    console.print("services starting — `smallwonder status` to check")


@app.command()
def down():
    """Stop all services and unload launchd agents."""
    from smallwonder.services import stack

    cfg = Config.load()
    stack.down(cfg)
    console.print("stack stopped")


@app.command()
def status():
    """Health of every service + models on disk."""
    from smallwonder.backends.base import get_backend
    from smallwonder.services import stack

    cfg = Config.load()
    t = Table(title=f"smallwonder [{cfg.backend} · {cfg.tier}]")
    t.add_column("service")
    t.add_column("healthy")
    for name, ok in stack.health(cfg).items():
        t.add_row(name, "✅" if ok else "❌")
    console.print(t)
    models = get_backend(cfg).models_on_disk()
    console.print(f"models on disk: {len(models)}")
    for role, ref in cfg.models.items():
        console.print(f"  {role:<8} → {ref}")


@app.command()
def doctor():
    """Diagnose the known failure modes."""
    from smallwonder.services import stack
    from smallwonder.services.stack import UV_TOOL_BIN

    cfg = Config.load_or_default()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("uv installed", bool(shutil.which("uv")), "brew install uv"))
    checks.append(
        ("litellm installed", (UV_TOOL_BIN / "litellm").exists(),
         "uv tool install --with semantic-router 'litellm[proxy]'")
    )
    checks.append(
        ("open-webui installed", (UV_TOOL_BIN / "open-webui").exists(),
         "uv tool install --python 3.12 open-webui")
    )
    h = stack.health(cfg)
    for name, ok in h.items():
        fix = {
            "backend": "smallwonder up (backend runtime not serving)",
            "router": "check ~/.smallwonder/logs/litellm.log",
            "ui": "check ~/.smallwonder/logs/openwebui.log (first boot takes ~2min)",
            "drawthings": "open Draw Things app + enable its API server in Settings",
            "image_shim": "smallwonder up",
        }.get(name, "")
        checks.append((f"service: {name}", ok, fix))

    if cfg.modules.get("image") and h.get("ui"):
        try:
            from smallwonder.openwebui import OpenWebUI

            img = OpenWebUI(cfg).get("/api/v1/images/config").json()
            checks.append(
                ("Open WebUI image gen enabled", bool(img.get("ENABLE_IMAGE_GENERATION")),
                 "smallwonder image enable  (Open WebUI disables it after a failed probe)")
            )
        except Exception:
            checks.append(("Open WebUI image config readable", False, "is the UI up?"))

    failed = 0
    for name, ok, fix in checks:
        suffix = "" if ok else f"  → [yellow]{fix}[/yellow]"
        console.print(f"{'✅' if ok else '❌'} {name}{suffix}")
        failed += 0 if ok else 1
    raise typer.Exit(1 if failed else 0)


@app.command()
def evals():
    """Run the golden-prompt suite against the router."""
    from smallwonder.evals import runner

    cfg = Config.load()
    failures = runner.run(cfg, console)
    console.print(f"\n{'❌' if failures else '✅'} {failures} failures")
    raise typer.Exit(1 if failures else 0)


@app.command()
def tutorial():
    """Print the quick-start card again."""
    console.print(Panel(_tutorial(Config.load()), title="🎭 smallwonder"))


# --- models ------------------------------------------------------------------
@models_app.command("list")
def models_list():
    """Show role → model mapping and what's on disk."""
    status()


@models_app.command("add")
def models_add(
    model_ref: str = typer.Argument(help="Backend model ref (LM Studio hub id or repo:quant)"),
    role: str = typer.Option(None, help="Assign to a role (coder/general/fast) immediately"),
):
    """Download a model; optionally point a role at it."""
    from smallwonder.backends.base import get_backend
    from smallwonder.services import launchd, stack

    cfg = Config.load()
    get_backend(cfg).pull(model_ref)
    console.print(f"downloaded: {model_ref} (usable now as local/{model_ref})")
    if role:
        if role not in ("coder", "general", "fast"):
            console.print("[red]role must be coder|general|fast[/red]")
            raise typer.Exit(1)
        cfg.models[role] = model_ref
        cfg.save()
        stack.render_router_configs(cfg)
        launchd.kickstart("litellm")
        console.print(
            f"role [bold]{role}[/bold] now serves {model_ref} — "
            "run `smallwonder evals` to compare"
        )


# --- image module ------------------------------------------------------------
@image_app.command("enable")
def image_enable():
    """Set up Draw Things + shim + Open WebUI image generation."""
    from smallwonder.modules import image

    cfg = Config.load()
    steps = image.enable(cfg)
    for s in steps:
        console.print(Panel(s, border_style="yellow"))


@image_app.command("disable")
def image_disable():
    from smallwonder.services import launchd, stack

    cfg = Config.load()
    cfg.modules["image"] = False
    cfg.save()
    launchd.uninstall("imageshim")
    stack.render_router_configs(cfg)
    launchd.kickstart("litellm")
    console.print("image module disabled")


# --- news module --------------------------------------------------------------
@news_app.command("enable")
def news_enable(hour: int = typer.Option(6, help="Local hour for the daily fetch")):
    """Enable the daily news brief (RSS → local digest → Open WebUI knowledge)."""
    from smallwonder.modules import news

    cfg = Config.load()
    cfg.modules["news"] = True
    cfg.news["hour"] = hour
    cfg.save()
    news.install_timer(cfg)
    console.print(
        f"news module enabled (daily at {hour:02d}:15). Feeds in ~/.smallwonder/config.yaml.\n"
        "Run once now with: smallwonder news run"
    )


@news_app.command("disable")
def news_disable():
    from smallwonder.services import launchd

    cfg = Config.load()
    cfg.modules["news"] = False
    cfg.save()
    launchd.uninstall("news")
    console.print("news module disabled")


@news_app.command("run")
def news_run():
    """Fetch + digest + store today's brief right now."""
    from smallwonder.modules import news

    news.run()


@app.command()
def uninstall(yes: bool = typer.Option(False, "--yes", "-y")):
    """Stop everything and remove smallwonder state (keeps downloaded models)."""
    import shutil as _sh

    from smallwonder.config import STATE_DIR
    from smallwonder.services import stack

    if not yes and not typer.confirm("Stop services and delete ~/.smallwonder?"):
        raise typer.Abort()
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        stack.down(Config.load())
    _sh.rmtree(STATE_DIR, ignore_errors=True)
    console.print("removed. Model weights (LM Studio / llama.cpp caches) were kept.")


def main():
    app()


if __name__ == "__main__":
    main()
