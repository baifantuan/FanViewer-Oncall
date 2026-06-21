"""腾讯云 CLS (Cloud Log Service) MCP Server

本地实现的 CLS 日志服务 MCP Server，通过腾讯云 SDK 直连 CLS API，
提供日志查询、检索和分析功能。
"""

import logging
import functools
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

# 腾讯云 SDK
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.cls.v20201016 import cls_client, models as cls_models

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CLS_MCP_Server")

mcp = FastMCP("CLS")

# ═══════════════════════════════════════════════════
# 腾讯云 CLS 客户端工厂
# ═══════════════════════════════════════════════════

def _get_cls_client() -> cls_client.ClsClient:
    """创建腾讯云 CLS 客户端（从环境变量读取凭据）。"""
    secret_id = os.getenv("TENCENTCLOUD_SECRET_ID", "")
    secret_key = os.getenv("TENCENTCLOUD_SECRET_KEY", "")
    region = os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou")

    if not secret_id or not secret_key:
        raise RuntimeError(
            "腾讯云 CLS 凭据未配置。请在 .env 中设置 TENCENTCLOUD_SECRET_ID 和 TENCENTCLOUD_SECRET_KEY"
        )

    cred = credential.Credential(secret_id, secret_key)
    return cls_client.ClsClient(cred, region)


