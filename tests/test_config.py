from smallwonder import config as config_mod
from smallwonder.config import Config


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "config.yaml")

    cfg = Config(backend="llamaswap", tier="32gb")
    cfg.models = {"coder": "x", "general": "y", "fast": "z", "embed": "e"}
    cfg.save()

    loaded = Config.load()
    assert loaded.backend == "llamaswap"
    assert loaded.tier == "32gb"
    assert loaded.models["coder"] == "x"
    assert loaded.api_key == cfg.api_key  # key survives round-trip
    assert loaded.ports["router"] == 4000


def test_unique_api_keys():
    assert Config().api_key != Config().api_key


def test_load_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "nope.yaml")
    try:
        Config.load()
        raise AssertionError("should have raised")
    except FileNotFoundError:
        pass
    assert Config.load_or_default().backend == "lmstudio"
