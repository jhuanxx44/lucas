"""Answer 阶段增量流式解析：从模型输出的 JSON 中边收边提取 reply 字符串。

三态状态机（见 docs/plans/2026-07-20-answer-streaming.md）：

- DECIDE：缓冲头部，判定本步输出类型——
  - 出现 `"action": "tool"` → BUFFER（工具调用，不流式）
  - 出现 `"reply": "`（字符串值，无论 action 键先后）→ STREAM
  - 出现 `"reply":` 后接非 `"`（对象/数字等）→ BUFFER（eval 的结构化 answer）
  - markdown 围栏 ```json 前缀跳过后再判定
- STREAM：增量 JSON 字符串解码（处理 \\”、\\\\、\\n、\\uXXXX 跨 chunk 边界），
  产出文本 delta
- BUFFER：全量累积，不发任何 chunk

关键性质：只有确认是字符串 reply 才开始推送；工具调用、格式错误、
非字符串 answer 绝不泄漏半个字到前端。
"""
import re

# reply 键 + 冒号 + 第一个非空白字符（决定 STREAM 还是 BUFFER）
_REPLY_RE = re.compile(r'"reply"\s*:\s*(\S)', re.DOTALL)
_TOOL_RE = re.compile(r'"action"\s*:\s*"tool"')

_ESCAPES = {
    '"': '"', "\\": "\\", "/": "/",
    "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
}


class AnswerStreamParser:
    """feed(chunk) -> 本 chunk 提取出的可推送文本 delta 列表；finalize() 收尾"""

    DECIDE = "decide"
    STREAM = "stream"
    BUFFER = "buffer"

    def __init__(self) -> None:
        self.state = self.DECIDE
        self._buf = ""            # DECIDE 阶段的原始累积
        self._sbuf = ""           # STREAM 阶段尚未解码的原始残余
        self._esc = False         # 上一个字符是未消费的反斜杠
        self._uni: str | None = None   # \uXXXX 已收集的 hex 数字
        self._high: int | None = None  # 未配对的高位代理（\uD800-\uDBFF）
        self._closed = False      # reply 字符串已闭合（忽略后续一切内容）

    def feed(self, chunk: str) -> list[str]:
        if self.state == self.BUFFER or self._closed:
            return []
        if self.state == self.DECIDE:
            self._buf += chunk
            self._try_decide()
            if self.state != self.STREAM:
                return []
        else:
            self._sbuf += chunk
        return self._drain()

    def finalize(self) -> list[str]:
        """收尾：未完成的转义/代理位属于非法 JSON，不补发（与防泄漏语义一致）"""
        return []

    def _try_decide(self) -> None:
        text = self._buf
        pos = 0
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        if text[pos:pos + 1] == "`":
            # markdown 围栏：跳过整行（```json），行未收全时继续等
            nl = text.find("\n", pos)
            if nl == -1:
                return
            pos = nl + 1
        head = text[pos:]
        m_reply = _REPLY_RE.search(head)
        m_tool = _TOOL_RE.search(head)
        # 两者都出现时按文本先后判定（reply 在 action 前的 answer 也走 STREAM）
        if m_tool is not None and (m_reply is None or m_tool.start() < m_reply.start()):
            self.state = self.BUFFER
            return
        if m_reply is None:
            return
        if m_reply.group(1) != '"':
            self.state = self.BUFFER
            return
        self.state = self.STREAM
        self._sbuf = head[m_reply.end():]
        self._buf = ""

    def _drain(self) -> list[str]:
        """增量 JSON 字符串解码：尽可能消费 _sbuf，残缺转义留待下一 chunk"""
        out: list[str] = []
        buf = self._sbuf
        i, n = 0, len(buf)
        while i < n and not self._closed:
            c = buf[i]
            if self._uni is not None:
                self._uni += c
                i += 1
                if len(self._uni) == 4:
                    digits, self._uni = self._uni, None
                    try:
                        ch = self._decode_codepoint(int(digits, 16))
                    except ValueError:
                        ch = ""  # 非法 hex：丢弃，不阻塞后续解码
                    if ch:
                        out.append(ch)
                continue
            if self._esc:
                self._esc = False
                i += 1
                if c == "u":
                    self._uni = ""
                else:
                    out.append(_ESCAPES.get(c, c))  # 未知转义按字面放行（宽容）
                continue
            if c == "\\":
                self._esc = True
                i += 1
                continue
            if c == '"':
                self._closed = True
                i += 1
                break
            # 高位代理后接普通字符：丢弃孤立代理位（防下游编码崩溃）
            self._high = None
            out.append(c)
            i += 1
        self._sbuf = buf[i:]
        return out

    def _decode_codepoint(self, code: int) -> str:
        if 0xD800 <= code <= 0xDBFF:
            self._high = code  # 等待低位代理配对
            return ""
        if 0xDC00 <= code <= 0xDFFF:
            if self._high is not None:
                high, self._high = self._high, None
                return chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00))
            return ""  # 孤立低位代理：丢弃
        self._high = None
        return chr(code)
