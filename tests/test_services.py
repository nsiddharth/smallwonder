"""Regression tests for launchd, LM Studio backend, and Open WebUI client."""

import json
import subprocess
from types import SimpleNamespace

from smallwonder.config import Config


# --- issue: launchctl bootstrap EIO race after bootout ------------------------
def test_launchd_install_retries_bootstrap(monkeypatch, tmp_path):
    from smallwonder.services import launchd

    monkeypatch.setattr(launchd, "AGENTS_DIR", tmp_path)
    monkeypatch.setattr(launchd, "LOG_DIR", tmp_path)
    monkeypatch.setattr(launchd, "uninstall", lambda name: None)

    calls = {"n": 0}

    def fake_run(cmd, capture_output=True, **kw):
        if cmd[1] == "bootstrap":
            calls["n"] += 1
            rc = 5 if calls["n"] < 3 else 0  # EIO twice, then success
            return SimpleNamespace(returncode=rc, stderr=b"EIO")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(launchd.subprocess, "run", fake_run)
    monkeypatch.setattr(launchd.time, "sleep", lambda s: None) if hasattr(launchd, "time") else None
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)

    launchd.install("t", args=["/bin/echo"])
    assert calls["n"] == 3  # retried until success


# --- issue: vision prompts overflow the 8192 JIT default context --------------
def test_lmstudio_raises_default_context(monkeypatch, tmp_path):
    from smallwonder.backends import lmstudio

    settings = tmp_path / ".lmstudio" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"defaultContextLength": {"type": "custom", "value": 8192}}))
    monkeypatch.setattr(lmstudio.Path, "home", classmethod(lambda cls: tmp_path))

    be = lmstudio.LMStudioBackend(Config(context_tokens=65536))
    stopped = []
    monkeypatch.setattr(be, "_lms", lambda *a, **k: stopped.append(a))
    be._ensure_default_context()

    saved = json.loads(settings.read_text())
    assert saved["defaultContextLength"]["value"] == 65536
    assert stopped[0][:2] == ("daemon", "stop")  # daemon bounced to apply


# --- issue: stale small-context instances break image prompts -----------------
def test_lmstudio_start_evicts_stale_instances(monkeypatch, tmp_path):
    from smallwonder.backends import lmstudio

    monkeypatch.setattr(lmstudio.Path, "home", classmethod(lambda cls: tmp_path))
    be = lmstudio.LMStudioBackend(Config(context_tokens=65536))

    unloaded = []

    def fake_lms(*args, **kw):
        if args[0] == "unload":
            unloaded.append(args[1])
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(be, "_lms", fake_lms)
    monkeypatch.setattr(
        be, "loaded_models",
        lambda: [{"identifier": "small", "contextLength": 8192},
                 {"identifier": "big", "contextLength": 65536}],
    )
    be.start()
    assert unloaded == ["small"]


# --- issue: knowledge list API is paginated ({items}), not a bare list --------
def test_knowledge_handles_paginated_and_list_shapes(monkeypatch):
    from smallwonder.openwebui import OpenWebUI

    ui = OpenWebUI.__new__(OpenWebUI)
    for shape in ({"items": [{"name": "Daily News", "id": "k1"}], "total": 1},
                  [{"name": "Daily News", "id": "k1"}]):
        monkeypatch.setattr(
            ui, "get",
            lambda path, _s=shape, **kw: SimpleNamespace(
                status_code=200, json=lambda: _s, raise_for_status=lambda: None
            ),
        )
        assert ui.find_or_create_knowledge("Daily News", "d") == "k1"


# --- issue: task-model on the thinking 35B added minutes per tool call --------
def test_set_task_model_sets_both_keys(monkeypatch):
    from smallwonder.openwebui import OpenWebUI

    ui = OpenWebUI.__new__(OpenWebUI)
    posted = {}
    monkeypatch.setattr(
        ui, "get",
        lambda path, **kw: SimpleNamespace(
            json=lambda: {"TASK_MODEL": "", "TASK_MODEL_EXTERNAL": "", "OTHER": 1}
        ),
    )
    monkeypatch.setattr(
        ui, "post",
        lambda path, json=None, **kw: (posted.update(json),
                                       SimpleNamespace(raise_for_status=lambda: None))[1],
    )
    ui.set_task_model("fast")
    assert posted["TASK_MODEL"] == "fast"
    assert posted["TASK_MODEL_EXTERNAL"] == "fast"
    assert posted["OTHER"] == 1  # other config keys preserved


# --- issue: numpy 2.x broke Open WebUI RAG; unpinned installs drift ------------
def test_python_tools_installed_pinned_and_isolated(monkeypatch):
    from smallwonder.services import stack

    cmds = []
    monkeypatch.setattr(stack.shutil, "which", lambda b: "/usr/local/bin/uv")
    monkeypatch.setattr(
        stack.subprocess, "run",
        lambda cmd, check=True: cmds.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    stack.install_python_tools()
    joined = [" ".join(c) for c in cmds]
    assert any("numpy<2" in c for c in joined)
    assert all("==" in c for c in joined)  # every tool version-pinned
    assert all(c.startswith("uv tool install") for c in joined)


# --- issue #2: requests racing TTL eviction must be retried by the router -----
def test_litellm_template_has_retries():
    import yaml
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("smallwonder", "templates"),
                      keep_trailing_newline=True)
    cfg = Config()
    out = yaml.safe_load(env.get_template("litellm.yaml.j2").render(
        models={"coder": "a", "general": "b", "fast": "c", "embed": "d"},
        backend_base=cfg.backend_base, ports=cfg.ports, api_key="k",
        render_dir="/tmp", image_enabled=False,
    ))
    assert out["litellm_settings"]["num_retries"] >= 2


# --- issue: reasoning_effort must reach LM Studio through LiteLLM --------------
def test_all_chat_models_allow_reasoning_effort():
    import yaml
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("smallwonder", "templates"),
                      keep_trailing_newline=True)
    cfg = Config()
    out = yaml.safe_load(env.get_template("litellm.yaml.j2").render(
        models={"coder": "a", "general": "b", "fast": "c", "embed": "d"},
        backend_base=cfg.backend_base, ports=cfg.ports, api_key="k",
        render_dir="/tmp", image_enabled=False,
    ))
    chat = [m for m in out["model_list"]
            if m["model_name"] in ("coder", "general", "fast") or m["model_name"].endswith("*")]
    assert len(chat) == 4
    for m in chat:
        assert "reasoning_effort" in m["litellm_params"]["allowed_openai_params"], m["model_name"]
