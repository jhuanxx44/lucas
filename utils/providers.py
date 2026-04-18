"""
Provider 配置加载器
从 providers.yaml 读取模型提供商配置
"""
import os
import yaml
from pathlib import Path
from typing import Optional

_PROVIDERS_CONFIG_PATH = Path(__file__).parent.parent / "providers.yaml"
_providers_cache: Optional[dict] = None


def load_providers() -> dict:
    """加载 providers.yaml"""
    global _providers_cache
    if _providers_cache is None:
        with open(_PROVIDERS_CONFIG_PATH, "r", encoding="utf-8") as f:
            _providers_cache = yaml.safe_load(f)
    return _providers_cache


def get_provider_config(provider_name: str) -> dict:
    """获取指定 provider 的配置"""
    providers = load_providers()
    return providers["providers"][provider_name]


def get_provider_model(provider_name: str, model_override: Optional[str] = None) -> str:
    """
    获取 provider 对应的实际模型名

    Args:
        provider_name: provider 名（如 gemini, minimax）
        model_override: 可选的模型覆盖，不填则用 default_model
    """
    config = get_provider_config(provider_name)
    return model_override or config["default_model"]


def get_provider_api_config(provider_name: str) -> tuple[str, str]:
    """
    获取 provider 的 API 配置

    Returns:
        (api_key_env_var, base_url_env_var)
    """
    config = get_provider_config(provider_name)
    return config["api_key_env"], config["base_url_env"]


def resolve_env_vars(api_key_env: str, base_url_env: str) -> tuple[str, str]:
    """从环境变量名解析实际的值"""
    api_key = os.environ.get(api_key_env, "")
    base_url = os.environ.get(base_url_env, "")
    return api_key, base_url
