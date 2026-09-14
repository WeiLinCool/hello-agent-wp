# Task-00 学习笔记：LLM 工具调用机制分析

## 问题 1：从 LLM 训练语料时效性出发，为什么要引入 `get_weather`、`get_attraction` 工具？

### 核心矛盾：训练数据的静态性 vs 现实世界的动态性

LLM 的知识完全来源于其训练语料，这带来了三个根本性限制：

| 限制 | 说明 | 本例中的体现 |
|------|------|-------------|
| **知识截止** | 模型只知道训练数据截止日期之前的信息 | LLM 无法知道"今天"北京的实时天气 |
| **无实时感知** | 模型无法主动获取当前世界的状态 | 无法查询此刻的温度、天气状况 |
| **无外部数据源** | 模型参数中不包含特定领域的结构化数据 | 无法获取 Tavily 搜索索引中的最新景点推荐 |

### 工具的本质：为 LLM 构建"外挂感知"

```
┌─────────────────────────────────────────────────┐
│                  LLM (静态知识)                   │
│  知道：北京是中国首都、故宫在北京市中心             │
│  不知道：今天北京 28°C、晴转多云                    │
└────────────┬──────────────────────────────────────┘
             │ 调用工具
             ▼
┌─────────────────────────────────────────────────┐
│              外部工具 (动态数据)                   │
│  get_weather()    → wttr.in API → 实时天气       │
│  get_attraction() → Tavily API → 实时景点推荐     │
└─────────────────────────────────────────────────┘
```

**总结**：引入工具的根本原因是 **LLM 的参数化记忆无法覆盖实时、动态、特定领域的数据需求**。工具充当了 LLM 与外部世界之间的桥梁，让模型在保持强大推理能力的同时，获得了对现实世界的"感知能力"。

---

## 问题 2：在 Prompt 中注入了工具，当前示例代码是如何让 LLM 调用工具的？

### 整体架构：ReAct 模式 + 正则解析

当前代码实现了一个经典的 **ReAct (Reasoning + Acting)** 循环，核心流程如下：

```
用户请求 ──► LLM思考(Thought) ──► 执行动作(Action) ──► 观察结果(Observation)
                    ▲                                          │
                    └──────────── 循环直到 Finish ◄────────────┘
```

### 具体实现步骤拆解

#### 步骤 1：Prompt 注入工具描述（System Prompt）

```python
AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手...

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`: 根据城市和天气搜索推荐的旅游景点。

# 输出格式要求:
Thought: [你的思考过程和下一步计划]
Action: [你要执行的具体行动]

