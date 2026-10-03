"""Async, serialized client for the isolated Member 1 worker process."""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.core.config import settings
from app.services.ml.member1_worker.protocol import PROTOCOL_VERSION


class Member1WorkerClient:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._runtime_info: dict[str, Any] | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def runtime_info(self) -> dict[str, Any] | None:
        return dict(self._runtime_info) if self._runtime_info else None

    def work_root(self) -> Path:
        configured = settings.ML_M1_WORK_ROOT.strip()
        return Path(configured).expanduser().resolve() if configured else (
            Path(tempfile.gettempdir()) / "visionqc-member1-work"
        ).resolve()

    def _safe_environment(self, python_executable: str, model_root: Path) -> dict[str, str]:
        # Deliberately whitelist the child environment: API keys and service
        # credentials from the FastAPI process are never passed to PyTorch.
        safe_names = (
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
            "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
            "LANG", "LC_ALL",
        )
        env = {name: os.environ[name] for name in safe_names if name in os.environ}
        executable = Path(python_executable).resolve()
        prefix = executable.parent
        runtime_paths = [
            str(prefix), str(prefix / "Scripts"), str(prefix / "Library" / "bin"),
            str(prefix / "Library" / "usr" / "bin"),
        ]
        if env.get("PATH"):
            runtime_paths.append(env["PATH"])
        path_value = os.pathsep.join(runtime_paths)
        env.update({
            "PATH": path_value,
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
            "VISIONQC_M1_MODEL_ROOT": str(model_root),
            "VISIONQC_M1_WORK_ROOT": str(self.work_root()),
            "VISIONQC_M1_CACHE_SIZE": str(max(1, settings.ML_M1_CACHE_SIZE)),
        })
        return env

    async def _stderr_pump(self, process: asyncio.subprocess.Process) -> None:
        assert process.stderr is not None
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if decoded:
                self._stderr_tail.append(decoded[:1000])

    async def _start_locked(self) -> None:
        if self.is_running and self._runtime_info:
            return
        await self._stop_locked(force=True)
        python = settings.ML_M1_PYTHON.strip() or sys.executable
        resolved_python = shutil.which(python) if not Path(python).is_absolute() else python
        if not resolved_python:
            raise RuntimeError("Configured Member 1 Python executable is unavailable")
        model_root = Path(settings.ML_M1_MODEL_ROOT).expanduser().resolve()
        if not model_root.is_dir():
            raise RuntimeError("Configured Member 1 model root is unavailable")
        work_root = self.work_root()
        work_root.mkdir(parents=True, exist_ok=True)
        worker_script = Path(__file__).with_name("worker.py").resolve()
        env = self._safe_environment(resolved_python, model_root)
        self._stderr_tail.clear()
        process = await asyncio.create_subprocess_exec(
            resolved_python, "-u", "-s", str(worker_script),
            cwd=str(model_root), env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=256 * 1024,
        )
        self._process = process
        self._stderr_task = asyncio.create_task(self._stderr_pump(process))
        try:
            response = await asyncio.wait_for(
                self._exchange_locked({"action": "hello"}),
                timeout=max(1, settings.ML_M1_WORKER_STARTUP_TIMEOUT),
            )
            info = response["result"]
            if info.get("protocol_version") != PROTOCOL_VERSION:
                raise RuntimeError("Member 1 worker protocol version mismatch")
            self._runtime_info = info
        except BaseException:
            await self._stop_locked(force=True)
            raise

    async def _exchange_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.returncode is not None or process.stdin is None or process.stdout is None:
            raise RuntimeError("Member 1 worker is not running")
        request_id = uuid.uuid4().hex
        request = {"version": PROTOCOL_VERSION, "request_id": request_id, **payload}
        process.stdin.write((json.dumps(request, allow_nan=False) + "\n").encode("utf-8"))
        await process.stdin.drain()
        line = await process.stdout.readline()
        if not line:
            raise RuntimeError("Member 1 worker closed its response stream")
        response = json.loads(line)
        if response.get("version") != PROTOCOL_VERSION or response.get("request_id") != request_id:
            raise RuntimeError("Member 1 worker returned an invalid protocol response")
        if not response.get("ok"):
            raise RuntimeError(f"Member 1 worker request failed: {response.get('error', 'unknown error')}")
        return response

    async def _request(self, payload: dict[str, Any], timeout: int | float) -> dict[str, Any]:
        async with self._lock:
            try:
                if not self.is_running or self._runtime_info is None:
                    await self._start_locked()
                response = await asyncio.wait_for(
                    self._exchange_locked(payload), timeout=max(1, timeout)
                )
                return response["result"]
            except BaseException:
                # A timed-out/cancelled line read would desynchronize the next
                # request. Kill the worker and start cleanly on the next call.
                await self._stop_locked(force=True)
                raise

    async def load_category(self, category: str) -> dict[str, Any]:
        return await self._request(
            {"action": "load", "category": category},
            settings.ML_M1_REQUEST_TIMEOUT,
        )

    async def inspect(self, category: str, image_bytes: bytes) -> dict[str, Any]:
        root = self.work_root()
        root.mkdir(parents=True, exist_ok=True)
        request_dir = root / f"request-{uuid.uuid4().hex}"
        request_dir.mkdir()
        image_path = request_dir / "input.png"
        map_path = request_dir / "anomaly_map.npy"
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.convert("RGB").save(image_path, format="PNG")
            result = await self._request({
                "action": "inspect",
                "category": category,
                "image_path": str(image_path.resolve()),
                "anomaly_map_path": str(map_path.resolve()),
            }, settings.ML_M1_REQUEST_TIMEOUT)
            if Path(result.get("anomaly_map_path", "")).resolve() != map_path.resolve():
                raise RuntimeError("Member 1 worker returned an unexpected map path")
            anomaly_map = np.load(map_path, allow_pickle=False)
            if anomaly_map.ndim != 2 or not np.isfinite(anomaly_map).all():
                raise RuntimeError("Member 1 worker returned an invalid anomaly map")
            result["anomaly_map"] = anomaly_map
            return result
        finally:
            shutil.rmtree(request_dir, ignore_errors=True)

    async def _stop_locked(self, force: bool) -> None:
        process = self._process
        self._process = None
        self._runtime_info = None
        if process is not None and process.returncode is None:
            if not force and process.stdin is not None and process.stdout is not None:
                try:
                    request_id = uuid.uuid4().hex
                    request = {"version": PROTOCOL_VERSION, "request_id": request_id,
                               "action": "shutdown"}
                    process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
                    await process.stdin.drain()
                    await asyncio.wait_for(process.stdout.readline(), timeout=2)
                    await asyncio.wait_for(process.wait(), timeout=2)
                except Exception:
                    force = True
            if force and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        task = self._stderr_task
        self._stderr_task = None
        if task is not None:
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def shutdown(self) -> None:
        async with self._lock:
            await self._stop_locked(force=False)


member1_worker = Member1WorkerClient()
