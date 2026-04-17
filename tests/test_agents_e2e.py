"""端到端测试：验证 Manager → Researcher 完整流程"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.config import load_config
from agents.manager import Manager


async def main():
    config = load_config()
    print(f"Manager: {config.manager.model}")
    print(f"研究员: {[r.name for r in config.researchers]}")

    manager = Manager(config)

    def on_status(msg):
        print(f"  → {msg}")

    report = await manager.analyze("简单分析一下宁德时代", on_status=on_status)

    print(f"\n{'='*60}")
    print(f"研究员数量: {len(report.results)}")
    for r in report.results:
        tokens = r.token_usage.total_tokens if r.token_usage else "N/A"
        print(f"  • {r.researcher_name} ({r.model}): {len(r.content)} 字, tokens={tokens}")

    print(f"\n综合分析 ({len(report.synthesis)} 字):")
    print(report.synthesis[:500])
    print(f"\n总 token: {report.total_tokens}")
    print("\n✅ 端到端测试通过")


if __name__ == "__main__":
    asyncio.run(main())
