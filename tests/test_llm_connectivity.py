"""验证 LLM 调用层连通性"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm_client import create_client


async def test_model(model: str):
    print(f"\n{'='*50}")
    print(f"测试模型: {model}")
    print('='*50)
    try:
        client = create_client(model=model, system_prompt="用一句话回答")
        text, usage = await client.chat("1+1等于几？")
        print(f"响应: {text[:200]}")
        if usage:
            print(f"Token: 输入={usage.prompt_tokens} 输出={usage.completion_tokens} 总计={usage.total_tokens}")
        print("✅ 通过")
    except Exception as e:
        print(f"❌ 失败: {e}")


async def main():
    models = ["gemini-3.1-pro"]

    # 可选：取消注释测试其他模型
    # models.append("deepseek-v3.2")
    # models.append("glm-4.7")
    # models.append("qwen-max")

    for model in models:
        await test_model(model)


if __name__ == "__main__":
    asyncio.run(main())
