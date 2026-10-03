"""Concurrency, fidelity and cancellation checks for the inspection fast path."""
import asyncio
import io
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.api.v1 import inspections
from app.core.config import settings
from app.db.models import Decision
from app.services.heatmap.generator import (
    generate_heatmap_from_anomaly_map, generate_heatmap_from_regions,
)
from app.services.vlm.base import ProductContext
from app.services.vlm.groq import GroqVisionEngine


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_upload', [None, 'original', 'heatmap'])
async def test_uploads_overlap_and_keep_successful_images(monkeypatch, failed_upload):
    original_started, heatmap_started = asyncio.Event(), asyncio.Event()
    defects = [{'type': 'crack'}]
    monkeypatch.setattr(inspections, '_prepare_heatmap', lambda *_: (defects, b'map'))

    async def original(*_):
        original_started.set()
        await asyncio.wait_for(heatmap_started.wait(), 2)
        if failed_upload == 'original':
            raise RuntimeError('storage unavailable')
        return 'original-url'

    async def heatmap(*_):
        heatmap_started.set()
        await asyncio.wait_for(original_started.wait(), 2)
        if failed_upload == 'heatmap':
            raise RuntimeError('storage unavailable')
        return 'heatmap-url'

    monkeypatch.setattr(inspections.storage_service, 'upload_original', original)
    monkeypatch.setattr(inspections.storage_service, 'upload_heatmap', heatmap)
    result = await inspections._prepare_and_upload(object(), b'image', 'fixture')
    assert result == (defects, None if failed_upload == 'original' else 'original-url',
                      None if failed_upload == 'heatmap' else 'heatmap-url')


@pytest.mark.asyncio
async def test_heatmap_processing_does_not_block_event_loop(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def render(*_):
        started.set()
        if not release.wait(2):
            raise AssertionError('API event loop blocked by image processing')
        return [], None

    async def original(*_):
        await asyncio.to_thread(started.wait, 2)
        release.set()
        return 'original-url'

    monkeypatch.setattr(inspections, '_prepare_heatmap', render)
    monkeypatch.setattr(inspections.storage_service, 'upload_original', original)
    assert await inspections._prepare_and_upload(object(), b'image', 'fixture') == (
        [], 'original-url', None,
    )


@pytest.mark.parametrize('native', [True, False])
def test_skipping_unused_overlay_preserves_every_heatmap_pixel(native):
    buffer = io.BytesIO()
    Image.new('RGB', (160, 120), (180, 180, 180)).save(buffer, format='JPEG')
    if native:
        args = (np.linspace(0, 1, 256).reshape(16, 16), buffer.getvalue())
        generate = generate_heatmap_from_anomaly_map
    else:
        args = ([{'x': .2, 'y': .2, 'width': .3, 'height': .3}], buffer.getvalue())
        generate = generate_heatmap_from_regions
    reference, overlay = generate(*args)
    optimized, omitted = generate(*args, include_overlay=False)
    assert overlay and omitted == b''
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(reference))),
                          np.asarray(Image.open(io.BytesIO(optimized))))


@pytest.mark.asyncio
async def test_vlm_reuses_client_and_cancels_timed_out_request(monkeypatch):
    import groq
    clients = []
    cancelled = asyncio.Event()

    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.closed = False
            self.slow = False
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            clients.append(self)

        async def create(self, **kwargs):
            if self.slow:
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.set()
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"decision":"PASS","anomaly_score":0,"confidence":0.9,"defects":[]}'
            ))])

        async def close(self):
            self.closed = True

    monkeypatch.setattr(groq, 'AsyncGroq', Client)
    monkeypatch.setattr(settings, 'GROQ_API_KEY', 'test-only')
    monkeypatch.setattr(settings, 'ENGINE_TIMEOUT_SECONDS', 0.05)
    engine = GroqVisionEngine()
    context = ProductContext()
    assert (await engine.inspect(b'image', context)).decision == Decision.PASS
    assert (await engine.inspect(b'image', context)).decision == Decision.PASS
    assert len(clients) == 1 and clients[0].options['max_retries'] == 0
    clients[0].slow = True
    with pytest.raises(asyncio.TimeoutError):
        await engine.inspect(b'image', context)
    assert cancelled.is_set()
    await engine.close()
    assert clients[0].closed
