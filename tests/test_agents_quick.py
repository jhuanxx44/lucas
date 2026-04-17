"""快速验证：用小 thinking budget 测试完整 Manager 流程"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Monkey-patch researcher 的 thinking_budget 为 0
import agents.researcher as _r
_orig_run = _r.run_researcher

async def _fast_run(config, task, prior_results=None):
    from utils.llm_client import create_client
    from agents.models import ResearchResult
    client = create_client(model=config.model, system_prompt=config.system_prompt, enable_thinking=False)
    parts = [f"## 用户问题\n{task.question}"]
    if task.instruction:
        parts.append(f"## Manager 指令\n{task.instruction}")
    prompt = "\n\n".join(parts) + "\n\n请用两三句话简要回答。"
    print(f"  [调用 {config.name}]", flush=True)
    text, usage = await client.chat(prompt=prompt, temperature=0.7, thinking_budget=0)
    return ResearchResult(
        researcher_id=config.id, researcher_name=config.name,
        model=config.model, content=text, token_usage=usage,
    )

_r.run_researcher = _fast_run

from agents.config import load_config
from agents.manager import Manager
from utils.llm_client import create_client


async def main():
    config = load_config()
    manager = Manager(config)
    manager.client = create_client(
        model=config.manager.model,
        system_prompt=config.manager.system_prompt,
        enable_thinking=False,
    )

    def on_status(msg):
        print(f"  → {msg}", flush=True)

    print("开始测试...", flush=True)
    report = await manager.analyze("用一句话评价宁德时代", on_status=on_status)

    print(f"\n研究员数量: {len(report.results)}", flush=True)
    for r in report.results:
        tokens = r.token_usage.total_tokens if r.token_usage else "N/A"
        print(f"  • {r.researcher_name}: {len(r.content)} 字, tokens={tokens}", flush=True)

    print(f"\n综合分析:\n{report.synthesis[:500]}", flush=True)
    print(f"\n总 token: {report.total_tokens}", flush=True)
    print("\n✅ 通过", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
