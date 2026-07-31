"""M3 Planner 实验：update_plan 工具 + SSE plan_update 事件 + plan_usage grader 测试"""
import asyncio
import json
from pathlib import Path

import pytest

from harness.models import FunctionCall, ModelRequest, ModelTurn, RunLimits
from harness.runner import AgentRunner, load_prompt_template
from harness.tools.base import ToolResult, ToolSpec
from harness.tools.generic.filesystem import READ_FILE_SPEC, LIST_FILES_SPEC
from harness.tools.generic.planning import UPDATE_PLAN_SPEC, _update_plan
from harness.tools.registry import ToolRuntime
from harness.trace import TraceRecorder, read_trace
from evals.harness.grader import _process_check

LIMITS = RunLimits(max_steps=8, timeout_seconds=30)


def _tool_turn(name: str, arguments: dict, call_id: str) -> ModelTurn:
    summary = f"执行 {name}"
    raw_arguments = json.dumps(
        {**arguments, "summary": summary},
        ensure_ascii=False,
    )
    return ModelTurn(
        function_calls=[FunctionCall(
            call_id=call_id,
            name=name,
            arguments=arguments,
            summary=summary,
        )],
        response_items=[{
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": raw_arguments,
        }],
    )


def _answer_turn(answer: str) -> ModelTurn:
    return ModelTurn(output_text=answer)


class FakeModel:
    def __init__(self, responses: list[ModelTurn]):
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelTurn:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return _answer_turn("fallback")


def _make_runner(tmp_path, model, specs=None):
    if specs is None:
        specs = [UPDATE_PLAN_SPEC, READ_FILE_SPEC, LIST_FILES_SPEC]
    tools = ToolRuntime(tmp_path, specs)
    template = load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "agent-loop.md"
    )
    return AgentRunner(model, tools, template)


def _trace(tmp_path, run_id="test-run") -> TraceRecorder:
    t = TraceRecorder(tmp_path / "trace.jsonl", run_id)
    t.record("run_started")
    return t


def test_agent_loop_prompt_uses_native_single_call_and_direct_json_rules():
    template = load_prompt_template(
        Path(__file__).resolve().parent.parent / "prompts" / "harness" / "agent-loop.md"
    )

    assert "最多只能包含一个 `function_call` item" in template
    assert "只输出可直接解析的 JSON" in template
    assert '"action"' not in template


# ===================== update_plan 工具单元测试 =====================

def test_update_plan_valid_input():
    """合法输入：三个不同状态的步骤"""
    result = _update_plan(Path("/tmp"), {
        "steps": [
            {"step": "搜索激光雷达公司", "status": "completed"},
            {"step": "阅读公司档案", "status": "in_progress"},
            {"step": "写对比报告", "status": "pending"},
        ]
    })
    assert result.ok
    assert "✅ 搜索激光雷达公司" in result.observation
    assert "🔵 阅读公司档案" in result.observation
    assert "⬜ 写对比报告" in result.observation
    assert result.observation.startswith("## 当前计划")


def test_update_plan_default_status():
    """不传 status 时默认 pending"""
    result = _update_plan(Path("/tmp"), {
        "steps": [{"step": "一个步骤"}]
    })
    assert result.ok
    assert "⬜ 一个步骤" in result.observation


def test_update_plan_invalid_status_defaults_to_pending():
    """非法 status 值 → 默认 pending"""
    result = _update_plan(Path("/tmp"), {
        "steps": [{"step": "测试", "status": "unknown_status"}]
    })
    assert result.ok
    assert "⬜ 测试" in result.observation


def test_update_plan_steps_not_list():
    """原生 schema 只接受 canonical steps 列表。"""
    result = _update_plan(Path("/tmp"), {"steps": "not_a_list"})
    assert result.status == "invalid_input"


def test_update_plan_step_not_dict():
    """原生 schema 的 steps 元素必须是对象。"""
    result = _update_plan(Path("/tmp"), {"steps": ["not a dict"]})
    assert result.status == "invalid_input"


def test_update_plan_missing_step_field():
    """step 缺少 step 字段 → 空字符串显示"""
    result = _update_plan(Path("/tmp"), {
        "steps": [{"status": "completed"}]
    })
    assert result.ok
    assert "✅ " in result.observation  # emoji + 空字符串


def test_update_plan_empty_steps():
    """空 steps 列表 → 只有标题"""
    result = _update_plan(Path("/tmp"), {"steps": []})
    assert result.ok
    assert result.observation == "## 当前计划"


# ===================== Runner 集成：update_plan 调用流程 =====================

