from smallwonder import preflight
from smallwonder.config import Config

PORTS = Config().ports


def test_passes_on_compatible_system(monkeypatch):
    # CI runners vary (macos-14 has 7GB RAM), so control every input:
    # a compatible system must produce zero failures.
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/local/bin/uv")
    monkeypatch.setattr(preflight, "_port_free_or_ours", lambda p: (True, ""))
    failures = preflight.check(PORTS, min_ram_gb=1)
    assert failures == []


def test_refuses_non_darwin(monkeypatch):
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    failures = preflight.check(PORTS)
    assert len(failures) == 1
    assert "macOS" in failures[0].remedy


def test_refuses_intel(monkeypatch):
    monkeypatch.setattr(preflight, "_is_apple_silicon", lambda: False)
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/local/bin/uv")
    monkeypatch.setattr(preflight, "_port_free_or_ours", lambda p: (True, ""))
    failures = preflight.check(PORTS)
    assert any("Apple Silicon" in f.remedy for f in failures)


def test_refuses_low_ram(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/local/bin/uv")
    monkeypatch.setattr(preflight, "_port_free_or_ours", lambda p: (True, ""))
    failures = preflight.check(PORTS, min_ram_gb=1024)
    assert any(f.what == "Memory" for f in failures)


def test_refuses_missing_uv(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: None)
    monkeypatch.setattr(preflight, "_port_free_or_ours", lambda p: (True, ""))
    failures = preflight.check(PORTS)
    assert any(f.what == "uv" for f in failures)


def test_reports_occupied_port(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/local/bin/uv")
    monkeypatch.setattr(
        preflight, "_port_free_or_ours",
        lambda p: (False, "nginx") if p == 8080 else (True, "")
    )
    failures = preflight.check(PORTS)
    assert any("8080" in f.what and "nginx" in f.detail for f in failures)
