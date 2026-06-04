"""Probe contract: a probe bundles a set of conditions, an MCP toolset,
and a trial runner.

No abstract base class. Just a Protocol so duck-typing works for future
probes (decompose, escalate, ...) without forcing inheritance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Protocol


@dataclass
class Condition:
    code: str                    # short identifier: "forced" | "neutral" | "anti"
    system_prompt: str
    allowed_tools: list[str]


class ProbeProtocol(Protocol):
    name: str                                # e.g. "verify"
    conditions: dict[str, Condition]

    @property
    def mcp_server(self) -> Any:
        ...

    async def run_trial(
        self,
        ex: dict,
        condition: Condition,
        model_id: str,
        *,
        save_trace_root: Any | None = None,
        audit_first_init: bool = False,
    ) -> dict[str, Any]:
        ...
