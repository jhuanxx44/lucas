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
