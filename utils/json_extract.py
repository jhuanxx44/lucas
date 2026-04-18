"""
从 LLM 返回的文本中提取 JSON 对象。

处理多种格式：
- 纯 JSON: {"action": "direct"}
- Markdown 代码块: ```json\n{"action": "direct"}\n```
- 混有思考过程（MiniMax thinking 模型）:
  <think>\n...(thinking)...</think>\n...(final JSON)...
"""
import json
import re
from typing import Optional


def extract_json(text: str) -> Optional[dict | list]:
    # 1. 去掉 markdown 代码块
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if len(lines) >= 2:
            stripped = "\n".join(lines[1:-1])
        else:
            stripped = stripped.strip("`")
    stripped = stripped.strip()
    # 2. 直接解析
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # 3. 思考模型：优先从 </think> 之后找（最终答案所在位置）
    think_end = stripped.rfind("</think>")
    if think_end >= 0:
        after_think = stripped[think_end + 9:].strip()
        try:
            return json.loads(after_think)
        except json.JSONDecodeError:
            pass
        matches = list(re.finditer(r'[\[{]', after_think))
        for m in reversed(matches):
            try:
                obj = json.loads(after_think[m.start():])
                if obj:
                    return obj
            except json.JSONDecodeError:
                continue
    # 4. 兜底：全文从后往前找最后一个能解析的 { 或 [
    matches = list(re.finditer(r'[\[{]', stripped))
    for m in reversed(matches):
        try:
            obj = json.loads(stripped[m.start():])
            if obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None
