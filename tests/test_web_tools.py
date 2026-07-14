"""web_tools 单元测试（全部 mock，不访问外网）"""
from __future__ import annotations

import io
from unittest.mock import patch

import src.tools.web_tools as web_tools
from src.tools.tool_result import ToolResult


def _fake_response(html: str, url: str = "https://example.com/page"):
    """构造一个模拟的 HTTP 响应对象"""
    raw = html.encode("utf-8")

    class _Resp:
        def __init__(self):
            self.headers = _Headers()

        def geturl(self):
            return url

        def read(self, limit=-1):
            if limit > 0:
                return raw[:limit]
            return raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Headers:
        def get(self, name, default=None):
            return default

        def get_content_charset(self):
            return "utf-8"

    return _Resp()


DDG_LITE_HTML = """
<html><body>
<table>
<tr><td><a href="https://example.com/a">Result A</a></td></tr>
<tr><td>Snippet for result A with enough text here</td></tr>
<tr><td><a href="https://example.com/b">Result B</a></td></tr>
<tr><td>Snippet for result B with enough text here</td></tr>
</table>
</body></html>
"""


def test_web_search_empty_query():
    result = web_tools.web_search("")
    assert result.success is False
    assert "查询词" in result.error


def test_web_search_via_ddg_lite_html():
    with patch.dict("sys.modules", {"duckduckgo_search": None}), \
         patch.object(web_tools, "_http_get", return_value=(DDG_LITE_HTML, "https://lite.duckduckgo.com/lite/")):
        result = web_tools.web_search("test query")
    assert result.success is True
    assert "Result A" in result.output
    assert "https://example.com/a" in result.output


def test_web_search_network_error():
    from urllib.error import URLError

    with patch.dict("sys.modules", {"duckduckgo_search": None}), \
         patch.object(web_tools, "_http_get", side_effect=URLError("boom")):
        result = web_tools.web_search("test query")
    assert result.success is False
    assert "搜索请求失败" in result.error


def test_web_search_no_results():
    with patch.dict("sys.modules", {"duckduckgo_search": None}), \
         patch.object(web_tools, "_http_get", return_value=("<html><body>nothing</body></html>", "https://lite.duckduckgo.com/lite/")):
        result = web_tools.web_search("test query")
    assert result.success is True
    assert "未找到" in result.output


def test_fetch_url_empty_url():
    result = web_tools.fetch_url("")
    assert result.success is False
    assert "URL" in result.error


def test_fetch_url_invalid_scheme():
    result = web_tools.fetch_url("ftp://example.com")
    assert result.success is False
    assert "协议" in result.error


def test_fetch_url_success():
    html = """
    <html><head><title>Example Page</title></head>
    <body><script>var x=1;</script>
    <p>Hello world paragraph one.</p>
    <p>Second paragraph with <a href="https://link.example.com">a link</a>.</p>
    </body></html>
    """
    with patch.object(web_tools, "urlopen", return_value=_fake_response(html, "https://example.com/page")):
        result = web_tools.fetch_url("https://example.com/page")
    assert result.success is True
    assert "Example Page" in result.output
    assert "Hello world" in result.output
    assert "Second paragraph" in result.output
    assert "a link" in result.output
    # script 内容不应出现
    assert "var x=1" not in result.output


def test_fetch_url_truncates_long_content():
    long_text = "A" * 20000
    html = f"<html><body><p>{long_text}</p></body></html>"
    with patch.object(web_tools, "urlopen", return_value=_fake_response(html)):
        result = web_tools.fetch_url("https://example.com/page", max_length=1000)
    assert result.success is True
    assert "截断" in result.output
    assert len(result.output) < 20000


def test_fetch_url_http_error():
    from urllib.error import HTTPError

    error = HTTPError(
        url="https://example.com/page",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=io.BytesIO(b""),
    )
    with patch.object(web_tools, "urlopen", side_effect=error):
        result = web_tools.fetch_url("https://example.com/page")
    assert result.success is False
    assert "HTTP" in result.error
    assert "404" in result.error


def test_html_to_markdown_extracts_title_and_text():
    html = "<html><head><title>标题</title><style>.a{}</style></head><body><p>正文内容</p></body></html>"
    text = web_tools._html_to_markdown(html)
    assert "标题" in text
    assert "正文内容" in text
    assert ".a{}" not in text


def test_web_tools_registered():
    from src.tools.registry import tool_registry

    assert "web_search" in tool_registry.list_tools()
    assert "fetch_url" in tool_registry.list_tools()
    spec = tool_registry.get("web_search")
    assert spec is not None
    assert spec.category == "external"
