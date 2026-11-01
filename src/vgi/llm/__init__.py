from .base import CitedResult, Doc, ParsedResult
from .claude import ClaudeLLM
from .stub import StubLLM

__all__ = ["CitedResult", "Doc", "ParsedResult", "ClaudeLLM", "StubLLM"]


def get_llm(ctx, stage: str):
    """Pick the LLM for a stage: stub on dry-run / no key / backend=stub, else Claude."""
    cfg = ctx.stage_cfg(stage)
    if ctx.dry_run or getattr(cfg, "backend", "stub") == "stub":
        return StubLLM(ctx.job.manifest.subject, ctx.cfg.topic.name)
    if not ctx.secrets.has_claude():
        ctx.log.for_stage(stage).warn("ANTHROPIC_API_KEY missing; using the stub LLM")
        return StubLLM(ctx.job.manifest.subject, ctx.cfg.topic.name)
    return ClaudeLLM(ctx.secrets.anthropic_api_key, cfg.model, cfg.effort, cfg.max_tokens, ctx.cfg.pricing)
