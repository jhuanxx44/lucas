import pytest
from pathlib import Path

from harness.tools.base import ToolSpec
from harness.tools.business.stock import STOCK_KLINE_SPEC, STOCK_QUOTE_SPEC
from harness.tools.business.wiki import WIKI_RECALL_SPEC
from harness.tools.generic.filesystem import (
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    READ_FILE_SPEC,
    SEARCH_SPEC,
    WRITE_FILE_SPEC,
)
from harness.tools.generic.planning import UPDATE_PLAN_SPEC
from harness.tools.generic.web_search import WEB_SEARCH_SPEC
from harness.tools.registry import ToolRuntime


PRODUCTION_SPECS = [
    READ_FILE_SPEC,
    APPLY_PATCH_SPEC,
    LIST_FILES_SPEC,
    WRITE_FILE_SPEC,
    SEARCH_SPEC,
    UPDATE_PLAN_SPEC,
    WEB_SEARCH_SPEC,
    WIKI_RECALL_SPEC,
    STOCK_QUOTE_SPEC,
    STOCK_KLINE_SPEC,
]


def _assert_object_schemas_are_closed(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
            assert isinstance(schema.get("properties"), dict)
            assert isinstance(schema.get("required"), list)
            assert set(schema["required"]) <= set(schema["properties"])
        for value in schema.values():
            _assert_object_schemas_are_closed(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_object_schemas_are_closed(value)


@pytest.mark.parametrize("spec", PRODUCTION_SPECS, ids=lambda spec: spec.name)
def test_production_tool_parameters_are_complete_closed_object_schemas(spec: ToolSpec):
    _assert_object_schemas_are_closed(spec.parameters)
    assert spec.parameters["type"] == "object"
    assert spec.description
    assert callable(spec.handler)


@pytest.mark.parametrize("spec", PRODUCTION_SPECS, ids=lambda spec: spec.name)
def test_step_summary_is_not_part_of_business_tool_parameters(spec: ToolSpec):
    assert "summary" not in spec.parameters["properties"]


@pytest.mark.parametrize(
    ("spec", "required"),
    [
        (READ_FILE_SPEC, {"path"}),
        (APPLY_PATCH_SPEC, {"path", "old", "new"}),
        (LIST_FILES_SPEC, set()),
        (WRITE_FILE_SPEC, {"path", "content"}),
        (SEARCH_SPEC, {"query"}),
        (UPDATE_PLAN_SPEC, {"steps"}),
        (WEB_SEARCH_SPEC, {"query"}),
        (WIKI_RECALL_SPEC, {"query"}),
        (STOCK_QUOTE_SPEC, {"code"}),
        (STOCK_KLINE_SPEC, {"code"}),
    ],
    ids=lambda value: value.name if isinstance(value, ToolSpec) else str(value),
)
def test_required_parameters_match_handler_contract(spec: ToolSpec, required: set[str]):
    assert set(spec.parameters["required"]) == required


def test_read_tools_marked_parallelizable_and_write_tools_not():
    write_names = {spec.name for spec in (WRITE_FILE_SPEC, APPLY_PATCH_SPEC, UPDATE_PLAN_SPEC)}
    for spec in PRODUCTION_SPECS:
        assert spec.parallelizable == (spec.name not in write_names)


def test_tool_spec_rejects_an_open_parameter_schema():
    with pytest.raises(ValueError, match="forbid additional properties"):
        ToolSpec(
            name="unsafe",
            description="test",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda workspace, args: None,
        )


@pytest.mark.asyncio
async def test_tool_runtime_rejects_missing_and_unknown_arguments(tmp_path: Path):
    runtime = ToolRuntime(tmp_path, [READ_FILE_SPEC])

    missing = await runtime.execute("read_file", {}, ["read_file"])
    unknown = await runtime.execute(
        "read_file", {"path": "x", "unexpected": True}, ["read_file"]
    )

    assert missing.error_code == "schema_validation"
    assert "missing required" in missing.observation
    assert unknown.error_code == "schema_validation"
    assert "unknown properties" in unknown.observation


@pytest.mark.asyncio
async def test_tool_runtime_validates_nested_plan_items(tmp_path: Path):
    runtime = ToolRuntime(tmp_path, [UPDATE_PLAN_SPEC])

    invalid = await runtime.execute(
        "update_plan",
        {"steps": [{"step": "do it", "status": "unknown"}]},
        ["update_plan"],
    )

    assert invalid.error_code == "schema_validation"
    assert "must be one of" in invalid.observation


@pytest.mark.asyncio
async def test_tool_runtime_normalizes_invalid_handler_return(tmp_path: Path):
    spec = ToolSpec(
        name="broken",
        description="broken handler",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=lambda workspace, args: None,
    )

    result = await ToolRuntime(tmp_path, [spec]).execute("broken", {}, ["broken"])

    assert result.status == "error"
    assert result.error_code == "handler_exception"
    assert "must return ToolResult" in result.observation
