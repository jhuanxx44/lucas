#!/usr/bin/env python3
"""Lucas 多 Agent 专家系统 CLI"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.config import load_config
from agents.manager import Manager


def print_status(msg: str):
    print(f"  → {msg}")


def print_report(report):
    print()
    # 如果有多个研究员，先显示各自的分析
    if len(report.results) > 1:
        for r in report.results:
            print(f"{'─'*60}")
            tokens = r.token_usage.total_tokens if r.token_usage else "N/A"
            print(f"📊 {r.researcher_name}（{r.model}）| tokens: {tokens}")
            print(f"{'─'*60}")
            print(r.content)
            print()

        print(f"{'═'*60}")
        print("📋 Manager 综合分析")
        print(f"{'═'*60}")

    print(report.synthesis)
    print(f"\n  [总 token: {report.total_tokens}]")


def print_researchers(config):
    print("\n当前研究员配置：")
    for r in config.researchers:
        print(f"  • {r.name} (id={r.id}, model={r.model})")
        print(f"    擅长: {r.expertise}")
    print()


async def main():
    config = load_config()
    manager = Manager(config)

    print("Lucas 多 Agent 专家系统")
    print(f"Manager: {config.manager.model}")
    print(f"研究员: {', '.join(r.name for r in config.researchers)}")
    print("输入问题开始分析，/researchers 查看研究员，/quit 退出\n")

    while True:
        try:
            user_input = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("再见！")
            break
        elif user_input == "/researchers":
            print_researchers(config)
            continue
        elif user_input.startswith("/"):
            print(f"未知命令: {user_input}")
            continue

        try:
            report = await manager.analyze(user_input, on_status=print_status)
            print_report(report)
        except Exception as e:
            print(f"\n❌ 分析出错: {e}")

        print()


if __name__ == "__main__":
    asyncio.run(main())
