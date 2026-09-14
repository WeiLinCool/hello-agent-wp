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

DeepSeek-harness 是一个 AI Agent 运行时框架（TypeScript），采用 **自定义 Schema DSL + 原生 Function Calling + 流式 Agent 循环 + 沙箱执行** 的架构：

**1. 工具定义：自定义 Schema DSL（非原始 JSON Schema）**

工具通过 `defineTool()` 工厂函数定义，使用自定义的类型安全 Schema DSL，编译为 JSON Schema：

```typescript
// packages/core/tools/src/schema.ts
defineTool({
  name: 'bash',
  description: 'Run a bash command',
  parameters: {
    command: { type: 'string', description: '...', required: true },
    timeoutMs: { type: 'number', description: '...' },
  },
  output: {
    schema: { type: 'object', properties: { stdout: { type: 'string' } } },
    render: (args, value) => [{ type: 'text', text: value.stdout }],
  },
  execute: async (args, exec) => { /* ... */ },
})
```

特点：
- **类型推断**：通过 TypeScript 条件类型（`InferValue<S>`, `InferArgs<S>`）在编译期推断参数类型
- **输出 Schema**：每个工具声明规范化输出 + `render()` 函数将 JSON 投影为模型可见的 `ContentBlock[]`
- **运行时校验**：参数通过 `validateJsonSchemaValue()` 校验，无效参数抛出 `ToolArgsError`

**2. 工具注册：分层服务 + MCP 桥接**

`ToolRuntime` 是一个 Cordis DI 服务，支持分层注册：

```typescript
// packages/core/tools/src/index.ts
class ToolRuntime extends Service {
  register(definition: ToolDefinition): () => void  // 返回 disposer
  restrict({ allow?, deny? }): void                  // 按作用域屏蔽工具
  guard(fn): void                                    // 注册单调拒绝守卫
}
```

- **作用域隔离**：工具可全局注册或按 Agent 作用域注册，作用域内工具遮蔽全局
- **MCP 桥接**：`syncTools()` 从 MCP 服务器获取工具，包装为 `mcp__<serverName>__<rawName>` 格式
- **展示模式**：`'native'`（发送全部 Schema 给模型）、`'ptc'`（仅核心工具 + Prompt）、`'both'`

**3. 工具调用解析：原生流式 Function Calling**

完全不使用正则，通过适配器层解析各 LLM 提供商的原生 tool_calls：

```typescript
// packages/llm/llm-deepseek/src/translate.ts
// DeepSeek 适配器：SSE → StreamChunk
export async function* translate(payloads: AsyncIterable<string>): AsyncGenerator<StreamChunk>
// 解析 delta.tool_calls[]，累积 function.name 和 function.arguments
// 输出: block-start → tool-call-delta → block-end → finish

// packages/llm/llm/src/assembler.ts
// BlockAssembler：将 StreamChunk 增量组装为 ContentBlock[]
// 最终产出: { type: 'tool-call', id, name, arguments: string(JSON) }
```

**4. Agent 循环：Turn → Step → Request → Tool Execution**

```
kick() → while(await turn()) {}
  turn():
    while (true):
      step = phase.step + 1
      decision = await preStep(target, {turn, step})
      stepEnd = await step(decision)
      if (turnEnds) break

  step(decision):
    request = buildRequest(config, tools, messages)
    stream = ctx.llm.stream(request)
    message = createAssistantMessage({ content: live.blocks() })

    toolCalls = message.content.filter(b => b.type === 'tool-call')
    if (toolCalls.length === 0) return 'completed'

    { concluded } = await executeToolCalls(ctx, turn, step, toolCalls, ...)
    return concluded ? 'completed' : null  // null = 继续下一轮 step
```

**工具调度器**（`tool-calls.ts`）：
- **并行 vs 独占**：工具通过 `isConcurrencySafe(args)` 分类，并行工具使用有界滚动池（`maxParallelToolCalls`），独占工具形成屏障
- **模型顺序提交**：结果按模型原始调用顺序提交，即使执行有重叠
- **中止处理**：为跳过的调用记录合成错误结果

