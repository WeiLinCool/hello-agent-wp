#!/usr/bin/env python3
"""weather_mcp_server 的 stdio 客户端（MCP 官方 SDK）。

用途：以真实 MCP 客户端身份启动 weather_mcp_server.py 子进程，通过
JSON-RPC 2.0 over stdio 完成一次完整交互：

    initialize → tools/list → tools/call → resources/list → resources/read
              → prompts/list → prompts/get

同时支持 --trace，把 stdio 上双向流动的 JSON-RPC 报文原样打印出来，
用来直观理解第 2.3 问中"JSON-RPC 2.0 + stdio"的通信模型。

运行方式：
    python weather_mcp_client.py                # 在线（失败自动回退离线模拟）
    python weather_mcp_client.py --offline      # 强制离线，结果可复现
    python weather_mcp_client.py --trace        # 打印 JSON-RPC 报文
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).resolve().with_name("weather_mcp_server.py")


# --------------------------------------------------------------------------
# JSON-RPC 报文抓取（透明代理 stdio 上的读写流）
# --------------------------------------------------------------------------
def _frame_text(item: Any) -> str:
    message = getattr(item, "message", item)
    dump = getattr(message, "model_dump_json", None)
    if callable(dump):
        try:
            return json.dumps(json.loads(dump(exclude_none=True)), ensure_ascii=False, indent=None)
        except Exception:  # pragma: no cover - 仅用于展示
            pass
    return json.dumps(str(message), ensure_ascii=False)


class TracedRead:
    """在 read 流上打印 "server → client" 报文。"""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def _log(self, item: Any) -> None:
        if isinstance(item, Exception):
            print(f"  ← [transport error] {item!r}", file=sys.stderr)
        else:
            print(f"  ← server → client: {_frame_text(item)}", file=sys.stderr)

    async def receive(self) -> Any:
        item = await self._stream.receive()
        self._log(item)
        return item

    def __aiter__(self) -> "TracedRead":
        return self

    async def __anext__(self) -> Any:
        item = await self._stream.__anext__()
        self._log(item)
        return item

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def __aenter__(self) -> "TracedRead":
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._stream.__aexit__(*exc)


class TracedWrite:
    """在 write 流上打印 "client → server" 报文。"""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    async def send(self, item: Any) -> None:
        print(f"  → client → server: {_frame_text(item)}", file=sys.stderr)
        await self._stream.send(item)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def __aenter__(self) -> "TracedWrite":
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._stream.__aexit__(*exc)


# --------------------------------------------------------------------------
# 结果展示辅助
# --------------------------------------------------------------------------
def pick(obj: Any, *names: str, default: Any = None) -> Any:
    """兼容 mcp 1.x（camelCase 字段）与 mcp 2.x（snake_case 字段）。"""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _payload(result: Any) -> Any:
    """优先取结构化输出（structuredContent），否则解析文本内容。"""
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured:
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            structured = structured["result"]
        return structured
    for block in getattr(result, "content", []) or []:
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return block.text
    return None


def show(title: str, value: Any, *, limit: int = 1200) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > limit:
        text = text[:limit] + f"\n...（已截断，共 {len(text)} 字符）"
    print(f"\n--- {title} ---\n{text}")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
async def run_client(offline: bool, trace: bool) -> int:
    args = [str(SERVER_SCRIPT)]
    if offline:
        args.append("--offline")

    params = StdioServerParameters(
        command=sys.executable,
        args=args,
        cwd=str(SERVER_SCRIPT.parent),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    print(f"[client] 启动 MCP Server 子进程：{sys.executable} {' '.join(args)}")
    async with stdio_client(params) as (read_stream, write_stream):
        if trace:
            print("[client] 开启 JSON-RPC 报文抓取（stderr）", file=sys.stderr)
            read_stream, write_stream = TracedRead(read_stream), TracedWrite(write_stream)

        async with ClientSession(read_stream, write_stream) as session:
            # 1) 握手
            init = await session.initialize()
            show(
                "initialize 握手结果",
                {
                    "protocol_version": getattr(init, "protocol_version", None),
                    "server_info": {
                        "name": init.server_info.name,
                        "version": init.server_info.version,
                    },
                    "capabilities": sorted(init.capabilities.model_dump(exclude_none=True).keys()),
                    "instructions": init.instructions,
                },
            )

            # 2) 工具发现
            tools = await session.list_tools()
            show(
                "tools/list",
                [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "required": pick(tool, "input_schema", "inputSchema", default={}).get("required", []),
                        "properties": list(
                            pick(tool, "input_schema", "inputSchema", default={}).get("properties", {}).keys()
                        ),
                    }
                    for tool in tools.tools
                ],
            )

            # 3) 调用工具（查询 → 比较 → 报表，体现工具协作）
            current = await session.call_tool("query_weather", {"city": "北京", "days": 2})
            show("tools/call query_weather(city=北京, days=2)", _payload(current))

            comparison = await session.call_tool(
                "compare_weather", {"cities": ["北京", "上海", "三亚"], "units": "celsius"}
            )
            show("tools/call compare_weather(北京/上海/三亚)", _payload(comparison))

            report = await session.call_tool(
                "build_weather_report", {"city": "上海", "days": 3, "audience": "出行者"}
            )
            report_payload = _payload(report)
            if isinstance(report_payload, dict):
                show("tools/call build_weather_report(上海) → markdown", report_payload.get("markdown"))
            else:
                show("tools/call build_weather_report(上海)", report_payload)

            # 4) 资源读取
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            show(
                "resources/list 与 resources/templates/list",
                {
                    "resources": [str(item.uri) for item in resources.resources],
                    "templates": [
                        pick(item, "uri_template", "uriTemplate")
                        for item in pick(templates, "resource_templates", "resourceTemplates", default=[])
                    ],
                },
            )

            cities = await session.read_resource("weather://cities")
            profiles = await session.read_resource("weather://cities/beijing")
            show("resources/read weather://cities（截断）", cities.contents[0].text)
            show("resources/read weather://cities/beijing", profiles.contents[0].text)

            # 5) 提示模板
            prompts = await session.list_prompts()
            show("prompts/list", [{"name": p.name, "description": p.description} for p in prompts.prompts])

            prompt = await session.get_prompt(
                "weather_report_prompt", {"city": "广州", "days": "3", "audience": "农业生产者"}
            )
            show(
                "prompts/get weather_report_prompt(广州)",
                [getattr(message.content, "text", str(message.content)) for message in prompt.messages],
            )

    print("\n[client] 交互完成：stdio 子进程已按 MCP 规范关闭。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="天气 MCP Server 的 stdio 客户端")
    parser.add_argument("--offline", action="store_true", help="让服务端使用可复现的离线模拟数据")
    parser.add_argument("--trace", action="store_true", help="在 stderr 打印 JSON-RPC 报文")
    args = parser.parse_args(argv)
    return asyncio.run(run_client(args.offline, args.trace))


if __name__ == "__main__":
    raise SystemExit(main())
