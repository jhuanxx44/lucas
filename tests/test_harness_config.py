from harness.config import DEFAULT_ALLOWED_TOOLS, load_agent_config
from utils.providers import get_provider_model


def test_load_agent_config_reads_lucas_yaml(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text(
        """
runtime:
  agent_mode: single

single_agent:
  name: TestAgent
  provider: deepseek
  temperature: 0.7
  max_steps: 7
  allowed_tools: [read_file, search]
""".strip(),
        encoding="utf-8",
    )

    config = load_agent_config(config_file)

    assert config.provider == "deepseek"
    assert config.model == get_provider_model("deepseek")
    assert config.temperature == 0.7
    assert config.max_steps == 7
    assert config.allowed_tools == ["read_file", "search"]
    assert config.name == "TestAgent"
    assert config.agent_mode == "single"


def test_load_agent_config_model_override(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text(
        "single_agent:\n  provider: deepseek\n  model: deepseek-custom-1\n",
        encoding="utf-8",
    )

    config = load_agent_config(config_file)

    assert config.model == "deepseek-custom-1"


def test_load_agent_config_defaults_when_file_missing(tmp_path):
    config = load_agent_config(tmp_path / "nonexistent.yaml")

    assert config.provider == "deepseek"
    assert config.model == get_provider_model("deepseek")
    assert config.temperature == 0.0
    assert config.max_steps == 10
    assert config.allowed_tools == DEFAULT_ALLOWED_TOOLS
    assert config.agent_mode == "single"


def test_repo_root_lucas_yaml_loads():
    """仓库根的 lucas.yaml 是有效配置，关键字段与默认允许工具集一致"""
    config = load_agent_config()

    assert config.provider == "deepseek"
    assert config.model == get_provider_model("deepseek")
    assert config.temperature == 0.0
    assert set(config.allowed_tools) == set(DEFAULT_ALLOWED_TOOLS)


def test_product_chat_intersects_config_with_registered_tools():
    from server.services.agent_stream import _resolve_chat_tool_names

    # 研究工具 + filesystem 工具均已注册；未知工具被过滤，保持配置顺序。
    assert _resolve_chat_tool_names([
        "read_file", "wiki_recall", "unknown", "web_search",
    ]) == ["read_file", "wiki_recall", "web_search"]


def test_chat_write_guard_allows_wiki_blocks_elsewhere(tmp_path):
    """聊天写工具只能落在 wiki/：raw/、根目录、越界路径一律拒绝。"""
    from server.services.agent_stream import _WIKI_WRITE_FILE_SPEC

    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw").mkdir()
    handler = _WIKI_WRITE_FILE_SPEC.handler

    ok = handler(tmp_path, {"path": "wiki/companies/x.md", "content": "hi"})
    assert ok.status == "ok"
    assert (tmp_path / "wiki/companies/x.md").read_text() == "hi"

    for bad in ("raw/x.md", "notes.md", "../escape.md", "/etc/passwd"):
        denied = handler(tmp_path, {"path": bad, "content": "x"})
        assert denied.status == "denied", bad
        assert denied.error_code == "write_scope", bad
