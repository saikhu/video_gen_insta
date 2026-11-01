"""ComfyUI HTTP/WebSocket client with the failure semantics the plan requires.

- client_id on POST /prompt, progress via /ws filtered by prompt_id, polling /history as fallback
- execution_error / execution_interrupted handling, per-prompt timeout, /interrupt, /free, /upload/image
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, endpoint: str, timeout_s: float = 30.0):
        self.endpoint = endpoint.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self.http = httpx.Client(base_url=self.endpoint, timeout=timeout_s)

    # ---------- health ----------
    def healthy(self) -> bool:
        try:
            r = self.http.get("/system_stats")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def system_stats(self) -> dict[str, Any]:
        return self.http.get("/system_stats").json()

    def queue_depth(self) -> int:
        q = self.http.get("/queue").json()
        return len(q.get("queue_running", [])) + len(q.get("queue_pending", []))

    # ---------- submit / wait ----------
    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        r = self.http.post("/prompt", json={"prompt": workflow, "client_id": self.client_id})
        if r.status_code != 200:
            raise ComfyError(f"POST /prompt {r.status_code}: {r.text[:500]}")
        data = r.json()
        if data.get("node_errors"):
            raise ComfyError(f"workflow validation errors: {json.dumps(data['node_errors'])[:800]}")
        return data["prompt_id"]

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        r = self.http.get(f"/history/{prompt_id}")
        if r.status_code != 200:
            return None
        return r.json().get(prompt_id)

    def wait(self, prompt_id: str, timeout_s: float, poll_s: float = 3.0, on_progress=None) -> dict[str, Any]:
        """Wait via websocket when possible, otherwise poll /history. Returns the history entry."""
        deadline = time.time() + timeout_s
        try:
            import websocket  # websocket-client

            ws_url = self.endpoint.replace("http", "ws", 1) + f"/ws?clientId={self.client_id}"
            ws = websocket.create_connection(ws_url, timeout=poll_s)
            try:
                while time.time() < deadline:
                    try:
                        raw = ws.recv()
                    except Exception:  # noqa: BLE001  (timeout → poll history)
                        h = self.history(prompt_id)
                        if h and h.get("status", {}).get("completed"):
                            return h
                        if h and h.get("status", {}).get("status_str") == "error":
                            raise ComfyError(self._error_text(h))
                        continue
                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    data = msg.get("data", {})
                    if data.get("prompt_id") not in (None, prompt_id):
                        continue
                    t = msg.get("type")
                    if t == "progress" and on_progress:
                        on_progress(data.get("value", 0), data.get("max", 0))
                    elif t == "execution_error":
                        raise ComfyError(f"execution_error in node {data.get('node_type')}: {data.get('exception_message')}")
                    elif t == "execution_interrupted":
                        raise ComfyError("execution_interrupted")
                    elif t == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                        h = self.history(prompt_id)
                        if h:
                            return h
            finally:
                ws.close()
        except ImportError:
            pass
        except ComfyError:
            raise
        except Exception:  # noqa: BLE001  websocket problems → polling
            pass
        while time.time() < deadline:
            h = self.history(prompt_id)
            if h:
                st = h.get("status", {})
                if st.get("status_str") == "error":
                    raise ComfyError(self._error_text(h))
                if st.get("completed"):
                    return h
            time.sleep(poll_s)
        raise ComfyError(f"timeout after {timeout_s}s waiting for {prompt_id}")

    @staticmethod
    def _error_text(h: dict[str, Any]) -> str:
        for m in h.get("status", {}).get("messages", []):
            if m and m[0] == "execution_error":
                d = m[1]
                return f"execution_error in {d.get('node_type')}: {d.get('exception_message')}"
        return "execution error"

    # ---------- outputs ----------
    def outputs(self, history_entry: dict[str, Any]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for node_out in history_entry.get("outputs", {}).values():
            for key in ("images", "gifs", "videos", "audio"):
                for f in node_out.get(key, []):
                    files.append(f)
        return files

    def download(self, f: dict[str, Any], dest: Path) -> Path:
        r = self.http.get("/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                            "type": f.get("type", "output")})
        if r.status_code != 200:
            raise ComfyError(f"/view {r.status_code} for {f}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest

    def upload_image(self, path: Path, subfolder: str = "vgi") -> str:
        with Path(path).open("rb") as fh:
            r = self.http.post("/upload/image", files={"image": (Path(path).name, fh, "image/png")},
                               data={"subfolder": subfolder, "overwrite": "true"})
        if r.status_code != 200:
            raise ComfyError(f"/upload/image {r.status_code}: {r.text[:300]}")
        d = r.json()
        return f"{d.get('subfolder', '')}/{d['name']}" if d.get("subfolder") else d["name"]

    # ---------- control ----------
    def free(self) -> None:
        self.http.post("/free", json={"unload_models": True, "free_memory": True})

    def interrupt(self) -> None:
        self.http.post("/interrupt")


def fill_workflow(template: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Replace {{key}} placeholders anywhere in an API-format workflow. Numeric strings become numbers."""
    def sub(v: Any) -> Any:
        if isinstance(v, str):
            for k, val in values.items():
                token = "{{" + k + "}}"
                if v == token:
                    return val
                if token in v:
                    v = v.replace(token, str(val))
            return v
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        if isinstance(v, list):
            return [sub(x) for x in v]
        return v
    return sub(template)


class EndpointPool:
    """One in-flight job per endpoint. `acquire()` blocks until a healthy endpoint is free; callers release it.

    Thread-safe: the video stage renders scenes concurrently with as many workers as there are endpoints,
    so each worker holds exactly one ComfyUI instance (and its websocket) at a time.
    """

    def __init__(self, endpoints: list[str]):
        import queue
        import threading

        self.clients = [ComfyClient(e) for e in endpoints]
        self._free: "queue.Queue[ComfyClient]" = queue.Queue()
        self._lock = threading.Lock()
        self._healthy = [c for c in self.clients if c.healthy()]
        for c in self._healthy:
            self._free.put(c)

    @property
    def size(self) -> int:
        return len(self._healthy)

    def healthy(self) -> list[ComfyClient]:
        return list(self._healthy)

    def acquire(self, timeout_s: float = 3600.0) -> ComfyClient:
        import queue

        if not self._healthy:
            raise ComfyError("no healthy ComfyUI endpoint")
        try:
            return self._free.get(timeout=timeout_s)
        except queue.Empty as e:
            raise ComfyError("timed out waiting for a free ComfyUI endpoint") from e

    def release(self, client: ComfyClient) -> None:
        self._free.put(client)

    def next(self) -> ComfyClient:
        """Non-blocking convenience for single-shot use (image backend); prefer acquire/release in loops."""
        if not self._healthy:
            raise ComfyError("no healthy ComfyUI endpoint")
        with self._lock:
            c = self._healthy[0]
            self._healthy.append(self._healthy.pop(0))
        return c

    def free_all(self) -> None:
        for c in self._healthy:
            c.free()
