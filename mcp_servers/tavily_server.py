"""Tavily Web Search MCP Server

通过 Tavily API 提供联网搜索能力，支持通用搜索和新闻搜索。
"""

import logging
import functools
import json
import os
from typing import Any, Dict, Optional
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

from tavily import TavilyClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Tavily_MCP_Server")

mcp = FastMCP("Tavily")


def log_tool_call(func):
    """装饰器：记录工具调用日志"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"{'='*60}")
        logger.info(f"调用方法: {func.__name__}")
        if kwargs:
            try:
                safe = {k: v for k, v in kwargs.items() if k != "api_key"}
                logger.info(f"参数:\n{json.dumps(safe, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
        try:
            result = func(*args, **kwargs)
            logger.info(f"返回状态: SUCCESS")
            if isinstance(result, dict):
                logger.info(
                    f"结果摘要: {json.dumps({k: v if not isinstance(v, list) else f'<{len(v)} items>' for k, v in list(result.items())[:4]}, ensure_ascii=False)}"
                )
            logger.info(f"{'='*60}")
            return result
        except Exception as e:
            logger.error(f"错误: {e}")
            raise

    return wrapper


def _get_tavily_client() -> TavilyClient:
    """创建 Tavily 客户端"""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY 未配置，请在 .env 中设置")
    return TavilyClient(api_key=api_key)


@mcp.tool()
@log_tool_call
def tavily_web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    days: Optional[int] = None,
    include_domains: Optional[str] = None,
    exclude_domains: Optional[str] = None,
) -> Dict[str, Any]:
    """使用 Tavily API 进行联网搜索，获取最新的网页信息。

    适用场景：查询实时信息、最新新闻、技术文档、行业动态等需要联网获取的内容。

    Args:
        query: 搜索关键词（必填），使用自然语言描述你想搜索的内容
        max_results: 返回结果数（默认 5，最多 10）
        search_depth: 搜索深度，"basic"(快速) 或 "advanced"(深入)
        topic: 搜索类别，"general"(通用)、"news"(新闻) 或 "finance"(金融)
        days: 限定最近 N 天内的结果（如 7 表示最近一周）
        include_domains: 限定搜索域名，逗号分隔（如 "github.com,stackoverflow.com"）
        exclude_domains: 排除指定域名，逗号分隔

    Returns:
        Dict: 包含 answer(直接答案) 和 results(搜索结果列表，每项含 title/url/content/score)
    """
    client = _get_tavily_client()

    # 处理域名参数
    inc_domains = (
        [d.strip() for d in include_domains.split(",") if d.strip()]
        if include_domains
        else None
    )
    exc_domains = (
        [d.strip() for d in exclude_domains.split(",") if d.strip()]
        if exclude_domains
        else None
    )

    params: Dict[str, Any] = {
        "query": query,
        "max_results": min(max_results, 10),
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": True,
    }
    if days:
        params["days"] = days
    if inc_domains:
        params["include_domains"] = inc_domains
    if exc_domains:
        params["exclude_domains"] = exc_domains

    response = client.search(**params)

    return {
        "query": query,
        "answer": response.get("answer", ""),
        "total_results": len(response.get("results", [])),
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
                "published_date": r.get("published_date", ""),
            }
            for r in response.get("results", [])
        ],
        "search_time": response.get("response_time", 0),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8005, path="/mcp")
