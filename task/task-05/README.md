# Task 05：天气查询 MCP Server（stdio 本地模式）

本章习题（第 10 章·智能体通信协议）第 2 题是动手实践题。本目录给出了一个**可真实运行**的
MCP Server 实现：以"天气查询"作为工具能力，采用 **JSON-RPC 2.0 over stdio** 的本地进程间通信模式。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| [weather_mcp_server.py](weather_mcp_server.py) | MCP Server 本体（Tools + Resources + Prompts），默认 stdio 传输 |
| [weather_mcp_client.py](weather_mcp_client.py) | MCP 客户端：启动服务器子进程，走完整交互流程；`--trace` 可打印 JSON-RPC 报文 |
| [test_weather_mcp_server.py](test_weather_mcp_server.py) | 端到端测试（真实 stdio 子进程），43 项检查，无需 pytest |
| [demo.py](demo.py) | 第 1/3/4/5 题的概念演示（协议对比、A2A 协作、ANP 拓扑与容错、安全机制） |
| [exercise-answer.md](exercise-answer.md) | 习题解答（含 2.4 节：本实现的设计与验证说明） |

## 快速开始

```bash
cd task/task-05
source venv/bin/activate          # 依赖：mcp 2.2.0（requirements.txt 已声明）

# 1) 端到端测试（离线、可复现）
python test_weather_mcp_server.py

# 2) 跑一遍完整交互（initialize → tools/list → tools/call → resources → prompts）
python weather_mcp_client.py --offline

# 3) 观察 stdio 上的 JSON-RPC 报文
python weather_mcp_client.py --offline --trace

# 4) 作为 MCP Server 供其他 MCP 客户端（Claude Desktop / Cursor / mcp CLI 等）使用
python weather_mcp_server.py                 # 默认 stdio，stdout 只承载 JSON-RPC
python weather_mcp_server.py --offline       # 强制离线模拟数据
python weather_mcp_server.py --transport streamable-http --port 8000   # 远程扩展（第 2.3 问）
```

## 对外暴露的能力

**Tools（3 个，相互复用同一条数据链路 → 体现"工具协作"）**

| 工具 | 说明 | 关键参数 |
| --- | --- | --- |
| `query_weather` | 实时天气 + 未来 N 天预报 | `city`, `days`(1-7), `units`(celsius/fahrenheit) |
| `compare_weather` | 多城市对比并给出气温排名（复用 `query_weather` 核心逻辑） | `cities`(≤10), `units` |
| `build_weather_report` | 生成 Markdown 天气报告（查询 → 分析 → 报表链路末端） | `city`, `days`, `audience` |

**Resources**

- `weather://cities`：内置城市目录（10 个城市，离线可用）
- `weather://cities/{city}`：单城市档案（坐标、气候备注），支持中文名 / 英文名 / key

**Prompts**

- `weather_report_prompt(city, days, audience)`：把"查天气 → 写报告"的流程固化成提示模板

## 数据来源与可靠性

- 默认调用免费的 [Open-Meteo](https://open-meteo.com/) API（无需 API Key）：先用 Geocoding 解析城市，再取实时/预报数据。
- 网络不可用或 `--offline` 时，自动回退到**确定性模拟数据**，结果中 `source` 字段标明
  `open-meteo` 或 `offline-mock`，做到"离线也能演示、测试可复现"。
- 可预期错误（城市未收录、`days` 越界）抛 SDK 的 `ToolError`，客户端收到 `isError=true`
  且**错误原文对模型可见**（普通异常只会得到 `Error executing tool xxx`）。

## 验证结果

```
$ python test_weather_mcp_server.py
共 43 项检查，通过 43 项，失败 0 项
```

覆盖：握手与能力声明、3 个工具及 JSON Schema、离线确定性、摄氏度↔华氏度换算、
参数校验与错误返回、多城市降级策略、Markdown 报告、资源与资源模板读取、提示模板填充。

## SDK 版本说明

`mcp 2.x` 将 `FastMCP` 改名为 `MCPServer`（`from mcp.server.mcpserver import MCPServer`）。
本实现以 2.x 为主，同时保留 1.x 的兼容导入；真实运行环境为 `mcp 2.2.0`。