Action的格式必须是以下之一：
1. 调用工具：function_name(arg_name="arg_value")
2. 结束任务：Finish[最终答案]
"""
```

> **关键**：工具的定义完全通过自然语言注入到 System Prompt 中，LLM 并不"原生"知道这些工具的存在。

#### 步骤 2：循环调用 LLM 并解析输出

```python
for i in range(5):  # 最多循环5次
    # 1. 将历史对话拼接为完整 prompt
    full_prompt = "\n".join(prompt_history)

    # 2. 调用 LLM
    llm_output = llm.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)

    # 3. 用正则截断多余的 Thought-Action 对
    match = re.search(r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|...))', llm_output, re.DOTALL)

    # 4. 用正则提取 Action
    action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)
```

#### 步骤 3：正则解析工具调用参数

```python
# 提取工具名：get_weather(city="北京")  →  "get_weather"
tool_name = re.search(r"(\w+)\(", action_str).group(1)

# 提取参数：city="北京"  →  {"city": "北京"}
args_str = re.search(r"\((.*)\)", action_str).group(1)
kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))
```

#### 步骤 4：执行工具并回注结果

```python
# 从字典中查找并执行工具函数
observation = available_tools[tool_name](**kwargs)

# 将结果作为 Observation 追加到历史记录
observation_str = f"Observation: {observation}"
prompt_history.append(observation_str)
```

### 完整调用链示意

```
第1轮:
  Prompt → LLM → "Thought: 需要先查天气
                   Action: get_weather(city="北京")"
  → 正则解析 → 执行 get_weather("北京")
  → Observation: "北京当前天气：晴，气温28摄氏度"

第2轮:
  Prompt(含历史) → LLM → "Thought: 天气晴，适合户外活动
                           Action: get_attraction(city="北京", weather="晴")"
  → 正则解析 → 执行 get_attraction("北京", "晴")
  → Observation: "推荐故宫、颐和园..."

第3轮:
  Prompt(含历史) → LLM → "Thought: 信息已足够
                           Action: Finish[今天北京天气晴朗...]"
  → 检测到 Finish → 输出最终答案 → 退出循环
```

---

## 问题 3：当前工具调用的缺陷，以及 DeepSeek-harness、opencode 的处理方式

### 当前实现的缺陷

#### 缺陷 1：正则解析极其脆弱

```python
# 当前代码：用正则匹配函数调用
tool_name = re.search(r"(\w+)\(", action_str).group(1)
args_str = re.search(r"\((.*)\)", action_str).group(1)
kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))
```

**问题**：
- 参数值只能匹配双引号字符串 `"..."` ，不支持数字、布尔值、嵌套对象
- 如果 LLM 输出 `get_weather(city='北京')` （单引号），解析失败
- 如果 LLM 输出 `get_weather("北京")` （位置参数而非关键字参数），解析失败
- 如果参数值中包含括号或引号，正则表达式会崩溃
- LLM 输出格式稍有偏差就会完全无法解析

#### 缺陷 2：没有结构化约束

- LLM 的输出是自由文本，工具调用完全依赖模型"记住"了 Prompt 中的格式要求
- 没有 JSON Schema 约束，模型可能输出不符合预期的格式
- 需要额外的正则截断逻辑来处理模型"话多"的情况

#### 缺陷 3：工具定义与执行耦合

```python
# 工具注册是硬编码的字典
available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}
```

- 新增工具需要同时修改 Prompt 文本和代码字典
- 没有统一的工具描述协议（Schema）
- 工具之间没有依赖管理

#### 缺陷 4：错误处理简陋

- 工具执行失败只返回错误字符串，没有重试机制
- 没有超时控制
- 没有工具调用的权限校验或沙箱隔离

### 开源项目的解决方案

#### DeepSeek-harness 的处理方式

DeepSeek-harness 采用 **原生 Function Calling API + 结构化 Agent 循环** 的方式：

| 维度 | 当前示例代码 | DeepSeek-harness |
|------|------------|-----------------|
| **工具定义** | 自然语言写在 Prompt 中 | 结构化 JSON Schema，通过 API 的 `tools` 参数传递 |
| **工具调用解析** | 正则表达式匹配文本 | 使用 OpenAI 兼容的 `function_call` / `tool_calls` 结构化响应 |
| **Agent 循环** | 简单的 for 循环 + 字符串拼接 | 完整的 Agent 循环框架，支持多轮对话、上下文管理 |
| **MCP 协议** | 不支持 | 支持 Model Context Protocol，工具可动态发现和注册 |
| **错误处理** | 返回错误字符串 | 结构化错误处理、重试、超时控制 |

**核心改进**：DeepSeek-harness 使用 LLM API 原生的 `tools` 参数（而非 Prompt 注入），让模型以结构化 JSON 格式返回工具调用，彻底消除了正则解析的脆弱性：

```python
# DeepSeek-harness 风格（使用原生 Function Calling）
response = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=[{                    # ← 结构化工具定义
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    }],
    tool_choice="auto"
)
# 响应中包含结构化的 tool_calls，无需正则解析
tool_call = response.choices[0].message.tool_calls[0]
tool_name = tool_call.function.name
tool_args = json.loads(tool_call.function.arguments)  # ← 保证是合法 JSON
```

#### opencode 的处理方式

opencode（终端 AI 编码助手）同样采用 **原生 Tool Use + 类型安全** 的方案：

| 维度 | 当前示例代码 | opencode |
|------|------------|----------|
| **工具定义** | Prompt 文本 | TypeScript 类型定义 + JSON Schema |
| **调用解析** | 正则匹配 | LLM 原生 tool_use 结构化输出 |
| **执行安全** | 直接调用 Python 函数 | 权限审批机制，危险操作需用户确认 |
| **工具生态** | 硬编码 2 个工具 | 插件化工具系统，支持社区扩展 |
| **上下文管理** | 简单字符串拼接 | 完整的对话历史管理、token 预算控制 |

**核心改进**：opencode 将每个工具定义为带有完整输入/输出 Schema 的类型安全模块：

```typescript
// opencode 风格（TypeScript 类型安全的工具定义）
const getWeatherTool = {
  name: "get_weather",
  description: "查询指定城市的实时天气",
  parameters: z.object({           // ← Zod Schema 类型安全
    city: z.string().describe("城市名称"),
  }),
  execute: async (args) => {       // ← 类型安全的执行函数
    const result = await fetchWeather(args.city);
    return { weather: result.description, temp: result.temp };
  },
};
```

### 总结对比

```
                    演进路线
                    
  当前示例代码          DeepSeek-harness / opencode
  ──────────          ──────────────────────────
  
  Prompt 文本注入  ──►  原生 Function Calling API
  正则解析输出    ──►  结构化 JSON Schema 响应
  硬编码工具字典  ──►  动态工具注册 / MCP 协议
  字符串拼接历史  ──►  完整 Agent 循环框架
  无安全控制     ──►  权限审批 + 沙箱隔离
  无错误恢复     ──►  重试 + 超时 + 降级策略
```

**核心启示**：当前示例代码展示了一个最小可行的 Agent 实现，其价值在于让我们理解工具调用的本质——**让 LLM 的推理能力与外部世界的实时数据相连接**。而现代开源项目的改进方向，本质上是在**可靠性、安全性、可扩展性**三个维度上对这一基本模式的工程化升级。
