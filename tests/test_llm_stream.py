"""DeepSeek Responses transport and adapter tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.model_adapter import ResponsesModelAdapter, responses_tool
from harness.models import ModelRequest
from harness.tools.base import ToolSpec
from utils.llm_client import DeepSeekResponsesClient, create_client


def _tool_spec() -> ToolSpec:
    return ToolSpec(
        name="lookup",
        description="lookup a value",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        handler=lambda workspace, args: None,
    )


class _Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return dict(self.dump)


def _usage(input_tokens=10, output_tokens=6, reasoning_tokens=2):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )


def _deepseek_style_usage(prompt_tokens=1200, completion_tokens=300, reasoning_tokens=80):
    # DeepSeek Chat Completions 风格：prompt_tokens/completion_tokens 命名，
    # reasoning 挂在 completion_tokens_details 下
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )


def test_responses_usage_parses_both_naming_conventions():
    from utils.llm_client import responses_usage

    openai_style = responses_usage(SimpleNamespace(usage=_usage()), model="m")
    assert openai_style.prompt_tokens == 10
    assert openai_style.completion_tokens == 4
    assert openai_style.thinking_tokens == 2
    assert openai_style.total_tokens == 16

    deepseek_style = responses_usage(
        SimpleNamespace(usage=_deepseek_style_usage()), model="m"
    )
    assert deepseek_style.prompt_tokens == 1200
    assert deepseek_style.completion_tokens == 300
    assert deepseek_style.thinking_tokens == 80
    assert deepseek_style.total_tokens == 1500

    dict_style = responses_usage(SimpleNamespace(usage={
        "input_tokens": 7,
        "output_tokens": 5,
        "output_tokens_details": {"reasoning_tokens": 2},
        "total_tokens": 12,
    }), model="m")
    assert dict_style.prompt_tokens == 7
    assert dict_style.completion_tokens == 3
    assert dict_style.total_tokens == 12


def test_create_client_uses_only_deepseek_responses_configuration():
    env = {
        "DEEPSEEK_API_KEY": "deepseek-key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
    }
    with patch.dict("os.environ", env, clear=True), patch("openai.AsyncOpenAI") as openai:
        client = create_client(instructions="system")

    assert isinstance(client, DeepSeekResponsesClient)
    assert client.model == "deepseek-v4-flash"
    assert client.instructions == "system"
    openai.assert_called_once_with(api_key="deepseek-key", base_url="https://api.deepseek.com")


@pytest.mark.parametrize("base_url", [
    "https://proxy.example/v1",
    "http://api.deepseek.com",
])
def test_client_rejects_non_official_endpoint(base_url):
    env = {
        "DEEPSEEK_API_KEY": "deepseek-key",
        "DEEPSEEK_BASE_URL": base_url,
    }
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="DeepSeek 官网"):
            create_client()


def test_client_uses_default_model_when_environment_value_is_blank():
    env = {
        "DEEPSEEK_API_KEY": "deepseek-key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_MODEL": "   ",
    }
    with patch.dict("os.environ", env, clear=True), patch("openai.AsyncOpenAI"):
        client = create_client()

    assert client.model == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_generate_text_uses_responses_and_normalizes_usage():
    response = SimpleNamespace(output_text="OK", usage=_usage())
    env = {
        "DEEPSEEK_API_KEY": "key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
    with patch.dict("os.environ", env, clear=True), patch("openai.AsyncOpenAI"):
        client = create_client(instructions="system")
        client._client.responses.create = AsyncMock(return_value=response)
        text, usage = await client.generate_text(
            "prompt", response_mime_type="application/json", temperature=0.2
        )

    assert text == "OK"
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 4
    assert usage.thinking_tokens == 2
    client._client.responses.create.assert_awaited_once_with(
        model="deepseek-v4-flash",
        input="prompt",
        max_output_tokens=65536,
        temperature=0.2,
        stream=False,
        instructions="system",
        text={"format": {"type": "json_object"}},
    )


@pytest.mark.asyncio
async def test_client_retries_transient_responses_error_without_changing_request():
    response = SimpleNamespace(output_text="OK", usage=_usage())
    retries = []
    env = {
        "DEEPSEEK_API_KEY": "key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
    with (
        patch.dict("os.environ", env, clear=True),
        patch("openai.AsyncOpenAI"),
        patch("utils.llm_client.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        client = create_client()
        client._client.responses.create = AsyncMock(
            side_effect=[RuntimeError("503 service unavailable"), response]
        )
        result = await client.create(input="hello", on_retry=retries.append)

    assert result is response
    assert client._client.responses.create.await_count == 2
    assert client._client.responses.create.await_args_list[0] == (
        client._client.responses.create.await_args_list[1]
    )
    assert retries == [{
        "retry_count": 1,
        "next_attempt": 2,
        "delay_seconds": 3,
        "error_type": "RuntimeError",
        "status_code": None,
    }]
    sleep.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_client_does_not_retry_non_transient_responses_error():
    env = {
        "DEEPSEEK_API_KEY": "key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
    with (
        patch.dict("os.environ", env, clear=True),
        patch("openai.AsyncOpenAI"),
        patch("utils.llm_client.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        client = create_client()
        client._client.responses.create = AsyncMock(side_effect=ValueError("bad request"))
        with pytest.raises(ValueError, match="bad request"):
            await client.create(input="hello")

    client._client.responses.create.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_sends_parallel_tool_calls_flag_with_tools():
    env = {
        "DEEPSEEK_API_KEY": "key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
    tools = [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}]
    with patch.dict("os.environ", env, clear=True), patch("openai.AsyncOpenAI"):
        client = create_client()
        client._client.responses.create = AsyncMock(
            return_value=SimpleNamespace(output_text="", usage=None)
        )
        await client.create(input="hello", tools=tools, parallel_tool_calls=False)

    client._client.responses.create.assert_awaited_once_with(
        model="deepseek-v4-flash",
        input="hello",
        max_output_tokens=65536,
        temperature=0.0,
        stream=False,
        tools=tools,
        tool_choice="auto",
        parallel_tool_calls=False,
    )


@pytest.mark.asyncio
async def test_adapter_passes_parallel_tool_calls_through_request():
    response = SimpleNamespace(
        id="resp_1", output=[], output_text="", status="completed", usage=_usage()
    )
    client = MagicMock(model="deepseek-v4-flash")
    client.create = AsyncMock(return_value=response)

    await ResponsesModelAdapter(client).complete(ModelRequest(
        instructions="system",
        input_items=[{"role": "user", "content": "lookup"}],
        tools=[_tool_spec()],
        parallel_tool_calls=False,
    ))

    assert client.create.await_args.kwargs["parallel_tool_calls"] is False


def test_responses_tool_injects_required_summary_without_mutating_business_schema():
    spec = _tool_spec()

    value = responses_tool(spec)

    assert value["type"] == "function"
    assert value["strict"] is True
    assert set(value["parameters"]["required"]) == {"key", "summary"}
    assert "summary" in value["parameters"]["properties"]
    assert "summary" not in spec.parameters["properties"]


@pytest.mark.asyncio
async def test_adapter_normalizes_native_function_call_and_preserves_output_items():
    reasoning = _Item(
        type="reasoning",
        content=[SimpleNamespace(text="先查")],
        dump={"type": "reasoning", "id": "r1", "content": []},
    )
    call = _Item(
        type="function_call",
        call_id="call_1",
        name="lookup",
        arguments='{"key":"alpha","summary":"先查一下"}',
        dump={
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": '{"key":"alpha","summary":"先查一下"}',
        },
    )
    response = SimpleNamespace(
        id="resp_1",
        output=[reasoning, call],
        output_text="",
        usage=_usage(),
    )
    client = MagicMock(model="deepseek-v4-flash")
    client.create = AsyncMock(return_value=response)
    adapter = ResponsesModelAdapter(client)

    turn = await adapter.complete(ModelRequest(
        instructions="system",
        input_items=[{"role": "user", "content": "lookup"}],
        tools=[_tool_spec()],
        temperature=0,
    ))

    assert turn.response_id == "resp_1"
    assert turn.reasoning == "先查"
    assert turn.output_text == ""
    assert turn.protocol_error == ""
    assert len(turn.function_calls) == 1
    assert turn.function_calls[0].call_id == "call_1"
    assert turn.function_calls[0].arguments == {"key": "alpha"}
    assert turn.function_calls[0].summary == "先查一下"
    assert [item["type"] for item in turn.response_items] == ["reasoning", "function_call"]


@pytest.mark.asyncio
async def test_adapter_separates_commentary_from_final_output_during_tool_call():
    commentary = _Item(
        type="message",
        phase="commentary",
        content=[SimpleNamespace(text="我先确认现有配置。")],
        dump={"type": "message", "phase": "commentary", "content": []},
    )
    call = _Item(
        type="function_call",
        call_id="call_1",
        name="lookup",
        arguments='{"key":"alpha","summary":"确认现有配置"}',
        dump={
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": '{"key":"alpha","summary":"确认现有配置"}',
        },
    )
    response = SimpleNamespace(
        id="resp_commentary",
        output=[commentary, call],
        output_text="我先确认现有配置。",
        usage=_usage(),
    )
    client = MagicMock(model="deepseek-v4-flash")
    client.create = AsyncMock(return_value=response)

    turn = await ResponsesModelAdapter(client).complete(ModelRequest(
        instructions="system",
        input_items=[{"role": "user", "content": "lookup"}],
        tools=[_tool_spec()],
    ))

    assert turn.output_text == ""
    assert turn.commentary == "我先确认现有配置。"
    assert len(turn.function_calls) == 1


@pytest.mark.asyncio
async def test_adapter_rejects_incomplete_response_as_protocol_error():
    message = _Item(
        type="message",
        content=[SimpleNamespace(text="未完成的答案")],
        dump={"type": "message", "content": []},
    )
    response = SimpleNamespace(
        id="resp_incomplete",
        status="incomplete",
        output=[message],
        output_text="未完成的答案",
        usage=_usage(),
    )
    client = MagicMock(model="deepseek-v4-flash")
    client.create = AsyncMock(return_value=response)

    turn = await ResponsesModelAdapter(client).complete(ModelRequest(
        instructions="system",
        input_items=[{"role": "user", "content": "answer"}],
        tools=[],
    ))

    assert turn.output_text == "未完成的答案"
    assert turn.protocol_error == "response status is incomplete"


@pytest.mark.asyncio
async def test_adapter_streams_reasoning_text_and_completed_turn():
    message = _Item(type="message", dump={"type": "message", "id": "m1"})
    response = SimpleNamespace(
        id="resp_2",
        output=[message],
        output_text="答案",
        usage=_usage(),
    )

    async def events():
        yield SimpleNamespace(type="response.reasoning_text.delta", delta="思考")
        yield SimpleNamespace(type="response.output_text.delta", delta="答案")
        yield SimpleNamespace(type="response.completed", response=response)

    client = MagicMock(model="deepseek-v4-flash")
    client.create = AsyncMock(return_value=events())
    adapter = ResponsesModelAdapter(client)
    request = ModelRequest(
        instructions="system",
        input_items=[{"role": "user", "content": "answer"}],
        tools=[],
    )

    result = [event async for event in adapter.complete_stream(request)]

    assert [(event.kind, event.text) for event in result[:2]] == [
        ("reasoning_delta", "思考"),
        ("output_text_delta", "答案"),
    ]
    assert result[-1].kind == "completed"
    assert result[-1].turn.output_text == "答案"
