#!/usr/bin/env python3
"""Lucas 多 Agent 专家系统 CLI"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.status import Status

from agents.config import load_config
from agents.manager import Manager

console = Console()

RESEARCHER_STYLES = {
    "fundamental": ("blue", "📊"),
    "technical": ("green", "📈"),
    "macro": ("yellow", "🌐"),
}


class StatusPrinter:
    """on_status 回调，用 rich 渲染状态信息"""

    def __init__(self):
        self._status: Status | None = None

    def __call__(self, msg: str):
        if msg.startswith("🔧"):
            self._stop_spinner()
            console.print(f"    [yellow]{msg}[/]")
            return

        if msg.startswith("  ✓") or msg.startswith("  ✗"):
            self._stop_spinner()
            icon = "[green]✓[/]" if "✓" in msg else "[red]✗[/]"
            console.print(f"    {icon} {msg.lstrip(' ✓✗ ')}")
            return

        if msg.startswith("✓"):
            self._stop_spinner()
            console.print(f"  [green]✓[/] {msg[2:]}")
            return

        if "创建" in msg or "更新" in msg:
            self._stop_spinner()
            console.print(f"    [dim]{msg.strip()}[/]")
            return

        self._stop_spinner()
        self._status = console.status(f"[bold cyan]{msg}[/]", spinner="dots")
        self._status.start()

    def _stop_spinner(self):
        if self._status:
            self._status.stop()
            self._status = None

    def done(self):
        self._stop_spinner()


def print_report(report):
    console.print()

    if len(report.results) > 1:
        for r in report.results:
            style, icon = RESEARCHER_STYLES.get(r.researcher_id, ("white", "📋"))
            tokens = r.token_usage.total_tokens if r.token_usage else "N/A"
            subtitle = f"{r.model} · {tokens} tokens"
            panel = Panel(
                Markdown(r.content),
                title=f"{icon} {r.researcher_name}",
                subtitle=f"[dim]{subtitle}[/]",
                border_style=style,
                padding=(1, 2),
            )
            console.print(panel)

        console.print()
        panel = Panel(
            Markdown(report.synthesis),
            title="🧠 Lucas 综合分析",
            border_style="bold gold1",
            padding=(1, 2),
        )
        console.print(panel)
    else:
        console.print(Markdown(report.synthesis))

    console.print(f"  [dim]tokens: {report.total_tokens}[/]\n")


def print_researchers(config):
    lines = []
    for r in config.researchers:
        _, icon = RESEARCHER_STYLES.get(r.id, ("white", "📋"))
        lines.append(f"{icon} [bold]{r.name}[/] ({r.id}, {r.model})")
        lines.append(f"   擅长: [dim]{r.expertise}[/]")
    console.print(Panel("\n".join(lines), title="研究员配置", border_style="cyan"))


def print_banner(config):
    researcher_names = " · ".join(r.name for r in config.researchers)
    banner = Text()
    banner.append("🧠 Lucas", style="bold bright_white")
    banner.append(" · A股智能分析系统\n", style="dim")
    banner.append(f"   模型: {config.manager.model}\n", style="dim")
    banner.append(f"   研究员: {researcher_names}", style="dim")
    console.print(Panel(banner, border_style="bright_blue", padding=(0, 1)))
    console.print("[dim]输入问题开始分析  /researchers 查看研究员  /quit 退出[/]\n")


async def main():
    config = load_config()
    manager = Manager(config)

    print_banner(config)

    while True:
        try:
            user_input = console.input("[bold bright_cyan]Lucas>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见 👋[/]")
            break

        if not user_input:
            continue

        if user_input in ("/quit", "exit", "quit"):
            console.print("[dim]再见 👋[/]")
            break
        elif user_input == "/researchers":
            print_researchers(config)
            continue
        elif user_input.startswith("/"):
            console.print(f"[red]未知命令: {user_input}[/]")
            continue

        status_printer = StatusPrinter()
        try:
            report = await manager.analyze(user_input, on_status=status_printer)
            status_printer.done()
            print_report(report)
        except Exception as e:
            status_printer.done()
            console.print(f"\n[bold red]✗ 分析出错:[/] {e}")

        console.print()


if __name__ == "__main__":
    asyncio.run(main())
