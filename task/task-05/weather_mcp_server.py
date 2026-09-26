#!/usr/bin/env python3
"""天气查询 MCP Server（本地 stdio 模式）。

本文件是《智能体通信协议》第 2 题"动手实践"的配套实现：用 MCP Python SDK
实现一个真实可运行的 MCP Server，通过 JSON-RPC 2.0 over stdio 暴露"天气查询"
能力，同时演示 MCP 的三大核心概念 Tools / Resources / Prompts。

暴露的能力
----------
Tools
  - query_weather         查询城市实时天气 + 未来 N 天预报
  - compare_weather       批量比较多个城市（复用 query_weather 核心逻辑，体现"工具协作"）
  - build_weather_report  基于查询结果生成 Markdown 报告（查询 → 分析 → 报表 链路）
Resources
  - weather://cities           支持的城市目录（JSON）
  - weather://cities/{city}    单个城市档案（坐标、气候备注）
Prompts
  - weather_report_prompt      生成"天气报告"的提示模板

数据来源
--------
默认调用免费的 Open-Meteo API（无需 API Key）；网络不可用时自动回退到本地
确定性模拟数据，结果的 source 字段会标注 open-meteo / offline-mock。
也可用 --offline 或环境变量 WEATHER_MCP_OFFLINE=1 强制离线，便于离线演示与测试。

运行方式
--------
    # 本地 stdio 模式（默认，也是 MCP 客户端最常用的方式）
    python weather_mcp_server.py

    # 强制离线（不访问网络）
    python weather_mcp_server.py --offline

    # 远程扩展（对应第 2.3 问：把传输层从 stdio 换成 HTTP）
    python weather_mcp_server.py --transport streamable-http --port 8000

注意：stdio 模式下 stdout 只承载 JSON-RPC 报文，所有日志一律写入 stderr。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

# --------------------------------------------------------------------------
# SDK 兼容导入：mcp>=2.0 中 FastMCP 改名为 MCPServer；mcp 1.x 仍是 FastMCP。
# 本仓库环境安装的是 mcp 2.2.0，因此优先走 MCPServer。
# --------------------------------------------------------------------------
try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer  # type: ignore[attr-defined]
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - 兼容 mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]

logger = logging.getLogger("weather-mcp-server")

SERVER_NAME = "weather-mcp-server"
SERVER_VERSION = "1.0.0"

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT = float(os.getenv("WEATHER_MCP_HTTP_TIMEOUT", "6"))
MAX_FORECAST_DAYS = 7


def _offline_requested() -> bool:
    return os.getenv("WEATHER_MCP_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


OFFLINE = _offline_requested()


class WeatherError(ToolError, ValueError):
    """天气查询相关的可预期错误。

    继承 SDK 的 ToolError（同时也继承 ValueError，便于直接当 Python 使用）：
    这类"预料之中"的失败会以 isError 结果返回，且**错误原文会传递给模型**；
    如果抛普通异常，SDK 只会返回 "Error executing tool xxx"，模型看不到原因。
    """


# --------------------------------------------------------------------------
# 城市目录（离线可用的基础数据）
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class City:
    key: str
    name: str
    country: str
    latitude: float
    longitude: float
    climate: str
    aliases: tuple[str, ...] = ()


CITY_CATALOG: tuple[City, ...] = (
    City("beijing", "北京", "中国", 39.9042, 116.4074, "温带季风气候，四季分明，冬季干冷", ("北京", "beijing", "peking")),
    City("shanghai", "上海", "中国", 31.2304, 121.4737, "亚热带季风气候，梅雨明显，夏季湿热", ("上海", "shanghai")),
    City("guangzhou", "广州", "中国", 23.1291, 113.2644, "亚热带季风气候，长夏无冬，雨量充沛", ("广州", "guangzhou", "canton")),
    City("shenzhen", "深圳", "中国", 22.5431, 114.0579, "亚热带海洋性气候，温暖湿润", ("深圳", "shenzhen")),
    City("hangzhou", "杭州", "中国", 30.2741, 120.1551, "亚热带季风气候，四季分明", ("杭州", "hangzhou")),
    City("chengdu", "成都", "中国", 30.5728, 104.0668, "亚热带湿润气候，多云多雾、日照少", ("成都", "chengdu")),
    City("xian", "西安", "中国", 34.3416, 108.9398, "暖温带半湿润气候，春秋短、冬夏长", ("西安", "xian", "xi'an")),
    City("harbin", "哈尔滨", "中国", 45.8038, 126.5350, "中温带大陆性气候，冬季严寒漫长", ("哈尔滨", "harbin")),
    City("sanya", "三亚", "中国", 18.2528, 109.5119, "热带海洋性气候，全年高温，干湿季分明", ("三亚", "sanya")),
    City("lhasa", "拉萨", "中国", 29.6520, 91.1721, "高原温带半干旱气候，日照强、昼夜温差大", ("拉萨", "lhasa")),
)

_CITY_INDEX: dict[str, City] = {}
for _city in CITY_CATALOG:
    for _alias in (_city.key, _city.name, *_city.aliases):
        _CITY_INDEX[_alias.strip().lower()] = _city


def lookup_city(value: str) -> City | None:
    """按名称 / 别名 / key 在城市目录中查找。"""
    return _CITY_INDEX.get((value or "").strip().lower())


# WMO 天气代码（Open-Meteo 使用）→ 中文描述
WMO_CODE_TEXT: dict[int, str] = {
    0: "晴",
    1: "少云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴小冰雹",
    99: "雷阵雨伴强冰雹",
}


def describe_weather(code: Any) -> str:
    try:
        return WMO_CODE_TEXT.get(int(code), f"未知天气(code={code})")
    except (TypeError, ValueError):
        return f"未知天气(code={code})"


# --------------------------------------------------------------------------
# 数据获取：Open-Meteo（在线） + 确定性模拟（离线回退）
# --------------------------------------------------------------------------
def _http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - 固定 https 域名
        return json.loads(response.read().decode("utf-8"))


def _geocode(city: str) -> dict[str, Any] | None:
    """用 Open-Meteo Geocoding API 解析任意城市名。"""
    payload = _http_get_json(GEOCODING_URL, {"name": city, "count": 1, "language": "zh", "format": "json"})
    results = payload.get("results") or []
    if not results:
        return None
    top = results[0]
    return {
        "name": top.get("name", city),
        "country": top.get("country", ""),
        "admin1": top.get("admin1", ""),
        "latitude": float(top["latitude"]),
        "longitude": float(top["longitude"]),
    }


def _seed(*parts: Any) -> int:
    digest = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mock_temperature(latitude: float, day: date, salt: str) -> float:
    """确定性的模拟气温：纬度基准 + 季节正弦 + 少量抖动。"""
    doy = day.timetuple().tm_yday
    seasonal = math.cos((doy - 200) / 365.0 * 2 * math.pi)  # 北半球 7 月中旬最热
    base = 30.0 - 0.45 * abs(latitude) + 8.0 * seasonal
    jitter = (_seed(salt, day.isoformat()) % 500) / 100.0 - 2.5  # [-2.5, 2.5)
    return round(base + jitter, 1)


def _mock_weather(city_name: str, latitude: float, longitude: float, days: int) -> dict[str, Any]:
    """离线模拟数据：同一城市同一天结果稳定，便于测试复现。"""
    today = date.today()
    salt = f"{city_name}:{latitude:.2f}:{longitude:.2f}"
    current_temp = _mock_temperature(latitude, today, salt)
    condition_pool = [0, 1, 2, 3, 61, 80, 95]
    code = condition_pool[_seed(salt, today.isoformat(), "code") % len(condition_pool)]

    forecast = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        day_temp = _mock_temperature(latitude, day, salt)
        day_code = condition_pool[_seed(salt, day.isoformat(), "code") % len(condition_pool)]
        forecast.append(
            {
                "date": day.isoformat(),
                "condition": describe_weather(day_code),
                "weather_code": day_code,
                "temp_max": round(day_temp + 3.5, 1),
                "temp_min": round(day_temp - 4.5, 1),
                "precipitation_probability": _seed(salt, day.isoformat(), "pop") % 101,
            }
        )

    return {
        "source": "offline-mock",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current": {
            "temperature": current_temp,
            "feels_like": round(current_temp + (_seed(salt, "feels") % 40) / 10.0 - 2.0, 1),
            "humidity": 35 + _seed(salt, "hum") % 55,
            "wind_speed": round(1 + (_seed(salt, "wind") % 140) / 10.0, 1),
            "condition": describe_weather(code),
            "weather_code": code,
        },
        "forecast": forecast,
    }


def _live_weather(latitude: float, longitude: float, days: int) -> dict[str, Any]:
    payload = _http_get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days,
        },
    )
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}

    forecast = []
    for index, day in enumerate(daily.get("time") or []):
        forecast.append(
            {
                "date": day,
                "condition": describe_weather((daily.get("weather_code") or [None])[index]),
                "weather_code": (daily.get("weather_code") or [None])[index],
                "temp_max": (daily.get("temperature_2m_max") or [None])[index],
                "temp_min": (daily.get("temperature_2m_min") or [None])[index],
                "precipitation_probability": (daily.get("precipitation_probability_max") or [None])[index],
            }
        )

    return {
        "source": "open-meteo",
        "observed_at": current.get("time") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current": {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "condition": describe_weather(current.get("weather_code")),
            "weather_code": current.get("weather_code"),
        },
        "forecast": forecast,
    }


def _to_units(celsius: Any, units: str) -> Any:
    if celsius is None or units == "celsius":
        return celsius
    try:
        return round(float(celsius) * 9 / 5 + 32, 1)
    except (TypeError, ValueError):
        return celsius


def _convert_payload(payload: dict[str, Any], units: str) -> dict[str, Any]:
    if units == "celsius":
        return payload
    current = payload.get("current", {})
    for field in ("temperature", "feels_like"):
        current[field] = _to_units(current.get(field), units)
    for day in payload.get("forecast", []):
        for field in ("temp_max", "temp_min"):
            day[field] = _to_units(day.get(field), units)
    return payload


async def resolve_location(city: str) -> dict[str, Any]:
    """解析城市 → 坐标。优先本地目录，其次在线 Geocoding。"""
    name = (city or "").strip()
    if not name:
        raise WeatherError("city 不能为空，请提供城市名，例如：北京 / Shanghai")

    known = lookup_city(name)
    if known is not None:
        return {
            "city": known.name,
            "country": known.country,
            "latitude": known.latitude,
            "longitude": known.longitude,
            "climate": known.climate,
            "resolved_by": "catalog",
        }

    if OFFLINE:
        raise WeatherError(
            f"离线模式下无法解析未收录的城市 {name!r}。"
            f"可用城市：{'、'.join(c.name for c in CITY_CATALOG)}"
        )

    try:
        geo = await asyncio.to_thread(_geocode, name)
    except Exception as exc:  # 网络异常 → 明确报错，而不是静默失败
        raise WeatherError(f"在线解析城市 {name!r} 失败（{type(exc).__name__}: {exc}），可改用 --offline 模式") from exc

    if not geo:
        raise WeatherError(f"未找到城市 {name!r}，请检查拼写")

    return {
        "city": geo["name"],
        "country": geo.get("country", ""),
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "climate": "",
        "resolved_by": "geocoding",
    }


async def query_weather_core(
    city: str,
    days: int = 1,
    units: Literal["celsius", "fahrenheit"] = "celsius",
) -> dict[str, Any]:
    """核心查询逻辑：resolve_location → 在线/离线取数 → 单位换算。

    三个 Tool 都复用这个函数，因此"工具之间可以协作"不是口号，而是同一份数据链路。
    """
    if units not in ("celsius", "fahrenheit"):
        raise WeatherError("units 只能是 'celsius' 或 'fahrenheit'")
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise WeatherError("days 必须是 1-7 之间的整数") from None
    if not 1 <= days <= MAX_FORECAST_DAYS:
        raise WeatherError(f"days 必须在 1-{MAX_FORECAST_DAYS} 之间，收到 {days}")

    location = await resolve_location(city)

    payload: dict[str, Any] | None = None
    fallback_reason = ""
    if not OFFLINE:
        try:
            payload = await asyncio.to_thread(
                _live_weather, location["latitude"], location["longitude"], days
            )
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
            logger.warning("在线取数失败，回退到离线模拟数据：%s", fallback_reason)

    if payload is None:
        payload = _mock_weather(location["city"], location["latitude"], location["longitude"], days)

    payload = _convert_payload(payload, units)
    payload.update(
        {
            "city": location["city"],
            "country": location["country"],
            "coordinates": {"latitude": location["latitude"], "longitude": location["longitude"]},
            "units": units,
            "wind_speed_unit": "km/h",
        }
    )
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


# --------------------------------------------------------------------------
# MCP Server 定义
# --------------------------------------------------------------------------
mcp = MCPServer(
    name=SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "天气查询 MCP Server。用 query_weather 查询单个城市天气，"
        "用 compare_weather 比较多个城市，用 build_weather_report 生成 Markdown 报告；"
        "weather://cities 资源提供支持的城市目录；weather_report_prompt 提供报告写作模板。"
    ),
)


@mcp.tool()
async def query_weather(
    city: str,
    days: int = 1,
    units: Literal["celsius", "fahrenheit"] = "celsius",
) -> dict[str, Any]:
    """查询指定城市的实时天气与未来 N 天预报。

    Args:
        city: 城市名，例如 北京 / 上海 / Shanghai，支持目录内城市与在线解析的城市。
        days: 预报天数，1-7，默认 1（仅当天）。
        units: 温度单位，celsius（摄氏度，默认）或 fahrenheit（华氏度）。

    Returns:
        包含 current（实时）、forecast（逐日预报）、source（open-meteo 或 offline-mock）等字段的字典。
    """
    return await query_weather_core(city, days=days, units=units)


@mcp.tool()
async def compare_weather(
    cities: list[str],
    units: Literal["celsius", "fahrenheit"] = "celsius",
) -> dict[str, Any]:
    """比较多个城市的实时天气，并按气温从高到低给出排名。

    该工具复用 query_weather 的核心查询逻辑，体现工具之间的协作/编排。

    Args:
        cities: 待比较的城市名列表，例如 ["北京", "上海", "三亚"]。
        units: 温度单位，celsius 或 fahrenheit。

    Returns:
        包含 ranking（排名）、hottest / coldest（最热/最冷城市）与逐城市明细的字典。
    """
    if not cities:
        raise WeatherError("cities 不能为空，至少提供一个城市名")
    if len(cities) > 10:
        raise WeatherError("一次最多比较 10 个城市")

    results: list[dict[str, Any]] = []
    for name in cities:
        try:
            data = await query_weather_core(name, days=1, units=units)
            results.append(
                {
                    "city": data["city"],
                    "country": data["country"],
                    "temperature": data["current"]["temperature"],
                    "feels_like": data["current"]["feels_like"],
                    "condition": data["current"]["condition"],
                    "humidity": data["current"]["humidity"],
                    "source": data["source"],
                }
            )
        except WeatherError as exc:
            results.append({"city": name, "error": str(exc)})

    ok = [item for item in results if "temperature" in item and item["temperature"] is not None]
    ok.sort(key=lambda item: item["temperature"], reverse=True)
    errors = [item for item in results if "error" in item]

    return {
        "units": units,
        "requested": len(cities),
        "succeeded": len(ok),
        "ranking": [f"{index + 1}. {item['city']} {item['temperature']}°" for index, item in enumerate(ok)],
        "hottest": ok[0]["city"] if ok else None,
        "coldest": ok[-1]["city"] if ok else None,
        # details 与 ranking 保持同一顺序（成功项按气温降序，失败项排在最后）
        "details": ok + errors,
    }


@mcp.tool()
async def build_weather_report(
    city: str,
    days: int = 3,
    units: Literal["celsius", "fahrenheit"] = "celsius",
    audience: str = "普通读者",
) -> dict[str, Any]:
    """查询天气并生成一份面向指定读者的 Markdown 天气报告。

    对应"查询 → 分析 → 报表"链路中的报表生成环节，数据完全来自 query_weather 的核心实现。

    Args:
        city: 城市名。
        days: 报告覆盖的预报天数，1-7。
        units: 温度单位，celsius 或 fahrenheit。
        audience: 报告读者，例如 普通读者 / 出行者 / 农业生产者。

    Returns:
        包含 markdown（报告正文）、source（数据来源）等字段的字典。
    """
    data = await query_weather_core(city, days=days, units=units)
    unit_symbol = "°C" if units == "celsius" else "°F"
    current = data["current"]

    lines = [
        f"# {data['city']} 天气报告",
        "",
        f"- 面向读者：{audience}",
        f"- 数据来源：{data['source']}"
        + (f"（在线取数失败，已回退：{data['fallback_reason']}）" if data.get("fallback_reason") else ""),
        f"- 观测时间：{data['observed_at']}",
        f"- 温度单位：{unit_symbol}",
        "",
        "## 实时天气",
        "",
        f"{data['city']}当前{current['condition']}，气温 {current['temperature']}{unit_symbol}，"
        f"体感 {current['feels_like']}{unit_symbol}，湿度 {current['humidity']}%，"
        f"风速 {current['wind_speed']} km/h。",
        "",
        f"## 未来 {len(data['forecast'])} 天预报",
        "",
        "| 日期 | 天气 | 最高温 | 最低温 | 降水概率 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for day in data["forecast"]:
        lines.append(
            f"| {day['date']} | {day['condition']} | {day['temp_max']}{unit_symbol} | "
            f"{day['temp_min']}{unit_symbol} | {day['precipitation_probability']}% |"
        )

    temps = [day["temp_max"] for day in data["forecast"] if isinstance(day.get("temp_max"), (int, float))]
    if temps:
        warmest = max(temps)
        coolest = min(temps)
        lines += [
            "",
            "## 结论与建议",
            "",
            f"- 预报期内最高温 {warmest}{unit_symbol}，最低温 {coolest}{unit_symbol}，温差 {round(warmest - coolest, 1)}{unit_symbol}。",
            f"- 数据源：{data['source']}；如需更准确的实时数据，请保持网络可用后重新查询。",
        ]

    return {
        "city": data["city"],
        "audience": audience,
        "days": len(data["forecast"]),
        "units": units,
        "source": data["source"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markdown": "\n".join(lines),
    }


@mcp.resource("weather://cities", name="supported-cities", description="支持查询的城市目录（离线可用）", mime_type="application/json")
def supported_cities() -> str:
    """返回内置城市目录，供模型在调用工具前了解可选范围。"""
    return json.dumps(
        [
            {
                "key": city.key,
                "name": city.name,
                "country": city.country,
                "coordinates": {"latitude": city.latitude, "longitude": city.longitude},
                "climate": city.climate,
            }
            for city in CITY_CATALOG
        ],
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("weather://cities/{city}", name="city-profile", description="单个城市的档案（坐标与气候备注）", mime_type="application/json")
def city_profile(city: str) -> str:
    """按城市名 / 别名 / key 返回城市档案。"""
    known = lookup_city(city)
    if known is None:
        return json.dumps(
            {"error": f"未收录城市 {city!r}", "supported": [c.name for c in CITY_CATALOG]},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {
            "key": known.key,
            "name": known.name,
            "country": known.country,
            "coordinates": {"latitude": known.latitude, "longitude": known.longitude},
            "climate": known.climate,
            "aliases": list(known.aliases),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.prompt(name="weather_report_prompt", description="生成某个城市天气分析报告的提示模板")
def weather_report_prompt(city: str, days: int = 3, audience: str = "普通读者") -> str:
    """把"查天气 → 写报告"的流程固化成一个可复用的提示模板。"""
    days = max(1, min(int(days), MAX_FORECAST_DAYS))
    return (
        f"请为【{city}】生成一份面向【{audience}】的天气分析报告，覆盖未来 {days} 天。\n"
        f"步骤：\n"
        f"1. 调用工具 query_weather(city=\"{city}\", days={days}) 获取实时天气与预报；\n"
        f"2. 如需与其他城市对比，调用 compare_weather 工具；\n"
        f"3. 调用 build_weather_report(city=\"{city}\", days={days}, audience=\"{audience}\") 生成报告正文；\n"
        f"4. 报告中必须注明数据来源（source 字段）与观测时间，温度使用 ℃；\n"
        f"5. 最后用 3 条以内的要点给出面向该读者的出行/生产建议。"
    )


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def _configure_logging() -> None:
    """stdio 模式下 stdout 必须只承载 JSON-RPC，日志走 stderr。"""
    logging.basicConfig(
        level=os.getenv("WEATHER_MCP_LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> None:
    global OFFLINE
    parser = argparse.ArgumentParser(description="天气查询 MCP Server（默认 stdio 本地模式）")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.getenv("WEATHER_MCP_TRANSPORT", "stdio"),
        help="传输方式，默认 stdio（本地进程间通信）",
    )
    parser.add_argument("--offline", action="store_true", help="强制使用本地模拟数据，不访问网络")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP/SSE 模式监听地址")
    parser.add_argument("--port", type=int, default=8000, help="HTTP/SSE 模式监听端口")
    args = parser.parse_args(argv)

    if args.offline:
        os.environ["WEATHER_MCP_OFFLINE"] = "1"
        OFFLINE = True

    _configure_logging()
    logger.warning("启动 %s v%s，transport=%s，offline=%s", SERVER_NAME, SERVER_VERSION, args.transport, OFFLINE)

    if args.transport == "stdio":
        # 关键：stdio 模式下服务器作为一个子进程运行，由客户端通过 stdin/stdout 通信
        mcp.run(transport="stdio")
    else:  # pragma: no cover - 远程扩展路径
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
