"""Regression tests for the voice (TTS) module."""

from types import SimpleNamespace

from smallwonder.config import Config


def test_enable_tts_sets_openai_engine_and_preserves_config(monkeypatch):
    from smallwonder.openwebui import OpenWebUI

    ui = OpenWebUI.__new__(OpenWebUI)
    posted = {}
    monkeypatch.setattr(
        ui, "get",
        lambda path, **kw: SimpleNamespace(
            json=lambda: {
                "tts": {"ENGINE": "", "SPLIT_ON": "punctuation", "API_KEY": ""},
                "stt": {"ENGINE": "", "WHISPER_MODEL": "base"},
            }
        ),
    )
    monkeypatch.setattr(
        ui, "post",
        lambda path, json=None, **kw: (posted.update(json),
                                       SimpleNamespace(raise_for_status=lambda: None))[1],
    )
    ui.enable_tts("http://127.0.0.1:8880/v1", model="kokoro", voice="af_heart")

    assert posted["tts"]["ENGINE"] == "openai"
    assert posted["tts"]["OPENAI_API_BASE_URL"] == "http://127.0.0.1:8880/v1"
    assert posted["tts"]["MODEL"] == "kokoro"
    assert posted["tts"]["VOICE"] == "af_heart"
    # wav avoids the TTS server's ffmpeg requirement for mp3
    assert posted["tts"]["OPENAI_PARAMS"] == {"response_format": "wav"}
    # unknown/unrelated keys survive the round-trip
    assert posted["tts"]["SPLIT_ON"] == "punctuation"
    # STT untouched: stays on built-in local whisper
    assert posted["stt"]["ENGINE"] == ""


def test_voice_port_in_default_config():
    assert "tts" in Config().ports


def test_mlx_audio_install_pins_arm64_python(monkeypatch):
    """Rosetta-brew uv resolves x86_64 wheels; mlx ships none. The install
    must request an aarch64 python explicitly."""
    import subprocess as sp

    from smallwonder.modules import voice

    cmds = []
    monkeypatch.setattr(voice, "is_installed", lambda: False)
    monkeypatch.setattr(voice.shutil, "which", lambda b: "/usr/local/bin/uv")
    monkeypatch.setattr(
        voice.subprocess, "run",
        lambda cmd, check=True: cmds.append(cmd) or sp.CompletedProcess(cmd, 0),
    )
    voice.install()
    assert any("aarch64" in arg for arg in cmds[0])
