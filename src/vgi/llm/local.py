"""Local LLM through Ollama's HTTP API (no API key, runs on the render box's GPUs or the Mac).

- generate(): free text (the dramatic treatment)
- cited():    Claude-style citations are emulated: sources are numbered [1]..[n] in the prompt, the model must cite
              with [n] markers, and the markers are mapped back to the documents
- parse():    Ollama structured outputs (`format` = the Pydantic JSON schema), validated, one repair retry
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from .base import CitedResult, Doc, ParsedResult, T


class LocalLLMError(RuntimeError):
    pass


class OllamaLLM:
    name = "local"

    def __init__(self, host: str, model: str, num_ctx: int = 32768, keep_alive: str | int = "0", think: Any = None,
                 timeout_s: float = 1800, temperature: float = 0.3, before_call=None):
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.think = think
        self.temperature = temperature
        self.before_call = before_call
        self.http = httpx.Client(base_url=self.host, timeout=timeout_s)

    # ---------- health ----------
    def installed_models(self) -> list[str]:
        try:
            r = self.http.get("/api/tags", timeout=5)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LocalLLMError(f"Ollama is not reachable at {self.host} ({e}). Start it: `ollama serve` "
                                f"(Linux: `bash scripts/ollama_serve.sh`)") from e
        return [m["name"] for m in r.json().get("models", [])]

    def ensure_model(self) -> None:
        names = self.installed_models()
        want = self.model if ":" in self.model else f"{self.model}:latest"
        if want not in names and self.model not in names:
            raise LocalLLMError(f"model {self.model!r} is not pulled on {self.host} (have: {names}). "
                                f"Run: uv run vgi llm pull")

    # ---------- calls ----------
    def _chat(self, system: str, user: str, fmt: dict | None = None, temperature: float | None = None) -> tuple[str, dict]:
        if self.before_call:
            self.before_call()
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "keep_alive": self.keep_alive,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"num_ctx": self.num_ctx, "temperature": self.temperature if temperature is None else temperature},
        }
        if fmt is not None:
            body["format"] = fmt
        if self.think is not None:
            body["think"] = self.think
        try:
            r = self.http.post("/api/chat", json=body)
        except httpx.HTTPError as e:
            raise LocalLLMError(f"Ollama request failed: {e}") from e
        if r.status_code != 200:
            raise LocalLLMError(f"Ollama {r.status_code}: {r.text[:400]}")
        data = r.json()
        content = (data.get("message") or {}).get("content", "")
        usage = {"input_tokens": int(data.get("prompt_eval_count") or 0), "output_tokens": int(data.get("eval_count") or 0)}
        return content, usage

    def generate(self, system: str, prompt: str, temperature: float | None = None) -> ParsedResult:
        text, usage = self._chat(system, prompt, temperature=temperature)
        return ParsedResult(obj=_strip_think(text), usage=usage, cost_usd=0.0, model=self.model)

    def cited(self, system: str, docs: list[Doc], question: str) -> CitedResult:
        numbered = "\n\n".join(f"[{i + 1}] {d.title}\n{d.text}" for i, d in enumerate(docs))
        rules = ("\n\nCITATION RULES: the sources are numbered [1]..[n] above. After every factual sentence write the "
                 "number(s) of the source(s) that support it in square brackets, e.g. [2] or [1][4]. Use only these "
                 "sources. If the sources do not support a claim, put it under 'Uncertain or disputed points' instead.")
        text, usage = self._chat(system + rules, f"SOURCES\n\n{numbered}\n\nTASK\n{question}", temperature=self.temperature)
        text = _strip_think(text)
        used = sorted({int(n) for n in re.findall(r"\[(\d{1,3})\]", text) if 1 <= int(n) <= len(docs)})
        renum = {old: new for new, old in enumerate(used, start=1)}
        text = re.sub(r"\[(\d{1,3})\]", lambda m: f"[{renum[int(m.group(1))]}]" if int(m.group(1)) in renum else "", text)
        sources = [{"n": renum[o], "id": docs[o - 1].id, "title": docs[o - 1].title, "url": docs[o - 1].url,
                    "license": docs[o - 1].license, "cited_text": ""} for o in used]
        return CitedResult(text=text, sources=sources, usage=usage, cost_usd=0.0, model=self.model)

    def parse(self, system: str, prompt: str, schema: type[T]) -> ParsedResult:
        fmt = schema.model_json_schema()
        sys2 = system + "\n\nReply with JSON only, matching the given schema exactly."
        content, usage = self._chat(sys2, prompt, fmt=fmt, temperature=0.2)
        try:
            return ParsedResult(obj=schema.model_validate_json(_strip_think(content)), usage=usage, model=self.model)
        except ValidationError as e:
            repair = (f"{prompt}\n\nYour previous JSON was invalid:\n{str(e)[:1500]}\n\nPrevious JSON:\n{content[:6000]}\n\n"
                      f"Return corrected JSON only.")
            content2, usage2 = self._chat(sys2, repair, fmt=fmt, temperature=0.1)
            try:
                obj = schema.model_validate_json(_strip_think(content2))
            except ValidationError as e2:
                raise LocalLLMError(f"local model returned invalid {schema.__name__} twice: {str(e2)[:600]}") from e2
            return ParsedResult(obj=obj, usage={k: usage[k] + usage2[k] for k in usage}, model=self.model)

    # ---------- model management ----------
    def pull(self, on_progress=None) -> None:
        with self.http.stream("POST", "/api/pull", json={"model": self.model, "stream": True}, timeout=None) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                if ev.get("error"):
                    raise LocalLLMError(ev["error"])
                if on_progress:
                    on_progress(ev)

    def unload(self) -> None:
        try:
            self.http.post("/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=30)
        except httpx.HTTPError:
            pass


def _strip_think(text: str) -> str:
    """Some models inline <think>…</think> even with structured output; drop it."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
