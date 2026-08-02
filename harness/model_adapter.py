"""Provider-neutral model contract backed by DeepSeek Responses."""

from __future__ import annotations

import copy
import json
import time
from typing import Any, AsyncIterator, Protocol

from harness.models import FunctionCall, ModelEvent, ModelRequest, ModelTurn
from harness.tools.base import ToolSpec
from utils.llm_client import DeepSeekResponsesClient, responses_usage


class ModelAdapter(Protocol):
    async def complete(self, request: ModelRequest) -> ModelTurn: ...

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...


def responses_tool(spec: ToolSpec) -> dict[str, Any]:
    parameters = copy.deepcopy(spec.parameters)
    properties = parameters.setdefault("properties", {})
    if "summary" in properties:
        raise ValueError(f"tool {spec.name} reserves the parameter name 'summary'")
    properties["summary"] = {
        "type": "string",
        "description": "给用户展示的一句话步骤旁白，不包含工具名等内部术语",
    }
    required = list(parameters.get("required", []))
    if "summary" not in required:
        required.append("summary")
    parameters["required"] = required
    parameters["additionalProperties"] = False
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": parameters,
        "strict": True,
    }


def responses_tools(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [responses_tool(spec) for spec in specs]


def _serialize_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return copy.deepcopy(item)
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True, mode="json")
    raise TypeError(f"unsupported Responses output item: {type(item).__name__}")


def _reasoning_text(output: list[Any]) -> str:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) != "reasoning":
            continue
        for content in getattr(item, "content", None) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "".join(parts)


def _message_text(output: list[Any], phase: str | None) -> str:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        item_phase = getattr(item, "phase", None)
        if phase == "commentary":
            if item_phase != "commentary":
                continue
        elif item_phase == "commentary":
            continue
        for content in getattr(item, "content", None) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "".join(parts)


def _normalize_response(
    response: Any,
    model: str,
    latency_ms: float = 0.0,
    provider_retries: list[dict[str, Any]] | None = None,
) -> ModelTurn:
    output = list(getattr(response, "output", None) or [])
    output_text = _message_text(output, None)
    commentary = _message_text(output, "commentary")
    has_commentary_message = any(
        getattr(item, "type", None) == "message"
        and getattr(item, "phase", None) == "commentary"
        for item in output
    )
    if not output_text and not has_commentary_message:
        output_text = getattr(response, "output_text", "") or ""
    calls: list[FunctionCall] = []
    errors: list[str] = []
    response_status = getattr(response, "status", "") or ""
    if response_status not in ("", "completed"):
        errors.append(f"response status is {response_status}")
    for item in output:
        if getattr(item, "type", None) != "function_call":
            continue
        call_id = getattr(item, "call_id", "") or ""
        name = getattr(item, "name", "") or ""
        raw_arguments = getattr(item, "arguments", "") or ""
        if not call_id:
            errors.append("function call missing call_id")
            continue
        if not name:
            errors.append(f"function call {call_id} missing name")
            continue
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, json.JSONDecodeError):
            errors.append(f"function call {call_id} arguments are not valid JSON")
            continue
        if not isinstance(arguments, dict):
            errors.append(f"function call {call_id} arguments must be an object")
            continue
        summary = arguments.pop("summary", None)
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"function call {call_id} missing non-empty summary")
            continue
        calls.append(FunctionCall(
            call_id=call_id,
            name=name,
            arguments=arguments,
            summary=summary.strip(),
            raw_arguments=raw_arguments,
        ))
    return ModelTurn(
        output_text=output_text,
        commentary=commentary,
        function_calls=calls,
        reasoning=_reasoning_text(output),
        usage=responses_usage(response, model, latency_ms),
        response_id=getattr(response, "id", "") or "",
        response_items=[_serialize_item(item) for item in output],
        provider_retries=list(provider_retries or []),
        protocol_error="; ".join(errors),
    )


class ResponsesModelAdapter:
    def __init__(self, client: DeepSeekResponsesClient):
        self.client = client

    async def complete(self, request: ModelRequest) -> ModelTurn:
        started = time.monotonic()
        provider_retries: list[dict[str, Any]] = []
        response = await self.client.create(
            input=request.input_items,
            instructions=request.instructions,
            tools=responses_tools(request.tools),
            temperature=request.temperature,
            parallel_tool_calls=request.parallel_tool_calls,
            on_retry=provider_retries.append,
        )
        return _normalize_response(
            response,
            self.client.model,
            (time.monotonic() - started) * 1000,
            provider_retries,
        )

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        started = time.monotonic()
        provider_retries: list[dict[str, Any]] = []
        stream = await self.client.create(
            input=request.input_items,
            instructions=request.instructions,
            tools=responses_tools(request.tools),
            temperature=request.temperature,
            parallel_tool_calls=request.parallel_tool_calls,
            stream=True,
            on_retry=provider_retries.append,
        )
        completed = False
        async for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.reasoning_text.delta":
                yield ModelEvent(kind="reasoning_delta", text=getattr(event, "delta", "") or "")
            elif event_type == "response.output_text.delta":
                yield ModelEvent(kind="output_text_delta", text=getattr(event, "delta", "") or "")
            elif event_type == "response.completed":
                completed = True
                turn = _normalize_response(
                    event.response,
                    self.client.model,
                    (time.monotonic() - started) * 1000,
                    provider_retries,
                )
                yield ModelEvent(kind="completed", turn=turn)
        if not completed:
            raise RuntimeError("Responses stream ended without response.completed")
