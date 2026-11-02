from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class Doc:
    id: str
    title: str
    text: str
    license: str = ""
    url: str = ""


@dataclass
class CitedResult:
    text: str                     # markdown with [n] markers
    sources: list[dict[str, Any]] # n -> {id,title,url,license}
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    model: str = ""


@dataclass
class ParsedResult:
    obj: Any
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    model: str = ""


class LLM(Protocol):
    name: str

    def cited(self, system: str, docs: list[Doc], question: str) -> CitedResult: ...
    def parse(self, system: str, prompt: str, schema: type[T]) -> ParsedResult: ...
    def generate(self, system: str, prompt: str, temperature: float | None = None) -> ParsedResult: ...