async def test_runner_plan_then_read_then_answer(tmp_path):
    """模型先 update_plan，再 read_file，最后 answer"""
    (tmp_path / "data.txt").write_text("营收: 60.6亿元\n利润: 12.0亿元")
    model = FakeModel([
        _tool_turn("update_plan", {
            "steps": [{"step": "读取数据文件", "status": "in_progress"}]
        }, "call-plan"),
        _tool_turn("read_file", {"path": "data.txt"}, "call-read"),
        _answer_turn("完成"),
    ])
    trace = _trace(tmp_path, "plan-test")
    runner = _make_runner(tmp_path, model)
    result = await runner.run("汇总数据", ["update_plan", "read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"
    # plan observation 进入了后续上下文
    second_input = str(model.requests[1].input_items)
    assert "## 当前计划" in second_input
    assert "🔵 读取数据文件" in second_input
    # 数据内容进入了后续上下文
    assert "60.6" in str(model.requests[2].input_items)

    # trace 中有 tool_call_finished for update_plan
    events = read_trace(trace.path)
    tools_called = [
        e["data"]["tool"] for e in events
        if e["event"] == "tool_call_started"
    ]
    assert "update_plan" in tools_called
    assert "read_file" in tools_called


async def test_runner_plan_update_twice(tmp_path):
    """模型两次调用 update_plan 更新进度"""
    (tmp_path / "a.txt").write_text("a")
    model = FakeModel([
        _tool_turn("update_plan", {
            "steps": [
                {"step": "读 A", "status": "in_progress"},
                {"step": "读 B", "status": "pending"},
            ]
        }, "call-plan-1"),
        _tool_turn("read_file", {"path": "a.txt"}, "call-read"),
        _tool_turn("update_plan", {
            "steps": [
                {"step": "读 A", "status": "completed"},
                {"step": "读 B", "status": "in_progress"},
            ]
        }, "call-plan-2"),
        _answer_turn("完成"),
    ])
    trace = _trace(tmp_path, "plan-twice")
    runner = _make_runner(tmp_path, model)
    result = await runner.run("读文件", ["update_plan", "read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"
    events = read_trace(trace.path)
    plan_calls = [
        e["data"]["tool"] for e in events
        if e["event"] == "tool_call_started" and e["data"]["tool"] == "update_plan"
    ]
    assert len(plan_calls) == 2


# ===================== plan_usage grader 单元测试 =====================

def _make_trace_events(tools_called: list[str]) -> list[dict]:
    """造最小 trace events 用于 grader 测试"""
    events = [{"event": "run_started", "run_id": "test", "sequence": 1}]
    seq = 2
    for tool in tools_called:
        call_id = f"call-{seq}"
        events.append({
            "event": "tool_call_started", "sequence": seq, "run_id": "test",
            "data": {"tool_call_id": call_id, "tool": tool, "args": {}}
        })
        seq += 1
        events.append({
            "event": "tool_call_finished", "sequence": seq, "run_id": "test",
            "data": {"tool_call_id": call_id, "tool": tool}
        })
        seq += 1
    events.append({"event": "run_finished", "sequence": seq, "run_id": "test"})
    return events


def test_plan_usage_min_calls_pass():
    """min_calls=1，调了 2 次 → 通过"""
    events = _make_trace_events(["update_plan", "read_file", "update_plan"])
    result = _process_check({"type": "plan_usage", "min_calls": 1, "required": True}, events)
    assert result["passed"]
    assert "called 2 times" in result["detail"]


def test_plan_usage_min_calls_fail():
    """min_calls=1，调了 0 次 → 失败"""
    events = _make_trace_events(["read_file", "list_files"])
    result = _process_check({"type": "plan_usage", "min_calls": 1, "required": True}, events)
    assert not result["passed"]
    assert "called 0 times" in result["detail"]


def test_plan_usage_max_calls_pass():
    """max_calls=0 用于简单任务，没调用 → 通过"""
    events = _make_trace_events(["read_file"])
    result = _process_check({"type": "plan_usage", "max_calls": 0, "required": True}, events)
    assert result["passed"]


def test_plan_usage_max_calls_fail():
    """max_calls=0 用于简单任务，但调了 1 次 → 失败"""
    events = _make_trace_events(["update_plan", "read_file"])
    result = _process_check({"type": "plan_usage", "max_calls": 0, "required": True}, events)
    assert not result["passed"]


def test_plan_usage_min_max_range_pass():
    """min=1, max=3，调了 2 次 → 通过"""
    events = _make_trace_events(["update_plan", "read_file", "update_plan"])
    result = _process_check({"type": "plan_usage", "min_calls": 1, "max_calls": 3, "required": True}, events)
    assert result["passed"]


def test_plan_usage_min_max_range_fail_low():
    """min=1, max=3，调了 0 次 → 失败"""
    events = _make_trace_events(["read_file"])
    result = _process_check({"type": "plan_usage", "min_calls": 1, "max_calls": 3, "required": True}, events)
    assert not result["passed"]


def test_plan_usage_no_max_unlimited():
    """不设 max_calls → 不限上限，调 10 次仍通过"""
    events = _make_trace_events(["update_plan"] * 10)
    result = _process_check({"type": "plan_usage", "min_calls": 1, "required": True}, events)
    assert result["passed"]
    assert "max=None" in result["detail"]


# ===================== MULTI-01 全链路：FakeModel 模拟 + 真实 grader =====================

async def test_multi01_full_pipeline(tmp_path):
    """用 FakeModel 模拟 MULTI-01 的任务流程，验证 runner + grader 全链路"""
    # 造 MULTI-01 fixture
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2024-Q1.md").write_text("## Q1\n- 营收：12.5亿元\n- 净利润：2.1亿元\n")
    (reports / "2024-Q2.md").write_text("## Q2\n- 营收：14.2亿元\n- 净利润：2.8亿元\n")
    (reports / "2024-Q3.md").write_text("## Q3\n- 营收：15.8亿元\n- 净利润：3.2亿元\n")
    (reports / "2024-Q4.md").write_text("## Q4\n- 营收：18.1亿元\n- 净利润：3.9亿元\n")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "2023-annual.md").write_text("旧数据")

    # FakeModel：先 plan → 逐个读文件 → answer
    model = FakeModel([
        _tool_turn("update_plan", {
            "steps": [
                {"step": "列出 reports 目录", "status": "in_progress"},
                {"step": "读取 Q1-Q4 报告", "status": "pending"},
                {"step": "汇总计算结果", "status": "pending"},
            ]
        }, "call-plan"),
        _tool_turn("list_files", {"path": "reports"}, "call-list"),
        _tool_turn("read_file", {"path": "reports/2024-Q1.md"}, "call-q1"),
        _tool_turn("read_file", {"path": "reports/2024-Q2.md"}, "call-q2"),
        _tool_turn("read_file", {"path": "reports/2024-Q3.md"}, "call-q3"),
        _tool_turn("read_file", {"path": "reports/2024-Q4.md"}, "call-q4"),
        _answer_turn('{"total_revenue": 60.6, "total_profit": 12.0}'),
    ])

    trace = _trace(tmp_path, "multi01-test")
    runner = _make_runner(tmp_path, model)
    result = await runner.run(
        "收集四个季度数据并汇总",
        ["update_plan", "read_file", "list_files"],
        LIMITS,
        trace,
    )

    assert result.finish_reason == "completed"
    answer = json.loads(result.answer) if isinstance(result.answer, str) else result.answer
    assert answer["total_revenue"] == 60.6
    assert answer["total_profit"] == 12.0

    # 验证 plan_usage grader
    events = read_trace(trace.path)
    plan_check = _process_check(
        {"type": "plan_usage", "min_calls": 1, "required": True}, events
    )
    assert plan_check["passed"], f"plan_usage should pass: {plan_check['detail']}"

    # 验证 allowed_tools grader（不应包含无关工具）
    tools_check = _process_check(
        {"type": "allowed_tools", "tools": ["update_plan", "read_file", "list_files"], "required": True}, events
    )
    assert tools_check["passed"]


# ===================== UPDATE_PLAN_SPEC 元数据校验 =====================

def test_update_plan_spec_metadata():
    """验证 ToolSpec 的 name/description/parameters 完整性"""
    assert UPDATE_PLAN_SPEC.name == "update_plan"
    assert "仅当面对需要多步骤" in UPDATE_PLAN_SPEC.description
    assert "不要调用" in UPDATE_PLAN_SPEC.description
    assert "steps" in UPDATE_PLAN_SPEC.parameters["properties"]
    step_object = UPDATE_PLAN_SPEC.parameters["properties"]["steps"]["items"]
    assert "pending" in step_object["properties"]["status"]["enum"]
    assert callable(UPDATE_PLAN_SPEC.handler)


# ===================== 简单任务不应使用 plan（反面验证） =====================

async def test_simple_task_no_plan_needed(tmp_path):
    """简单读取任务，agent 不调用 update_plan 也应成功"""
    (tmp_path / "hello.txt").write_text("hello world")
    model = FakeModel([
        _tool_turn("read_file", {"path": "hello.txt"}, "call-read"),
        _answer_turn("hello world"),
    ])
    trace = _trace(tmp_path, "simple-test")
    runner = _make_runner(tmp_path, model)
    result = await runner.run("读文件", ["update_plan", "read_file"], LIMITS, trace)

    assert result.finish_reason == "completed"
    events = read_trace(trace.path)
    # 简单任务不应调用 update_plan（FakeModel 没给，所以确实没调）
    plan_check = _process_check(
        {"type": "plan_usage", "max_calls": 0, "required": True}, events
    )
    assert plan_check["passed"], f"simple task shouldn't use plan: {plan_check['detail']}"


def test_update_plan_string_elements_in_list():
    """不再兼容字符串步骤元素。"""
    result = _update_plan(Path("/tmp"), {
        "steps": ["第一步", "第二步"]
    })
    assert result.status == "invalid_input"