**5. 错误处理与重试**

**LLM 请求重试**（`retry-policy.ts`）：
- 有界重试（默认 5 次），指数退避 + 抖动（500ms → 10s）
- 可重试条件：`EMPTY_RESPONSE`, `RATE_LIMIT`, `SERVER`, `TIMEOUT`, `TRANSPORT`

**工具错误类型体系**：
| 错误类型 | 触发条件 | 处理 |
|---------|---------|------|
| `ToolNotFoundError` | 工具名不存在 | 错误信息发给模型自我纠正 |
| `ToolArgsError` | 参数校验失败 | 违规信息作为错误返回 |
| `ToolOutputError` | 输出不符合 Schema | 规范化错误 |
| `ToolExecutionFailure` | 工具执行抛异常 | 错误消息文本化 |
| 前置拒绝（deny） | 权限守卫拒绝 | `"Error: {reason}"` |
| 后置阻断（block） | 执行后审查拒绝 | 纠正性反馈作为错误 |

**关键设计**：所有工具错误都转化为模型可见的文本 `"Error: {message}"`，让模型能够自我纠正。

**6. 安全与沙箱**

- 文件操作有沙箱权限控制（read-only / workspace-write / danger-full-access）
- 工具执行有超时控制（`timeoutMs` 参数）
- 敏感操作需要用户审批（approval prompt）
- 单调拒绝守卫（monotonic denial guard）：一旦拒绝，同类操作不可绕过

**关键源码文件**：
| 关注点 | 文件路径 |
|--------|---------|
| 工具定义 DSL | `packages/core/tools/src/schema.ts` |
| 工具注册 & 管道 | `packages/core/tools/src/index.ts` |
| Agent 循环 | `packages/core/agent-loop/src/agent.ts` |
| 工具调用调度 | `packages/core/agent-loop/src/tool-calls.ts` |
| 流组装器 | `packages/llm/llm/src/assembler.ts` |
| DeepSeek 适配器 | `packages/llm/llm-deepseek/src/translate.ts` |
| 重试策略 | `packages/llm/llm/src/retry-policy.ts` |
| MCP 工具桥接 | `packages/mcp/mcp-client/src/tools.ts` |

#### opencode 的处理方式

opencode（`anomalyco/opencode`，207k stars，TypeScript，MIT 协议）是一个终端 AI 编码助手，采用 **Vercel AI SDK 原生 Function Calling + Effect 类型系统 + 流式 Agent 循环** 的架构：

**1. 工具定义：Effect Schema 类型安全**

每个工具使用 Effect 的 `Schema` 进行参数验证，编译为高效的解码器：

```typescript
export interface Def<Parameters, M> {
  id: string
  description: string
  parameters: Parameters           // ← Effect Schema 解码器
  jsonSchema?: JSONSchema7         // ← 预计算的 JSON Schema
  execute(args, ctx): Effect.Effect<ExecuteResult<M>>
  formatValidationError?(error: unknown): string
}
```

**2. 工具注册：分层服务架构**

`ToolRegistry` 是一个 Effect `Layer` 服务，按层加载工具：
1. 内置工具（shell, read, edit, write, glob, grep, webfetch, websearch 等）
2. 项目自定义工具（`.opencode/tool/*.ts` 文件）
3. 插件工具
4. MCP 服务器工具
5. 按模型能力过滤（如 GPT 模型用 `apply_patch` 替代 `edit`/`write`）
6. 按权限规则过滤

**3. 工具调用解析：Vercel AI SDK 原生处理**

opencode **完全不使用正则或结构化输出解析**，而是通过 Vercel AI SDK 的 `streamText()` 处理：

```typescript
streamText({
  model: wrapLanguageModel({ model: language, middleware: [...] }),
  tools: prepared.tools,
  toolChoice: input.toolChoice,
  messages: prepared.messages,
})
```

