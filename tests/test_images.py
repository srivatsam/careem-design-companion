"""Unit tests for image-generation gating (app/agent/images.py)."""
from __future__ import annotations

from app.agent import images


def test_has_real_photo_true_for_row_image_url():
    p = {"perfume_id": "p1", "image_url": "https://cdn.example.com/p1.jpg", "product_url": None}
    assert images.has_real_photo(p) is True


def test_has_real_photo_true_for_derivable_fragrantica_photo():
    p = {"perfume_id": "p1", "image_url": None, "product_url": "https://www.fragrantica.com/perfume/x/y-123.html"}
    assert images.has_real_photo(p) is True


def test_has_real_photo_false_without_any_real_image():
    p = {"perfume_id": "p1", "image_url": None, "product_url": "https://www.google.com/search?q=x"}
    assert images.has_real_photo(p) is False
    p2 = {"perfume_id": "p2", "image_url": "", "product_url": None}
    assert images.has_real_photo(p2) is False


class _RecordingThread:
    spawned: list = []

    def __init__(self, target=None, daemon=None):
        _RecordingThread.spawned.append(target)

    def start(self):
        pass


def test_request_generation_skips_when_real_photo_exists(monkeypatch):
    # Even with generation fully "configured", a real photo must short-circuit before any thread is spawned.
    monkeypatch.setattr(images, "image_deployment", lambda: "some-deployment")
    monkeypatch.setattr(images.settings, "azure_openai_endpoint", "https://example.com")
    monkeypatch.setattr(images.settings, "azure_openai_api_key", "key")
    _RecordingThread.spawned = []
    monkeypatch.setattr(images.threading, "Thread", _RecordingThread)

    p = {"perfume_id": "p_real", "image_url": "https://cdn.example.com/x.jpg", "product_url": None}
    images.request_generation(p)
    assert _RecordingThread.spawned == []


def test_request_generation_still_runs_without_a_real_photo(monkeypatch):
    monkeypatch.setattr(images, "image_deployment", lambda: "some-deployment")
    monkeypatch.setattr(images.settings, "azure_openai_endpoint", "https://example.com")
    monkeypatch.setattr(images.settings, "azure_openai_api_key", "key")
    _RecordingThread.spawned = []
    monkeypatch.setattr(images.threading, "Thread", _RecordingThread)

    p = {"perfume_id": "p_needs_generation", "image_url": None, "product_url": None}
    images.request_generation(p)
    assert len(_RecordingThread.spawned) == 1
