"""Regression tests for the Draw Things shim — every case here was a field bug."""

import base64
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from smallwonder.shim import dt_openai_shim as shim

client = TestClient(shim.app)


def _png(width: int, height: int) -> bytes:
    """Minimal valid PNG of the given dimensions."""
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x00\x00\x00" * width
    idat = zlib.compress(row * height)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


@pytest.fixture
def dt(monkeypatch):
    """Fake Draw Things: captures img2img/txt2img payloads."""
    captured = {}

    def fake_get(url, timeout=5):
        return FakeResponse({"model": captured.get("active_model", "flux_2_klein_4b_q8p.ckpt")})

    def fake_post(url, json=None, timeout=600):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse({"images": [base64.b64encode(b"fake-image").decode()]})

    monkeypatch.setattr(shim.requests, "get", fake_get)
    monkeypatch.setattr(shim.requests, "post", fake_post)
    return captured


# --- issue: Draw Things errors if both strength keys are sent ---------------
def test_edit_sends_only_denoising_strength(dt):
    dt["active_model"] = "z_image_turbo_1.0_q8p.ckpt"
    r = client.post("/v1/images/edits", data={"prompt": "x", "strength": "0.6"},
                    files={"image": ("a.png", _png(512, 512))})
    assert r.status_code == 200
    assert "denoising_strength" in dt["payload"]
    assert "strength" not in dt["payload"]


# --- issue #1: partial strength on instruction-edit models returns a no-op --
def test_edit_model_forces_full_strength(dt):
    dt["active_model"] = "flux_2_klein_4b_q8p.ckpt"
    client.post("/v1/images/edits", data={"prompt": "x", "strength": "0.5"},
                files={"image": ("a.png", _png(512, 512))})
    assert dt["payload"]["denoising_strength"] == 1.0


def test_img2img_model_honors_client_strength(dt):
    dt["active_model"] = "z_image_turbo_1.0_q8p.ckpt"
    client.post("/v1/images/edits", data={"prompt": "x", "strength": "0.5"},
                files={"image": ("a.png", _png(512, 512))})
    assert dt["payload"]["denoising_strength"] == 0.5


def test_img2img_model_default_strength(dt):
    dt["active_model"] = "z_image_turbo_1.0_q8p.ckpt"
    client.post("/v1/images/edits", data={"prompt": "x"},
                files={"image": ("a.png", _png(512, 512))})
    assert dt["payload"]["denoising_strength"] == 0.75


# --- issue: canvas must match init image dimensions --------------------------
def test_edit_defaults_canvas_to_image_dimensions(dt):
    client.post("/v1/images/edits", data={"prompt": "x"},
                files={"image": ("a.png", _png(640, 448))})
    assert dt["payload"]["width"] == 640
    assert dt["payload"]["height"] == 448


def test_png_dimension_parser():
    assert shim._image_dimensions(_png(1024, 768)) == (1024, 768)


# --- issue: 12MP photos rendered for >10min then timed out --------------------
def test_oversized_canvas_fails_fast(dt):
    r = client.post("/v1/images/edits", data={"prompt": "x", "size": "4032x3024"},
                    files={"image": ("a.png", _png(64, 64))})
    assert r.status_code == 400
    assert "resize" in r.json()["detail"]


# --- generations contract -----------------------------------------------------
def test_generations_contract(dt):
    r = client.post("/v1/images/generations", json={"prompt": "a cat", "size": "512x512"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["b64_json"]
    assert dt["payload"]["width"] == 512
