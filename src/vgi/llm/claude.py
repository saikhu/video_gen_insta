"""Claude API client (anthropic SDK 2.x). Two call shapes:
- cited(): documents with citations enabled (beta create with server-side fallbacks) -> markdown + source map
- parse(): structured output via client.messages.parse(output_format=PydanticModel)
Citations and structured output cannot be combined in one request (API returns 400), hence two passes.
"""
from __future__ import annotations

from typing import Any

import anthropic

from ..core.cost import claude_cost_usd
from .base import CitedResult, Doc, ParsedResult, T


def _usage(resp: Any) -> dict[str, int]:
    u = getattr(resp, "usage", None)
    if not u:
        return {}
    return {k: int(getattr(u, k, 0) or 0) for k in
            ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}


class ClaudeLLM:
    name = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "high", max_tokens: int = 16000,
                 pricing: dict[str, Any] | None = None):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.pricing = pricing or {}

    def cited(self, system: str, docs: list[Doc], question: str) -> CitedResult:
        content: list[dict[str, Any]] = []
        for d in docs:
            content.append({
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": d.text},
                "title": d.title[:200],
                "context": f"id={d.id}; license={d.license}; url={d.url}",
                "citations": {"enabled": True},
            })
        content.append({"type": "text", "text": question})
        kwargs: dict[str, Any] = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                                      messages=[{"role": "user", "content": content}],
                                      output_config={"effort": self.effort})
        if self.model.startswith(("claude-opus-5", "claude-fable", "claude-sonnet-5-5")):
            resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                    **kwargs)
        else:
            resp = self.client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the research request: {getattr(resp, 'stop_details', None)}")
        sources: list[dict[str, Any]] = []
        index: dict[int, int] = {}
        out: list[str] = []
        for block in resp.content:
            if block.type != "text":
                continue
            out.append(block.text)
            for c in getattr(block, "citations", None) or []:
                di = getattr(c, "document_index", None)
                if di is None:
                    continue
                if di not in index:
                    d = docs[di]
                    sources.append({"n": len(sources) + 1, "id": d.id, "title": d.title, "url": d.url,
                                    "license": d.license, "cited_text": (getattr(c, "cited_text", "") or "")[:200]})
                    index[di] = len(sources)
                out.append(f"[{index[di]}]")
        usage = _usage(resp)
        return CitedResult(text="".join(out), sources=sources, usage=usage,
                           cost_usd=claude_cost_usd(self.pricing, self.model, usage), model=self.model)

    def parse(self, system: str, prompt: str, schema: type[T]) -> ParsedResult:
        resp = self.client.messages.parse(model=self.model, max_tokens=self.max_tokens, system=system,
                                          messages=[{"role": "user", "content": prompt}],
                                          output_format=schema, output_config={"effort": self.effort})
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the request: {getattr(resp, 'stop_details', None)}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("Claude hit max_tokens before finishing the structured output; raise script.max_tokens")
        usage = _usage(resp)
        return ParsedResult(obj=resp.parsed_output, usage=usage, cost_usd=claude_cost_usd(self.pricing, self.model, usage),
                            model=self.model)