def log_tool_call(func):
    """装饰器：记录工具调用的日志，包括方法名、参数和返回状态"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method_name = func.__name__

        # 记录调用信息
        logger.info(f"=" * 80)
        logger.info(f"调用方法: {method_name}")

        # 记录参数（排除self等）
        if kwargs:
            # 使用 json.dumps 格式化参数，处理可能的序列化错误
            try:
                params_str = json.dumps(kwargs, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                params_str = str(kwargs)
            logger.info(f"参数信息:\n{params_str}")
        else:
            logger.info("参数信息: 无")

        # 执行方法
        try:
            result = func(*args, **kwargs)

            # 记录返回状态
            logger.info(f"返回状态: SUCCESS")

            # 记录返回结果摘要（避免日志过长）
            if isinstance(result, dict):
                summary = {k: v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} with {len(v)} items>"
                          for k, v in list(result.items())[:5]}
                logger.info(f"返回结果摘要: {json.dumps(summary, ensure_ascii=False)}")
            else:
                logger.info(f"返回结果: {result}")

            logger.info(f"=" * 80)
            return result

        except Exception as e:
            # 记录错误状态
            logger.error(f"返回状态: ERROR")
            logger.error(f"错误信息: {str(e)}")
            logger.error(f"=" * 80)
            raise

    return wrapper


def parse_time_or_default(time_str: Optional[str], default_offset_hours: int = 0) -> datetime:
    """解析时间字符串或返回默认时间。

    Args:
        time_str: 时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        default_offset_hours: 默认时间偏移（小时）

    Returns:
        datetime: 解析后的时间对象
    """
    if time_str:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now() + timedelta(hours=default_offset_hours)


def generate_time_series(base_time: datetime, minutes_offset: int) -> str:
    """生成基于基准时间的时间字符串。

    Args:
        base_time: 基准时间
        minutes_offset: 分钟偏移量

    Returns:
        str: 格式化的时间字符串
    """
    result_time = base_time + timedelta(minutes=minutes_offset)
    return result_time.strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
@log_tool_call
def get_current_timestamp() -> int:
    """获取当前时间戳（以毫秒为单位）。
    
    此工具用于获取标准的毫秒时间戳，可用于：
    1. 作为 search_log 的 end_time 参数（查询到现在）
    2. 计算历史时间点作为 start_time 参数
    
    Returns:
        int: 当前时间戳（毫秒），例如: 1708012345000
    
    使用示例:
        # 获取当前时间
        current = get_current_timestamp()
        
        # 计算15分钟前的时间
        fifteen_min_ago = current - (15 * 60 * 1000)
        
        # 计算1小时前的时间
        one_hour_ago = current - (60 * 60 * 1000)
        
        # 用于搜索最近15分钟的日志
        search_log(
            topic_id="topic-001",
            start_time=fifteen_min_ago,
            end_time=current
        )
    """
    return int(datetime.now().timestamp() * 1000)


@mcp.tool()
@log_tool_call
def get_region_code_by_name(region_name: str) -> Dict[str, Any]:
    """根据地区名称搜索对应的地区参数。

    Args:
        region_name: 地区名称（如：北京、上海、广州等）

    Returns:
        Dict: 包含地区代码和相关信息的字典
            - region_code: 地区代码
            - region_name: 地区名称
            - available: 是否可用
    """
    # 腾讯云常见地域映射表
    region_mapping = {
        "北京": {"region_code": "ap-beijing", "region_name": "北京", "available": True},
        "上海": {"region_code": "ap-shanghai", "region_name": "上海", "available": True},
        "广州": {"region_code": "ap-guangzhou", "region_name": "广州", "available": True},
        "成都": {"region_code": "ap-chengdu", "region_name": "成都", "available": True},
        "重庆": {"region_code": "ap-chongqing", "region_name": "重庆", "available": True},
        "南京": {"region_code": "ap-nanjing", "region_name": "南京", "available": True},
        "香港": {"region_code": "ap-hongkong", "region_name": "香港", "available": True},
        "新加坡": {"region_code": "ap-singapore", "region_name": "新加坡", "available": True},
        "东京": {"region_code": "ap-tokyo", "region_name": "东京", "available": True},
        "硅谷": {"region_code": "na-siliconvalley", "region_name": "硅谷", "available": True},
        "弗吉尼亚": {"region_code": "na-ashburn", "region_name": "弗吉尼亚", "available": True},
    }

    result = region_mapping.get(region_name)
    if result:
        return result
    else:
        return {
            "region_code": None,
            "region_name": region_name,
            "available": False,
            "error": f"未找到地区: {region_name}"
        }


@mcp.tool()
@log_tool_call
def get_topic_info_by_name(topic_name: str, region_code: Optional[str] = None) -> Dict[str, Any]:
    """根据主题名称搜索相关的主题信息（通过腾讯云 CLS DescribeTopics API）。

    Args:
        topic_name: 主题名称（精确匹配）
        region_code: 地区代码（可选，默认使用 .env 配置的地域）

    Returns:
        Dict: 包含主题信息的字典
            - topic_id: 主题ID
            - topic_name: 主题名称
            - region_code: 所属地区
            - create_time: 创建时间
            - period: 日志保存天数
            - auto_split: 是否自动分裂
    """
    try:
        client = _get_cls_client()
        req = cls_models.DescribeTopicsRequest()
        # 按主题名称精确过滤
        filter_obj = cls_models.Filter()
        filter_obj.Key = "topicName"
        filter_obj.Values = [topic_name]
        req.Filters = [filter_obj]

        resp = client.DescribeTopics(req)

        if resp.Topics and len(resp.Topics) > 0:
            topic = resp.Topics[0]
            return {
                "topic_id": topic.TopicId,
                "topic_name": topic.TopicName,
                "logset_id": topic.LogsetId,
                "logset_name": getattr(topic, "LogsetName", ""),
                "region_code": region_code or os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou"),
                "create_time": topic.CreateTime,
                "period": topic.Period,
                "auto_split": topic.AutoSplit,
            }

        return {
            "topic_id": None,
            "topic_name": topic_name,
            "error": f"未找到主题: {topic_name}",
        }

    except TencentCloudSDKException as e:
        return {"error": f"CLS API 调用失败: {e.code} - {e.message}"}
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool()
@log_tool_call
def search_topic_by_service_name(
    service_name: str,
    region_code: Optional[str] = None,
    fuzzy: bool = True
) -> Dict[str, Any]:
    """根据服务名称搜索相关的日志主题信息，支持模糊搜索。
    
    此工具用于根据服务名称查找对应的日志主题（topic），便于后续进行日志查询。
    
    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service", "sync", "data-sync"
            说明: 当 fuzzy=True 时，支持部分匹配
        
        region_code: 地区代码（可选）
            示例: "ap-beijing", "ap-shanghai"
            说明: 如果指定，只返回该地区的主题
        
        fuzzy: 是否启用模糊搜索（可选，默认 True）
            True: 部分匹配，例如 "sync" 可以匹配 "data-sync-service"
            False: 精确匹配，必须完全一致
    
    Returns:
        Dict: 搜索结果
            - total: 匹配到的主题数量
            - topics: 主题列表，每个主题包含:
                * topic_id: 主题ID（用于后续日志查询）
                * topic_name: 主题名称
                * service_name: 服务名称
                * region_code: 所属地区
                * create_time: 创建时间
                * log_count: 日志数量
                * description: 主题描述
            - query: 查询条件
    
    使用示例:
        # 示例1: 模糊搜索（推荐）
        search_topic_by_service_name(service_name="data-sync")
        # 可以匹配: "data-sync-service", "data-sync-worker" 等
        
        # 示例2: 精确搜索
        search_topic_by_service_name(
            service_name="data-sync-service",
            fuzzy=False
        )
        
        # 示例3: 指定地区搜索
        search_topic_by_service_name(
            service_name="sync",
            region_code="ap-beijing"
        )
        
        # 示例4: 查找后进行日志搜索的完整流程
        # 步骤1: 根据服务名查找 topic
        result = search_topic_by_service_name(service_name="data-sync-service")
        
        # 步骤2: 获取 topic_id
        topic_id = result["topics"][0]["topic_id"]  # "topic-001"
        
        # 步骤3: 使用 topic_id 查询日志
        current_ts = get_current_timestamp()
        start_ts = current_ts - (15 * 60 * 1000)
        search_log(
            topic_id=topic_id,
            start_time=start_ts,
            end_time=current_ts
        )
    """
    try:
        client = _get_cls_client()
        # 列出所有日志主题
        req = cls_models.DescribeTopicsRequest()
        resp = client.DescribeTopics(req)

        all_topics = resp.Topics or []
        matched_topics = []

        for topic in all_topics:
            topic_name = topic.TopicName

            # 服务名称匹配（在 topic 名称中搜索）
            if fuzzy:
                if service_name.lower() not in topic_name.lower():
                    continue
            else:
                if service_name.lower() != topic_name.lower():
                    continue

            matched_topics.append({
                "topic_id": topic.TopicId,
                "topic_name": topic_name,
                "logset_id": topic.LogsetId,
                "logset_name": getattr(topic, "LogsetName", ""),
                "create_time": topic.CreateTime,
                "period": topic.Period,
                "auto_split": topic.AutoSplit,
            })

        return {
            "total": len(matched_topics),
            "topics": matched_topics,
            "query": {
                "service_name": service_name,
                "region_code": region_code,
                "fuzzy": fuzzy,
            },
            "message": (
                f"找到 {len(matched_topics)} 个匹配的日志主题"
                if matched_topics
                else f"未找到包含 '{service_name}' 的日志主题"
            ),
        }

    except TencentCloudSDKException as e:
        return {"error": f"CLS API 调用失败: {e.code} - {e.message}"}
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool()
@log_tool_call
def search_log(
    topic_id: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    query: Optional[str] = None,
    limit: int = 100,
    time_range: Optional[str] = None,
) -> Dict[str, Any]:
    """基于提供的查询参数搜索日志（默认查询过去 1 小时）。

    Args:
        topic_id: 主题ID（必填）
            示例: "e30efca7-7506-4909-9aa6-067c5c6e7073"

        time_range: 时间范围（可选，字符串），优先级高于 start_time
            可选值: "15m"(15分钟), "1h"(1小时), "6h"(6小时), "24h"(1天), "3d"(3天), "7d"(7天)
            推荐使用此参数而非手动计算时间戳，例如 time_range="24h"

        start_time: 开始时间戳（可选，int 类型毫秒）
            默认: 1 小时前

        end_time: 结束时间戳（可选，int 类型毫秒）
            默认: 当前时间

        query: 查询语句（可选，CLS 查询语法）
            示例: "level:ERROR" 或 "level:ERROR OR level:WARN"

        limit: 返回结果数量限制（默认 100）

    Returns:
        Dict: 搜索结果，包含 logs 列表及每条日志的 timestamp/level/message 等字段

    使用示例:
        # 查最近 24 小时
        search_log(topic_id="e30efca7-...", time_range="24h")

        # 查最近 1 小时
        search_log(topic_id="e30efca7-...", time_range="1h")

        # 查指定级别
        search_log(topic_id="...", query="level:ERROR", time_range="24h")
    """
    # time_range 优先级高于 start_time
    if time_range:
        end_time = int(datetime.now().timestamp() * 1000)
        r = time_range.lower()
        if r.endswith("m"):
            start_time = end_time - int(r[:-1]) * 60 * 1000
        elif r.endswith("h"):
            start_time = end_time - int(r[:-1]) * 60 * 60 * 1000
        elif r.endswith("d"):
            start_time = end_time - int(r[:-1]) * 24 * 60 * 60 * 1000
        else:
            start_time = end_time - 60 * 60 * 1000  # fallback: 1h

    # 默认时间范围：过去 1 小时
    if end_time is None:
        end_time = int(datetime.now().timestamp() * 1000)
    if start_time is None:
        start_time = end_time - 60 * 60 * 1000  # 1 小时前
    import time as _time
    _t0 = _time.time()

    try:
        client = _get_cls_client()
        req = cls_models.SearchLogRequest()
        req.TopicId = topic_id
        req.From = start_time
        req.To = end_time
        req.Query = query or ""
        req.Limit = limit

        resp = client.SearchLog(req)

        # 解析返回的日志
        logs = []
        results = resp.Results or []
        for log_info in results:
            log_entry = {
                "timestamp": _time.strftime(
                    "%Y-%m-%d %H:%M:%S", _time.localtime(log_info.Time / 1000)
                ),
                "topic_id": getattr(log_info, "TopicId", ""),
                "topic_name": getattr(log_info, "TopicName", ""),
                "source": getattr(log_info, "Source", ""),
            }
            # 解析 LogJson（JSON 字符串）为字典
            log_json = getattr(log_info, "LogJson", "")
            if log_json:
                try:
                    parsed = json.loads(log_json)
                    log_entry.update(parsed)
                except json.JSONDecodeError:
                    log_entry["_raw"] = log_json
            logs.append(log_entry)

        took_ms = round((_time.time() - _t0) * 1000)

        return {
            "topic_id": topic_id,
            "start_time": start_time,
            "end_time": end_time,
            "query": query,
            "limit": limit,
            "total": len(logs),
            "logs": logs,
            "took_ms": took_ms,
            "message": f"成功查询 {len(logs)} 条日志（耗时 {took_ms}ms）",
        }

    except TencentCloudSDKException as e:
        return {
            "topic_id": topic_id,
            "error": f"CLS SearchLog 失败: {e.code} - {e.message}",
            "total": 0,
            "logs": [],
        }
    except RuntimeError as e:
        return {"error": str(e), "total": 0, "logs": []}



if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")
