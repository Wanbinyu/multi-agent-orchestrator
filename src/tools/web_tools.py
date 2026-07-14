"""网页工具：web_search 与 fetch_url

仅依赖标准库；若安装了可选依赖 duckduckgo-search 则优先使用以提升搜索质量。
"""
from __future__ import annotations

import gzip
import io
import json
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult

# 抓取上限
_MAX_BYTES = 1024 * 1024  # 1MB
_DEFAULT_TIMEOUT = 15
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> tuple[str, str]:
    """发起 GET 请求，返回 (text, final_url)"""
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urlopen(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        raw = resp.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raw = raw[:_MAX_BYTES]
        # 处理 gzip
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
        if encoding == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        charset = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
    return text, final_url


@tool_registry.register(
    name="web_search",
    description="使用 DuckDuckGo 进行网页搜索，返回标题、链接和摘要列表",
    params={
        "query": {"type": "string", "description": "搜索关键词"},
        "top_n": {"type": "integer", "description": "返回结果数量", "default": 5},
    },
    category="external",
)
def web_search(query: str, top_n: int = 5) -> ToolResult:
    if not query.strip():
        return ToolResult(success=False, error="查询词不能为空")

    # 优先使用可选依赖 duckduckgo-search
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception:
        DDGS = None

    if DDGS is not None:
        try:
            results: list[dict] = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=top_n):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href") or r.get("url") or "",
                        "snippet": r.get("body") or r.get("snippet") or "",
                    })
            if results:
                return ToolResult(success=True, output=_format_search_results(query, results))
        except Exception:
            pass  # 降级到 HTML 抓取

    # 降级方案：解析 DuckDuckGo lite HTML
    try:
        html, _ = _http_get(f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}")
        results = _parse_ddg_lite(html, top_n)
        if not results:
            return ToolResult(success=True, output=f"未找到与 '{query}' 相关的搜索结果。")
        return ToolResult(success=True, output=_format_search_results(query, results))
    except (HTTPError, URLError, TimeoutError) as e:
        return ToolResult(success=False, error=f"搜索请求失败：{e}")
    except Exception as e:
        return ToolResult(success=False, error=f"搜索失败：{e}")


@tool_registry.register(
    name="fetch_url",
    description="抓取指定 URL 的网页内容并转为简易 Markdown 文本",
    params={
        "url": {"type": "string", "description": "要抓取的网页地址"},
        "max_length": {"type": "integer", "description": "返回文本最大字符数", "default": 8000},
    },
    category="external",
)
def fetch_url(url: str, max_length: int = 8000) -> ToolResult:
    if not url.strip():
        return ToolResult(success=False, error="URL 不能为空")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ToolResult(success=False, error=f"不支持的协议：{parsed.scheme}")
    if not parsed.netloc:
        return ToolResult(success=False, error="URL 缺少域名")

    try:
        html, final_url = _http_get(url)
    except HTTPError as e:
        return ToolResult(success=False, error=f"HTTP 错误：{e.code} {e.reason}")
    except (URLError, TimeoutError) as e:
        return ToolResult(success=False, error=f"请求失败：{e}")
    except Exception as e:
        return ToolResult(success=False, error=f"抓取失败：{e}")

    try:
        text = _html_to_markdown(html)
    except Exception as e:
        return ToolResult(success=False, error=f"解析页面失败：{e}")

    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length] + "\n\n...（内容已截断）"
    header = f"来源：{final_url}\n\n"
    return ToolResult(success=True, output=header + text)


def _format_search_results(query: str, results: list[dict]) -> str:
    lines = [f'搜索 "{query}" 的结果（{len(results)} 条）：', ""]
    for i, r in enumerate(results, 1):
        title = r.get("title", "(无标题)") or "(无标题)"
        url = r.get("url", "")
        snippet = (r.get("snippet", "") or "").replace("\n", " ").strip()
        if url:
            lines.append(f"{i}. [{title}]({url})")
        else:
            lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _parse_ddg_lite(html: str, top_n: int) -> list[dict]:
    """从 DuckDuckGo lite 页面提取结果"""
    parser = _DDGLiteParser()
    parser.feed(html)
    results: list[dict] = []
    for r in parser.results[:top_n]:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("snippet", ""),
        })
    return results


class _DDGLiteParser(HTMLParser):
    """简化解析 DuckDuckGo lite 结果表格"""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._current: dict[str, str] = {}
        self._capture: str | None = None
        self._link_href: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href", "") or ""
            if href.startswith("http://") or href.startswith("https://"):
                self._link_href = href
                self._capture = "title"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture == "title":
            self._capture = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._capture == "title" and self._link_href:
            self._current = {"title": text, "url": self._link_href, "snippet": ""}
            self._capture = "snippet"
            self._link_href = ""
        elif self._capture == "snippet" and self._current:
            if self._current["snippet"]:
                self._current["snippet"] += " " + text
            else:
                self._current["snippet"] = text
            if len(self._current["snippet"]) > 30:
                self.results.append(self._current)
                self._current = {}
                self._capture = None


class _TextExtractor(HTMLParser):
    """把 HTML 抽取为简易 Markdown 文本"""

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._skip_tag: str | None = None
        self._title: str = ""
        self._in_title = False
        self._current_link: str = ""
        self._link_text: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth > 0:
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth = 1
            self._skip_tag = tag
            return
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href", "") or ""
            if href.startswith("http://") or href.startswith("https://"):
                self._current_link = href
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth > 0:
            if tag == self._skip_tag:
                self._skip_depth = 0
                self._skip_tag = None
            return
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_link and self._link_text.strip():
            self._chunks.append(f"[{self._link_text.strip()}]({self._current_link})")
            self._current_link = ""
            self._link_text = ""
        elif tag in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data
        if self._in_title:
            self._title += text
            return
        if self._current_link:
            self._link_text += text
            return
        self._chunks.append(text)

    @property
    def text(self) -> str:
        title = self._title.strip()
        body = "".join(self._chunks)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if title:
            return f"# {title}\n\n{body}"
        return body


def _html_to_markdown(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text
