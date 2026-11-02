from .base import CitedResult, Doc, ParsedResult
from .claude import ClaudeLLM
from .local import LocalLLMError, OllamaLLM
from .stub import StubLLM

__all__ = ["CitedResult", "Doc", "ParsedResult", "ClaudeLLM", "OllamaLLM", "LocalLLMError", "StubLLM", "get_llm",
           "local_llm"]


def local_llm(cfg, log=None, root=None, comfy_endpoints: list[str] | None = None) -> OllamaLLM:
    """Build the Ollama client from configs/llm.yaml (+ env overrides)."""
    lc = (cfg.llm or {}).get("local", {})
    before = None
    if lc.get("free_comfy_first", True) and comfy_endpoints:
        def before() -> None:          # GPU hand-off: unload ComfyUI models so the LLM fits in VRAM
            from ..backends.comfy_client import ComfyClient

            for e in comfy_endpoints:
                c = ComfyClient(e, timeout_s=10)
                if c.healthy():
                    c.free()
    return OllamaLLM(host=lc.get("host", "http://127.0.0.1:11434"), model=lc.get("model", "qwen3.8:27b"),
                     num_ctx=int(lc.get("num_ctx", 32768)), keep_alive=lc.get("keep_alive", "0"), think=lc.get("think"),
                     timeout_s=float(lc.get("timeout_seconds", 1800)), before_call=before)


def get_llm(ctx, stage: str):
    """stub on --dry-run or backend: stub; local (Ollama) or claude as configured. A configured backend that is
    unavailable is an error, never a silent fallback to canned text."""
    cfg = ctx.stage_cfg(stage)
    backend = getattr(cfg, "backend", "stub")
    if ctx.dry_run or backend == "stub":
        return StubLLM(ctx.job.manifest.subject, ctx.cfg.topic.name)
    if backend in ("local", "ollama"):
        llm = local_llm(ctx.cfg, comfy_endpoints=ctx.cfg.env.comfy.endpoints if ctx.cfg.env.comfy.gpu_lease else None)
        llm.ensure_model()
        return llm
    if backend == "claude":
        if not ctx.secrets.has_claude():
            raise RuntimeError(f"{stage}: backend is claude but ANTHROPIC_API_KEY is not set (.env); "
                               f"set backend: local in configs/stages/{stage}.yaml to use the local model")
        cc = (ctx.cfg.llm or {}).get("claude", {})
        return ClaudeLLM(ctx.secrets.anthropic_api_key, cc.get("model", cfg.model), cc.get("effort", cfg.effort),
                         cfg.max_tokens, ctx.cfg.pricing)
    raise ValueError(f"unknown LLM backend {backend!r} (local | claude | stub)")
