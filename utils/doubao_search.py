"""豆包搜索（Global 版）API 客户端。

接口文档：火山引擎联网搜索 Global 版。
- URL: https://open.feedcoopapi.com/search_api/global_search
- 认证: Authorization: Bearer <API_KEY>（环境变量 DOUBAO_SEARCH_API_KEY）
- 限流: 账号维度 5 QPS；免费额度每月 500 次
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

DOUBAO_SEARCH_URL = "https://open.feedcoopapi.com/search_api/global_search"
DOUBAO_SEARCH_TIMEOUT_SECONDS = 20.0
MAX_DOC_COUNT = 20
MAX_SNIPPET_LENGTH = 3000
# 图片摘要不做文本展示，传 1 减少响应体积
MAX_IMAGE_COUNT_PER_DOC = 1


class DoubaoSearchError(Exception):
    """豆包搜索调用失败（未配置 key、网络错误、接口错误码等）。"""


async def search(
    query: str,
    max_results: int = 10,
    max_snippet_length: int = 500,
) -> str:
    """调用豆包搜索 Global 版，返回 markdown 结果列表；失败抛 DoubaoSearchError。

    无结果时返回空字符串。max_results 上限 20，max_snippet_length 上限 3000。
    """
    api_key = os.environ.get("DOUBAO_SEARCH_API_KEY")
    if not api_key:
        raise DoubaoSearchError("未配置豆包搜索 API Key（环境变量 DOUBAO_SEARCH_API_KEY）")
    payload = {
        "Query": query,
        "DocCount": max_results,
        "MaxSnippetLength": max_snippet_length,
        "MaxImageCountPerDoc": MAX_IMAGE_COUNT_PER_DOC,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(
            timeout=DOUBAO_SEARCH_TIMEOUT_SECONDS, headers=headers,
        ) as client:
            response = await client.post(DOUBAO_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise DoubaoSearchError(
            f"豆包搜索 HTTP {e.response.status_code}：{e.response.text[:200]}"
        ) from e
    except httpx.HTTPError as e:
        raise DoubaoSearchError(f"豆包搜索网络错误：{type(e).__name__}: {e}") from e
    except ValueError as e:
        raise DoubaoSearchError(f"豆包搜索响应解析失败：{e}") from e

    metadata = data.get("ResponseMetadata") or {}
    error = metadata.get("Error")
    if error:
        code = error.get("Code") or error.get("CodeN")
        raise DoubaoSearchError(f"豆包搜索接口错误 {code}：{error.get('Message', '')}")

    result = data.get("Result")
    if not isinstance(result, dict):
        raise DoubaoSearchError("豆包搜索响应异常：Result 为空")
    if result.get("ErrorCode"):
        raise DoubaoSearchError(
            f"豆包搜索错误 {result.get('ErrorCode')}：{result.get('ErrorMsg', '')}"
        )

    documents = result.get("Documents") or []
    if not documents:
        return ""
    return _format_documents(documents)


def _format_documents(documents: list[dict]) -> str:
    parts = []
    for index, doc in enumerate(documents, 1):
        title = (doc.get("Title") or "").strip() or "无标题"
        url = doc.get("Url") or ""
        lines = [f"{index}. [{title}]({url})"]
        meta = []
        host_info = doc.get("HostInfo") or {}
        if host_info.get("Hostname"):
            meta.append(f"来源：{host_info['Hostname']}")
        doc_info = doc.get("DocumentInfo") or {}
        if doc_info.get("PublishTime"):
            meta.append(f"发布时间：{doc_info['PublishTime']}")
        if meta:
            lines.append("   " + "｜".join(meta))
        text_parts = [
            snippet["Text"].strip()
            for snippet in doc.get("Snippet") or []
            if isinstance(snippet, dict)
            and snippet.get("Type") == "text"
            and snippet.get("Text")
        ]
        body = "\n".join(text_parts).strip()
        if body:
            lines.append(f"   {body}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
