from harness.config import (
    DEFAULT_ALLOWED_TOOLS,
    DEFAULT_MODEL,
    build_single_system_prompt,
    load_agent_config,
    load_wiki_config,
)


def test_load_agent_config_reads_lucas_yaml(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text(
        """
runtime:
  agent_mode: single

single_agent:
  name: TestAgent
  model: deepseek-custom-1
  temperature: 0.7
  max_steps: 7
  allowed_tools: [read_file, search]
""".strip(),
        encoding="utf-8",
    )

    config = load_agent_config(config_file)

    assert config.model == "deepseek-custom-1"
    assert config.temperature == 0.7
    assert config.max_steps == 7
    assert config.allowed_tools == ["read_file", "search"]
    assert config.name == "TestAgent"
    assert config.agent_mode == "single"
    assert not hasattr(config, "provider")


def test_model_falls_back_to_deepseek_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-env-model")
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text("single_agent: {}\nwiki: {}\n", encoding="utf-8")

    assert load_agent_config(config_file).model == "deepseek-env-model"
    assert load_wiki_config(config_file).model == "deepseek-env-model"


def test_load_agent_config_defaults_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_MODEL", "  ")

    config = load_agent_config(tmp_path / "nonexistent.yaml")

    assert config.model == DEFAULT_MODEL
    assert config.temperature == 0.0
    assert config.max_steps == 10
    assert config.allowed_tools == DEFAULT_ALLOWED_TOOLS
    assert config.agent_mode == "single"


def test_agent_config_context_compression_level_defaults_to_max(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text("single_agent: {}\n", encoding="utf-8")

    assert load_agent_config(config_file).context_compression_level == 2


def test_agent_config_context_compression_level_override(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text(
        "single_agent:\n  context_compression_level: 1\n",
        encoding="utf-8",
    )

    assert load_agent_config(config_file).context_compression_level == 1


def test_load_wiki_config_reads_domain_and_model(tmp_path):
    config_file = tmp_path / "lucas.yaml"
    config_file.write_text(
        """
wiki:
  model: deepseek-wiki
  industries: [电子, 新能源]
  index_title: 测试索引
  source_max_chars: 1234
""".strip(),
        encoding="utf-8",
    )

    config = load_wiki_config(config_file)

    assert config.model == "deepseek-wiki"
    assert config.industries == ["电子", "新能源"]
    assert config.index_title == "测试索引"
    assert config.source_max_chars == 1234
    assert not hasattr(config, "provider")


def test_repo_root_lucas_yaml_loads_explicit_model():
    config = load_agent_config()
    wiki_config = load_wiki_config()

    assert config.model == "deepseek-v4-flash"
    assert wiki_config.model == "deepseek-v4-flash"
    assert config.temperature == 0.0
    assert set(config.allowed_tools) == set(DEFAULT_ALLOWED_TOOLS)


def test_single_system_prompt_renders_only_date():
    prompt = build_single_system_prompt(current_date="2026-07-24")

    assert "完整、具体、细致的回答" in prompt
    assert "不要只给结论、只写一两句话" in prompt
    assert "事实依据、分析、关键假设、不确定性、风险和可行的下一步" in prompt
    assert "简单事实题可以简洁" in prompt
    assert "2026-07-24" in prompt
    assert "## 可用工具" not in prompt
    assert "{tools_desc}" not in prompt


def test_single_system_prompt_uses_observable_retrieval_triggers():
    prompt = build_single_system_prompt(current_date="2026-07-24")

    assert "能用工具查证就查，只在明确不需要查时才跳过" in prompt
    assert "其他所有问题" in prompt
    assert "查找公告、招股书或监管文件原文时" in prompt
    assert '凡涉及"最新""近期""今年"等时间判断' in prompt
    assert "把上一轮结论恢复为待验证" in prompt
    assert "非官方镜像必须明确标注" in prompt
