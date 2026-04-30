"""
Lucas 工具系统：给 Manager 的文件系统操作能力

工具通过 JSON 协议调用：LLM 返回 {"action": "tool", "tool": "xxx", "args": {...}}，
Manager 执行后把结果追加到上下文让 LLM 继续决策。
"""
import glob
import json
import os

from workspace import Workspace

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_PROJECT_DIRS = {
    "prompts": _PROMPTS_DIR,
    "reviews": os.path.join(_PROJECT_ROOT, "reviews"),
    "logs": os.path.join(_PROJECT_ROOT, "logs"),
    "docs": os.path.join(_PROJECT_ROOT, "docs"),
}


class ToolKit:
    """per-request 工具集，绑定到用户的 workspace。"""

    def __init__(self, workspace: Workspace):
        self._ws = workspace

    def _resolve_path(self, rel_path: str) -> str | None:
        """将 LLM 给出的相对路径解析为绝对路径，拒绝越界。"""
        rel_path = rel_path.lstrip("/")
        top = rel_path.split("/")[0] if "/" in rel_path else rel_path

        project_dir = _PROJECT_DIRS.get(top)
        if project_dir:
            full = os.path.normpath(os.path.join(project_dir, *rel_path.split("/")[1:]))
            if not full.startswith(project_dir):
                return None
            return full

        root = self._ws.root
        full = os.path.normpath(os.path.join(root, rel_path))
        if not full.startswith(root):
            return None
        return full

    def list_files(self, path: str = "") -> str:
        target = self._resolve_path(path) if path else self._ws.root
        if not target or not os.path.isdir(target):
            return f"目录不存在或无权访问: {path}"
        entries = []
        try:
            for name in sorted(os.listdir(target)):
                if name.startswith("."):
                    continue
                full = os.path.join(target, name)
                if os.path.isdir(full):
                    count = len([f for f in os.listdir(full) if not f.startswith(".")])
                    entries.append(f"📁 {name}/ ({count} 项)")
                else:
                    size = os.path.getsize(full)
                    if size > 1024 * 1024:
                        size_str = f"{size / 1024 / 1024:.1f}MB"
                    elif size > 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size}B"
                    entries.append(f"📄 {name} ({size_str})")
        except PermissionError:
            return f"无权访问: {path}"
        if not entries:
            return f"目录为空: {path}"
        return "\n".join(entries)

    def read_file(self, path: str, max_chars: int = 4000, keyword: str = "") -> str:
        full = self._resolve_path(path)
        if not full:
            return f"路径无效或无权访问: {path}"
        if not os.path.isfile(full):
            return f"文件不存在: {path}"
        try:
            with open(full, "r", encoding="utf-8") as f:
                content = f.read()

            if keyword:
                lines = content.split("\n")
                keyword_lower = keyword.lower()
                hit_indices = [i for i, l in enumerate(lines) if keyword_lower in l.lower()]
                if not hit_indices:
                    return f"文件 {path} 中未找到关键词 '{keyword}'"
                segments = []
                for idx in hit_indices[:5]:
                    start = max(0, idx - 5)
                    end = min(len(lines), idx + 6)
                    segment = "\n".join(f"{start+j+1:4d}| {lines[start+j]}" for j in range(end - start))
                    segments.append(segment)
                result = f"--- {path} (关键词 '{keyword}' 命中 {len(hit_indices)} 处，显示前 {min(5, len(hit_indices))} 处上下文) ---\n\n"
                result += "\n\n...\n\n".join(segments)
                return result

            if len(content) > max_chars:
                content = content[:max_chars]
                return f"--- {path} (已截断至 {max_chars} 字符) ---\n{content}"
            return f"--- {path} ---\n{content}"
        except Exception as e:
            return f"读取失败: {path}: {e}"

    def search_files(self, keyword: str, scope: str = "all") -> str:
        search_dirs = []
        if scope in ("raw", "all"):
            search_dirs.append(self._ws.raw_root)
        if scope in ("wiki", "all"):
            search_dirs.append(self._ws.wiki_root)
        if scope in ("all",):
            search_dirs.append(self._ws.memory_root)

        matches = []
        keyword_lower = keyword.lower()
        for d in search_dirs:
            for md_path in glob.glob(os.path.join(d, "**", "*"), recursive=True):
                if not os.path.isfile(md_path):
                    continue
                rel = os.path.relpath(md_path, self._ws.root)

                if keyword_lower in rel.lower():
                    size = os.path.getsize(md_path)
                    size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                    matches.append(f"📄 {rel} ({size_str}) [文件名匹配]")
                    continue

                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except (UnicodeDecodeError, PermissionError):
                    continue

                hit_lines = []
                for i, line in enumerate(lines):
                    if keyword_lower in line.lower():
                        hit_lines.append(i)

                if hit_lines:
                    size = os.path.getsize(md_path)
                    size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                    snippets = []
                    for idx in hit_lines[:2]:
                        start = max(0, idx - 1)
                        end = min(len(lines), idx + 2)
                        snippet = "".join(lines[start:end]).strip()
                        if len(snippet) > 200:
                            snippet = snippet[:200] + "..."
                        snippets.append(f"  L{idx+1}: {snippet}")
                    matches.append(f"📄 {rel} ({size_str}) [内容匹配, {len(hit_lines)}处]\n" + "\n".join(snippets))

        if not matches:
            return f"未找到包含 '{keyword}' 的文件"
        return f"找到 {len(matches)} 个匹配:\n\n" + "\n\n".join(matches[:15])

    def recall(self, keyword: str, max_results: int = 5) -> str:
        conclusions_path = os.path.join(self._ws.memory_root, "conclusions.jsonl")
        if not os.path.isfile(conclusions_path):
            return "暂无历史分析记录"

        keyword_lower = keyword.lower()
        scored = []
        with open(conclusions_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = f"{rec.get('question', '')} {rec.get('conclusion', '')} {' '.join(rec.get('topics', []))}"
                if keyword_lower in text.lower():
                    scored.append(rec)
        if not scored:
            return f"未找到与 '{keyword}' 相关的历史分析"
        results = scored[:max_results]
        parts = []
        for r in results:
            topics = ", ".join(r.get("topics", []))
            parts.append(
                f"[{r.get('date', '?')}] {r.get('question', '')}\n"
                f"  结论: {r.get('conclusion', '')}\n"
                f"  情绪: {r.get('sentiment', '?')} | 话题: {topics}"
            )
        return f"找到 {len(scored)} 条相关记录（显示前 {len(results)} 条）:\n\n" + "\n\n".join(parts)

    # ── 工具注册表 ──

    def _tools(self) -> dict:
        return {
            "list_files": {
                "description": "列出指定目录下的文件和子目录",
                "params": {"path": "相对于项目根目录的路径，如 raw/reports 或 wiki/companies。留空则列出根目录"},
                "fn": self.list_files,
            },
            "read_file": {
                "description": "读取指定文件的内容。可指定 keyword 只返回关键词附近的上下文片段，避免加载全文",
                "params": {"path": "文件的相对路径", "max_chars": "最大读取字符数，默认4000", "keyword": "可选，只返回关键词所在段落的上下文"},
                "fn": self.read_file,
            },
            "search_files": {
                "description": "按关键词搜索文件名和文件内容，返回匹配文件及上下文片段",
                "params": {"keyword": "搜索关键词，如 胜宏 或 PCB", "scope": "搜索范围: raw / wiki / all（默认 all）"},
                "fn": self.search_files,
            },
            "recall": {
                "description": "从历史分析结论中检索相关记录（按关键词匹配问题、结论、话题）",
                "params": {"keyword": "搜索关键词，如 胜宏 或 宁德时代", "max_results": "最大返回条数，默认5"},
                "fn": self.recall,
            },
        }

    def get_tools_description(self) -> str:
        lines = []
        for name, tool in self._tools().items():
            params_desc = ", ".join(f"{k}: {v}" for k, v in tool["params"].items())
            lines.append(f"- **{name}**: {tool['description']}\n  参数: {{{params_desc}}}")
        return "\n".join(lines)

    def execute(self, name: str, args: dict) -> str:
        tools = self._tools()
        tool = tools.get(name)
        if not tool:
            return f"未知工具: {name}。可用工具: {', '.join(tools.keys())}"
        fn = tool["fn"]
        try:
            return fn(**args)
        except TypeError as e:
            return f"工具参数错误: {name}: {e}"
        except Exception as e:
            return f"工具执行失败: {name}: {e}"