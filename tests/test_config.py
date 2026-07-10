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


def test_old_config_gains_new_keys(tmp_path, monkeypatch):
    """Upgrade path: a config saved by an older version must pick up
    newly-introduced ports/modules instead of KeyError-ing."""
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "config.yaml")
    (tmp_path / "config.yaml").write_text(
        "backend: lmstudio\n"
        "ports: {backend: 1234, router: 4000, ui: 8080}\n"   # pre-tts era
        "modules: {image: true}\n"
    )
    cfg = Config.load()
    assert cfg.ports["tts"] == 8880          # new key from defaults
    assert cfg.ports["ui"] == 8080           # saved value wins
    assert cfg.modules["image"] is True
    assert cfg.modules["voice"] is False     # new module key present
