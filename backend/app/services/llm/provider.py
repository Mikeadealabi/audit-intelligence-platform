from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolExecutionResult:
    """What a tool executor returns. `content` is sent back to the model as the
    tool_result; `summary` is a safe, short string for audit logs (never full
    financial payloads); `evidence_ids` are any transaction_record IDs this call
    actually revealed, used later to ground the model's claims."""

    content: object
    summary: str
    evidence_ids: list[str] = field(default_factory=list)
    is_error: bool = False


@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    result_summary: str
    is_error: bool
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class InvestigationOutcome:
    raw_result_json: str
    tool_calls: list[ToolCallRecord]
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """Raised on timeout, rate limit, invalid output, or any other provider-side
    failure. The caller must leave the InvestigationRun in a `failed` state and
    allow a human-triggered retry — never fabricate a result to fill the gap."""


ToolExecutor = Callable[[str, dict], ToolExecutionResult]


class LLMProvider(Protocol):
    def investigate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        tool_executor: ToolExecutor,
        output_schema: dict,
        max_tool_turns: int,
    ) -> InvestigationOutcome: ...
