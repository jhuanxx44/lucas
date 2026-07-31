"""验证 LLM 调用层连通性"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm_client import create_client


async def check_model(model: str):
    """官网 Responses 最小连通性探针。[llm-weight: light]"""
    print(f"\n{'='*50}")
    print(f"测试模型: {model}")
    print('='*50)
    try:
        client = create_client(model=model, instructions="用一句话回答")
        text, usage = await client.generate_text("1+1等于几？")
        print(f"响应: {text[:200]}")
        if usage:
            print(f"Token: 输入={usage.prompt_tokens} 输出={usage.completion_tokens} 总计={usage.total_tokens}")
        print("✅ 通过")
    except Exception as e:
        print(f"❌ 失败: {e}")


async def main():
    await check_model("deepseek-v4-flash")


if __name__ == "__main__":
    asyncio.run(main())
