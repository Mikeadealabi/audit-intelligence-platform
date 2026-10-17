import json
from typing import Any, cast

import anthropic

from app.services.llm.provider import (
    InvestigationOutcome,
    ProviderError,
    ToolCallRecord,
    ToolExecutionResult,
    ToolExecutor,
)

# Kept small and fixed: this generates a structured investigation report, not a
# long-form document. Revisit if a future control needs more room.
_MAX_TOKENS_PER_CALL = 4096


class AnthropicProvider:
    """Calls the real Anthropic API. See docs/claude-tool-contract.md for the
    non-negotiables this implements: read-only tools only, every tool call
    authenticated/scoped/capped/logged by the caller (this class only executes
    whatever `tool_executor` it's given — it has no DB access itself), bounded
    tool-use turns, and a structured-output finalization phase so the model's
    answer is schema-validated JSON rather than parsed out of free text."""

    def __init__(self, *, api_key: str, model_id: str, timeout_seconds: float):
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds, max_retries=2)
        self._model_id = model_id

    def investigate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        tool_executor: ToolExecutor,
        output_schema: dict,
        max_tool_turns: int,
    ) -> InvestigationOutcome:
        messages: list[dict] = [{"role": "user", "content": user_message}]
        tool_calls_log: list[ToolCallRecord] = []
        input_tokens = 0
        output_tokens = 0

        try:
            for _ in range(max_tool_turns):
                # Our tool/message dicts are built dynamically from TOOL_DEFINITIONS and
                # conversation state to match the documented wire schema exactly; casting
                # to Any here is simpler and just as honest as re-declaring every one of
                # the SDK's TypedDict param shapes locally.
                response = self._client.messages.create(
                    model=self._model_id,
                    max_tokens=_MAX_TOKENS_PER_CALL,
                    system=system_prompt,
                    tools=cast(Any, tools),
                    messages=cast(Any, messages),
                )
                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens

                if response.stop_reason == "end_turn":
                    break

                if response.stop_reason != "tool_use":
                    raise ProviderError(f"Unexpected stop_reason during investigation: {response.stop_reason}")

                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in tool_use_blocks:
                    result = self._run_one_tool(block.name, block.input, tool_executor)
                    tool_calls_log.append(
                        ToolCallRecord(
                            tool_name=block.name,
                            arguments=block.input,
                            result_summary=result.summary,
                            is_error=result.is_error,
                            evidence_ids=result.evidence_ids,
                        )
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result.content if isinstance(result.content, str) else json.dumps(result.content),
                            "is_error": result.is_error,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})
            else:
                raise ProviderError(f"Investigation did not conclude within max_tool_turns={max_tool_turns}")

            final_response = self._client.messages.create(
                model=self._model_id,
                max_tokens=_MAX_TOKENS_PER_CALL,
                system=system_prompt,
                output_config=cast(Any, {"format": {"type": "json_schema", "schema": output_schema}}),
                messages=cast(
                    Any,
                    [
                        *messages,
                        {
                            "role": "user",
                            "content": "Provide your final structured investigation result now, per the required schema.",
                        },
                    ],
                ),
            )
            input_tokens += final_response.usage.input_tokens
            output_tokens += final_response.usage.output_tokens
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"Rate limited: {exc}") from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderError(f"Request timed out: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"Connection error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"API error ({exc.status_code}): {exc.message}") from exc

        text_block = next((b for b in final_response.content if b.type == "text"), None)
        if text_block is None:
            raise ProviderError("Final response had no text content to parse as the structured result")

        return InvestigationOutcome(
            raw_result_json=text_block.text,
            tool_calls=tool_calls_log,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @staticmethod
    def _run_one_tool(name: str, arguments: dict, tool_executor: ToolExecutor) -> ToolExecutionResult:
        try:
            return tool_executor(name, arguments)
        except Exception as exc:  # noqa: BLE001 — any tool failure becomes a tool_result error, not a crash
            return ToolExecutionResult(content={"error": str(exc)}, summary=f"error: {exc}", is_error=True)
