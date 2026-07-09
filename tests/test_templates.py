import json

import yaml
from jinja2 import Environment, PackageLoader

from smallwonder.config import Config

env = Environment(loader=PackageLoader("smallwonder", "templates"), keep_trailing_newline=True)

MODELS = {
    "coder": "qwen/qwen3.6-27b",
    "general": "qwen/qwen3.6-35b-a3b",
    "fast": "qwen/qwen3.5-4b",
    "embed": "text-embedding-nomic-embed-text-v1.5",
}


def _ctx(**over):
    cfg = Config()
    ctx = {
        "models": MODELS,
        "backend_base": cfg.backend_base,
        "ports": cfg.ports,
        "api_key": "sk-test",
        "render_dir": "/tmp/render",
        "image_enabled": False,
    }
    ctx.update(over)
    return ctx


def test_litellm_yaml_valid_and_complete():
    out = yaml.safe_load(env.get_template("litellm.yaml.j2").render(**_ctx()))
    names = [m["model_name"] for m in out["model_list"]]
    assert names == ["coder", "general", "fast", "local-embed", "auto", "local/*"]
    assert out["litellm_settings"]["telemetry"] is False
    assert out["general_settings"]["master_key"] == "sk-test"
    coder = out["model_list"][0]["litellm_params"]
    assert coder["allowed_openai_params"] == ["reasoning_effort"]
    assert coder["extra_body"]["ttl"] == 900
    fast = out["model_list"][2]["litellm_params"]
    assert fast["extra_body"]["ttl"] == 7200


def test_litellm_yaml_image_block_conditional():
    out = yaml.safe_load(env.get_template("litellm.yaml.j2").render(**_ctx(image_enabled=True)))
    names = [m["model_name"] for m in out["model_list"]]
    assert "image" in names


def test_auto_router_json_valid():
    out = json.loads(env.get_template("auto_router.json.j2").render(**_ctx()))
    assert out["encoder_type"] == "litellm"
    routes = {r["name"]: r for r in out["routes"]}
    assert routes["coder"]["score_threshold"] == 0.46
    assert routes["fast"]["score_threshold"] == 0.55
    assert len(routes["coder"]["utterances"]) >= 10


def test_plist_renders():
    out = env.get_template("launchd.plist.j2").render(
        label="ai.smallwonder.test",
        args=["/bin/echo", "hi"],
        env={"A": "b"},
        keep_alive=True,
        working_dir=None,
        calendar=None,
        log_path="/tmp/x.log",
    )
    assert "<string>ai.smallwonder.test</string>" in out
    assert "<key>RunAtLoad</key><true/>" in out


def test_plist_calendar_mode():
    out = env.get_template("launchd.plist.j2").render(
        label="l", args=["x"], env=None, keep_alive=False,
        working_dir=None, calendar={"hour": 6}, log_path="/tmp/x.log",
    )
    assert "StartCalendarInterval" in out
    assert "RunAtLoad" not in out


def test_llamaswap_yaml_valid():
    models = {
        "coder": "unsloth/A-GGUF:Q4_K_M",
        "general": "unsloth/B-GGUF:Q4_K_M",
        "fast": "unsloth/C-GGUF:Q4_K_M",
        "embed": "nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0",
    }
    out = yaml.safe_load(
        env.get_template("llama-swap.yaml.j2").render(
            ports=Config().ports, models=models,
            llama_server_bin="/opt/bin/llama-server", context_tokens=65536,
        )
    )
    assert out["listen"].endswith(":1234")
    assert set(out["models"]) == set(models.values())