AI SDK 自动处理各提供商的协议差异（Anthropic 的 XML 格式、OpenAI 的 function calling、Google 的 function calling），输出统一的 `tool-call`/`tool-result` 事件流。

**4. 工具调用修复机制**

当工具调用验证失败时，opencode 有专门的修复机制：

```typescript
async experimental_repairToolCall(failed) {
  // 1. 尝试大小写修复
  const lower = failed.toolCall.toolName.toLowerCase()
  if (lower !== failed.toolCall.toolName && prepared.tools[lower]) {
    return { ...failed.toolCall, toolName: lower }
  }
  // 2. 路由到 InvalidTool，返回错误让 LLM 自我纠正
  return {
    ...failed.toolCall,
    input: JSON.stringify({ tool: failed.toolCall.toolName, error: failed.error.message }),
    toolName: "invalid",
  }
}
```

**5. Agent 循环：Effect 流式管道 + 末日循环检测**

- 流式处理 LLM 事件（`tool-input-start` → `tool-input-delta` → `tool-call` → `tool-result`）
- **末日循环检测**（Doom Loop Detection）：如果同一工具用相同参数连续调用 3 次，触发用户确认
- 上下文溢出时自动压缩（context compaction）
- 支持权限审批，危险操作需用户确认

**6. 错误处理与重试**

- **指数退避重试**：基础延迟 2000ms × 2^(attempt-1)，25% 随机抖动
- 尊重 `Retry-After` 响应头
- 最多重试 5 次，最大延迟 30 秒
- 可重试条件：HTTP 429/500/502/503/504、速率限制、网络错误、超时

### 三者对比总结

| 维度 | 当前示例代码 | DeepSeek-harness | opencode |
|------|------------|-----------------|----------|
| **工具定义** | Prompt 自然语言 | JSON Schema | Effect Schema + JSON Schema |
| **调用解析** | 正则表达式 | 原生 Function Calling | Vercel AI SDK 原生处理 |
| **Agent 循环** | for 循环 + 字符串拼接 | 完整会话管理 + 子 Agent | Effect 流式管道 |
| **错误处理** | 返回错误字符串 | 结构化错误 + 重试 | 指数退避 + 调用修复 + InvalidTool |
| **安全控制** | 无 | 沙箱权限 + 审批 | 权限规则集 + 用户确认 |
| **工具生态** | 硬编码 2 个 | 内置 + MCP + Skill | 内置 + 自定义 + 插件 + MCP |
| **上下文管理** | 字符串拼接 | 对话历史 + 压缩 | 流式事件 + 自动压缩 |
| **循环检测** | 无 | 无 | 末日循环检测（3次阈值） |
| **实现语言** | Python | TypeScript | TypeScript (Effect) |

### 演进路线

```
当前示例代码              DeepSeek-harness              opencode
──────────              ──────────────────              ────────

Prompt 文本注入    ──►   原生 Function Calling    ──►   AI SDK 统一抽象层
正则解析输出       ──►   结构化 JSON Schema 响应  ──►   Schema 编译解码器
硬编码工具字典     ──►   内置 + MCP 动态注册      ──►   分层服务 + 插件系统
字符串拼接历史     ──►   完整 Agent 循环框架      ──►   Effect 流式管道
无安全控制        ──►   沙箱权限 + 审批机制      ──►   规则集 + 用户确认
无错误恢复        ──►   结构化错误处理           ──►   指数退避 + 调用修复
```

### 核心启示

当前示例代码展示了一个**最小可行的 Agent 实现**，其价值在于让我们理解工具调用的本质——**让 LLM 的推理能力与外部世界的实时数据相连接**。

而 DeepSeek-harness 和 opencode 的改进方向，本质上是在三个维度上的工程化升级：

1. **可靠性**：从脆弱的正则解析 → 原生 Function Calling → 调用修复 + 末日循环检测
2. **安全性**：从无控制 → 沙箱隔离 → 细粒度权限规则集
3. **可扩展性**：从硬编码 → MCP 动态注册 → 分层服务 + 插件生态
