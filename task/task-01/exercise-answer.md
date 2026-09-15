# 智能体范式与工程实践 —— 课后练习深度解答

> **阅读指引**：本文档以「费曼学习法」为组织原则——先用一句话和类比建立直觉，再深入技术细节，最后用工程实例验证理解。每道题的答案都遵循 **"是什么 → 为什么 → 怎么做"** 的三层结构。本文是与AI结对思考由AI主要编写而成。

---

## 目录

- [练习 1：三种经典智能体范式对比](#练习-1三种经典智能体范式对比)
- [练习 2：ReAct 输出解析的脆弱性与改进](#练习-2react-输出解析的脆弱性与改进)
- [练习 3：工具调用的扩展实践](#练习-3工具调用的扩展实践)
- [练习 4：Plan-and-Solve 范式深入分析](#练习-4plan-and-solve-范式深入分析)
- [练习 5：Reflection 机制的优化设计](#练习-5reflection-机制的优化设计)
- [练习 6：提示词工程的对比与实践](#练习-6提示词工程的对比与实践)
- [练习 7：电商客服智能体综合设计](#练习-7电商客服智能体综合设计)

---

## 练习 1：三种经典智能体范式对比

### 1.1 三种范式在"思考"与"行动"组织方式上的本质区别

> **一句话理解**：ReAct 像"边走边看"的探险家，Plan-and-Solve 像"先画地图再出发"的旅行者，Reflection 像"写完论文请导师审稿"的研究生。

| 维度 | ReAct | Plan-and-Solve | Reflection |
|------|-------|----------------|------------|
| **核心循环** | Thought → Action → Observation（交替进行） | Plan → Execute（两阶段分离） | Execute → Reflect → Refine（迭代优化） |
| **思考方式** | 每一步行动前做一次即时推理 | 先一次性全局规划，再逐步执行 | 执行后回顾，从错误中学习 |
| **行动特点** | 走一步看一步，根据观察结果决定下一步 | 按预设计划顺序执行，步骤间相对独立 | 反复修改同一产出，追求质量提升 |
| **信息利用** | 实时利用每步 Observation 调整方向 | 规划时不利用执行反馈（静态计划） | 利用历史轨迹（trajectory）自我改进 |
| **适用场景** | 需要与环境持续交互的任务 | 可预先分解的多步骤推理任务 | 需要质量迭代的生成类任务 |

**类比理解**：

```
ReAct         = 出租车司机（根据路况实时决策）
Plan-and-Solve = 导航软件（先规划路线，再逐步引导）
Reflection    = 代码审查（写完代码 → 评审 → 修改 → 再评审）
```

**本质区别的核心**：三者的根本差异在于 **「思考」与「行动」的时间关系**：

- **ReAct**：思考与行动 **交织**（interleaved），每步都有思考
- **Plan-and-Solve**：思考与行动 **分离**（separated），先集中思考，再集中行动
- **Reflection**：思考在行动 **之后**（post-hoc），是对已完成行动的再思考

---

### 1.2 智能家居控制助手的范式选择

> **结论**：选择 **ReAct** 作为基础架构，辅以 Reflection 做策略优化。

**为什么选 ReAct？**

智能家居场景的核心特征是 **环境状态实时变化 + 需要即时响应**，这恰好是 ReAct 的主场：

```
用户说："我觉得有点热"
  → Thought: 用户觉得热，需要降低室温。当前室温28°C，目标是25°C。
             应该先检查空调状态，再决定如何调节。
  → Action: 查询空调状态()
  → Observation: 空调已开启，制冷模式，设定温度27°C，当前室温28°C
  → Thought: 空调已在制冷但温度设定偏高，需要调低设定温度，
             同时检查窗帘是否关闭（阳光直射会影响降温效果）
  → Action: 查询窗帘状态()
  → Observation: 客厅窗帘打开中
  → Thought: 窗帘开着导致阳光直射，应该先关窗帘再调低空调温度
  → Action: 关闭窗帘()
  → Observation: 窗帘已关闭
  → Action: 设置空调温度(24)
  → Observation: 空调温度已设置为24°C
  → Thought: 已完成调节，告知用户
  → Final Answer: "已为您关闭窗帘并将空调调至24°C，稍后室温会降低。"
```

**为什么不用其他范式？**

- **Plan-and-Solve 的问题**：家居环境是动态的（人可能走进房间、天气可能突变），一次性规划无法应对实时变化。就像你不能在出门前就规划好一整天每一步怎么走——路况随时在变。
- **Reflection 的问题**：控制设备需要即时响应，不能等"反思"完再执行。你不能先"反思"一下要不要开灯，让用户在黑暗中等30秒。

**混合增强方案**：

```
┌──────────────────────────────────────────────────────────────┐
│                 智能家居混合架构（含记忆注入）                  │
│                                                              │
│   memory.md ──► Prompt 构建时注入 ──┐                        │
│                                     │                        │
│  ┌──────────────────────────────────▼───────────────────┐   │
│  │              ReAct 核心（实时控制）                    │   │
│  │   System Prompt 中显式包含 {memory_context} 占位符    │   │
│  └───────────────────────┬──────────────────────────────┘   │
│                          │ 执行轨迹                          │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Reflection 后台（定期策略优化）                │   │
│  │   分析执行轨迹 → 提炼用户习惯 → 写入 memory.md        │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              设备层（灯 / 空调 / 窗帘）                │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

- **ReAct** 负责实时设备控制（即时响应）
- **Reflection** 在后台定期分析用户行为模式，将洞察沉淀到 `memory.md`
- **关键**：`memory.md` 必须在 ReAct 的 **Prompt 构建阶段** 被注入，否则记忆形同虚设

#### ⚠️ 长期记忆的注入时机：为什么"存了"不等于"用了"

> **核心洞察**：Reflection 沉淀的用户习惯（memory.md）只是一份「静态文档」。如果 ReAct 的 Prompt 模板中没有显式设计「读取并引用 memory.md」的环节，这些记忆就是**死数据**——存了但永远不会影响决策。

**记忆注入的完整数据流**：

```
时间轴 ─────────────────────────────────────────────────────────►

[T0] 用户操作：22:00 调暗客厅灯光
      │
      ▼
[T1] ReAct 执行控制（此时 Prompt 中已注入 memory.md）
      │  Thought: memory.md 记录用户偏好 22:00 后灯光调至 30%
      │  Action: 设置灯光亮度(30%)
      │
      ▼
[T2] 执行轨迹写入 execution_log.md
      │
      ▼
[T3] Reflection 后台任务触发（每日/每周）
      │  分析 execution_log.md，发现规律
      │  "用户连续 5 天 22:00 调暗灯光至 30%"
      │
      ▼
[T4] Reflection 输出洞察，**写入 memory.md**
      │  ## 用户习惯 - 灯光
      │  - 22:00 后偏好客厅灯光亮度 30%
      │  - 工作日 vs 周末无显著差异
      │
      ▼
[T5] 次日 T1 时刻，ReAct Prompt 构建时 **重新读取 memory.md**
      │  → 记忆生效：主动建议 "需要帮您把灯光调暗吗？"
      └──► 循环回到 [T1]
```

**三个关键注入时机**：

| 时机 | 触发条件 | 注入方式 | 作用 |
|------|---------|---------|------|
| **① Prompt 构建时** | 每次 ReAct 循环启动前 | 将 memory.md 相关内容拼入 System Prompt | 让 LLM 在推理时"看到"历史习惯 |
| **② Thought 引导时** | ReAct 每轮 Thought 生成前 | 在 Prompt 中设置"请先查阅用户习惯"的指令 | 强制模型主动引用记忆 |
| **③ Action 校验时** | 模型输出 Action 后、执行前 | 用 memory.md 中的规则校验 Action 是否违背已知偏好 | 防止模型"忘记"记忆做出反常操作 |

**Prompt 模板的正确设计**（对比反例）：

```python
# ❌ 错误示范：Prompt 中没有引用 memory.md 的位置
REACT_PROMPT = """
你是一个智能家居助手。根据用户需求控制设备。
可用工具：{tools}
Question: {question}
"""
# 问题：即使 memory.md 存在，模型也看不到里面的内容

# ✅ 正确示范：显式注入记忆上下文
REACT_PROMPT_WITH_MEMORY = """
你是一个智能家居助手。根据用户需求控制设备。

## 用户习惯记忆（来自 memory.md）
{memory_context}
<!-- 这部分由系统在 Prompt 构建时动态填充 -->
<!-- 如果 memory.md 为空，则注入 "暂无历史习惯记录" -->

## 重要指令
在每次 Thought 中，你必须先检查上述用户习惯记忆，
判断当前操作是否与已知偏好一致。如有冲突，优先遵循用户当前明确指令，
但在 Thought 中标注冲突。

## 可用工具
{tools}

Question: {question}
"""

# 记忆注入的代码实现
def build_react_prompt(question: str, tools: str, memory_path: str = "memory.md") -> str:
    """构建 ReAct Prompt，关键步骤：读取并注入 memory.md"""
    
    # 步骤 1：读取长期记忆
    try:
        with open(memory_path, 'r', encoding='utf-8') as f:
            memory_content = f.read().strip()
    except FileNotFoundError:
        memory_content = "暂无历史习惯记录"
    
    # 步骤 2：相关性过滤（可选优化）
    # 当 memory.md 很大时，用 embedding 检索与当前问题相关的片段
    # 避免塞入全部记忆导致 token 爆炸
    memory_context = retrieve_relevant_memories(memory_content, question)
    
    # 步骤 3：注入 Prompt 模板
    return REACT_PROMPT_WITH_MEMORY.format(
        memory_context=memory_context or "暂无相关习惯记录",
        tools=tools,
        question=question,
    )
```

**记忆写入侧的实现**（Reflection → memory.md）：

```python
class MemoryWriter:
    """
    Reflection 完成分析后，将洞察结构化写入 memory.md。
    注意：不是追加原始日志，而是提炼为可被 Prompt 直接引用的格式。
    """
    
    MEMORY_TEMPLATE = """# 用户习惯记忆库

## 设备偏好
{device_preferences}

## 时间规律
{time_patterns}

## 场景联动
{scene_rules}

---
*最后更新: {last_updated}*
*数据基础: 最近 {days_analyzed} 天的交互记录*
"""
    
    def update_memory(self, reflection_insights: dict):
        """
        将 Reflection 的输出转化为结构化记忆。
        
        reflection_insights 示例:
        {
            "device_preferences": ["客厅灯光 22:00 后偏好 30% 亮度", ...],
            "time_patterns": ["工作日 07:30 自动开启咖啡机", ...],
            "scene_rules": ["观影模式 = 灯光 10% + 窗帘关闭 + 空调 25°C", ...],
        }
        """
        content = self.MEMORY_TEMPLATE.format(
            device_preferences=self._format_list(
                reflection_insights.get("device_preferences", [])),
            time_patterns=self._format_list(
                reflection_insights.get("time_patterns", [])),
            scene_rules=self._format_list(
                reflection_insights.get("scene_rules", [])),
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
            days_analyzed=reflection_insights.get("days_analyzed", 7),
        )
        
        with open("memory.md", 'w', encoding='utf-8') as f:
            f.write(content)
```

> **费曼检验**：把 memory.md 想象成一本「员工手册」。Reflection 是「经验总结会」，ReAct 是「一线员工」。如果开完会写了手册，但员工上岗前不要求读手册——那会议开得再好也没用。**注入时机 = 员工上岗前的必读环节**。

---

### 1.3 三种范式的混合架构设计

> **核心思想**：不同范式解决不同维度的问题，混合使用的关键是 **明确每层的职责边界**。

#### 混合架构：PR³（Plan-React-Reflect-Revise）

```
                    ┌──────────────────────┐
                    │   用户输入 / 触发事件  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Phase 1: Plan       │
                    │  全局任务分解         │
                    │  "做什么、什么顺序"    │
                    └──────────┬───────────┘
                               │ 计划步骤列表
                    ┌──────────▼───────────┐
                    │  Phase 2: React      │
                    │  逐步执行 + 实时推理   │
                    │  "怎么做、根据反馈调整" │
                    └──────────┬───────────┘
                               │ 执行结果
                    ┌──────────▼───────────┐
                    │  Phase 3: Reflect    │
                    │  质量评估 + 问题诊断   │
                    │  "做得好不好"          │
                    └──────────┬───────────┘
                               │ 反馈
                        ┌──────▼──────┐
                        │ 需要修正？   │
                        └──┬──────┬───┘
                      Yes  │      │ No
                           │      │
                    ┌──────▼──┐ ┌─▼──────────┐
                    │ Revise  │ │  输出最终结果 │
                    │ 修正计划 │ └────────────┘
                    │ 回到 P2  │
                    └─────────┘
```

**适用场景示例**：「帮我策划并执行一场线上产品发布会」

| 阶段 | 范式 | 具体工作 |
|------|------|---------|
| Plan | Plan-and-Solve | 分解为：确定议程 → 邀请嘉宾 → 准备演示 → 测试设备 → 发送通知 |
| React | ReAct | 执行"邀请嘉宾"时，根据每位嘉宾的回复实时调整备选名单 |
| Reflect | Reflection | 彩排后审查流程，发现转场时间过长，提出优化建议 |
| Revise | 回到 Plan | 根据反馈修改时间表，重新进入 React 执行 |

---

## 练习 2：ReAct 输出解析的脆弱性与改进

### 2.1 当前正则解析方法的潜在脆弱性

> **一句话总结**：正则解析依赖 LLM 输出严格遵循固定格式，但 LLM 本质是概率模型，无法保证 100% 格式一致。

**具体脆弱性分析**：

| 脆弱性类型 | 失败场景 | 示例 |
|-----------|---------|------|
| **格式漂移** | 模型偶尔改变输出格式 | 输出 `Thought: 我想...` 而非 `Thought: 我想...`（多了空格或换行） |
| **语言混淆** | 模型在 Thought 中使用 Action 关键词 | `Thought: 我应该使用 Search 工具来搜索` → 正则可能误匹配 |
| **多步输出** | 模型一次输出多个 Thought-Action 对 | 一次返回了两组 Thought/Action，正则只匹配第一组 |
| **特殊字符** | 搜索内容包含正则特殊字符 | `Action: Search["什么是正则表达式?"]` 中的 `?` 和 `[]` |
| **空输出/截断** | API 超时或 token 限制导致输出不完整 | 只输出了 `Thought: 我需要` 就截断了 |
| **Markdown 污染** | 模型用 markdown 格式包裹输出 | 输出 ````Thought: ...```` 或 `**Thought**: ...` |

**代码层面的问题**（参考本章实现）：

```python
# 典型的正则解析代码
thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|$)', response, re.DOTALL)
action_match = re.search(r'Action:\s*(\w+)\[(.+?)\]', response)
```

这段代码的问题：
1. `(.+?)` 是非贪婪匹配，如果 Thought 内容中包含 "Action:" 字样会提前截断
2. `(\w+)` 不支持包含空格或中文的工具名
3. `(.+?)` 在 Action 参数中不支持嵌套方括号
4. 没有处理匹配失败的 fallback 逻辑

---

### 2.2 更鲁棒的输出解析方案

| 方案 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| **JSON 模式** | 要求模型输出结构化 JSON | 解析可靠，schema 可验证 | 部分模型不支持强制 JSON 输出 |
| **Function Calling** | 使用模型原生的函数调用能力 | 最可靠，类型安全 | 依赖特定模型供应商的 API |
| **XML 标签** | 用 XML 标签包裹各部分 | 比正则更结构化，支持嵌套 | 比 JSON 冗长 |
| **分隔符 + 状态机** | 用明确分隔符 + 状态机解析 | 灵活，容错性好 | 需要更多工程代码 |
| **Pydantic + LLM** | 用 Pydantic schema 约束输出 | 类型安全，自动验证 | 增加依赖和复杂度 |

**推荐方案：Function Calling（首选）或 JSON 模式（通用）**

---

### 2.3 代码改进：使用 JSON 结构化输出

```python
import json
from typing import Optional, Literal
from pydantic import BaseModel, Field

# ===== 方案 A：使用 Pydantic 定义结构化输出 =====

class ReActStep(BaseModel):
    """ReAct 单步输出的结构化定义"""
    thought: str = Field(description="当前步骤的推理过程")
    action: Optional[str] = Field(None, description="要调用的工具名称，如果是最终答案则为 null")
    action_input: Optional[str] = Field(None, description="工具的输入参数")
    final_answer: Optional[str] = Field(None, description="最终答案（仅在有最终答案时填写）")

# ===== 方案 B：健壮的解析器 =====

class ReActParser:
    """
    多层 fallback 的 ReAct 输出解析器。
    策略：JSON > XML标签 > 正则 > 原始文本
    """
    
    def parse(self, raw_output: str) -> ReActStep:
        """尝试多种策略解析 LLM 输出，返回结构化结果"""
        
        # 策略 1：尝试直接 JSON 解析
        try:
            cleaned = self._extract_json(raw_output)
            return ReActStep.model_validate_json(cleaned)
        except Exception:
            pass
        
        # 策略 2：尝试 XML 标签解析
        try:
            return self._parse_xml_tags(raw_output)
        except Exception:
            pass
        
        # 策略 3：尝试正则解析（带容错）
        try:
            return self._parse_regex(raw_output)
        except Exception:
            pass
        
        # 策略 4：降级为纯文本（将整个输出视为 thought）
        return ReActStep(
            thought=raw_output.strip(),
            action=None,
            final_answer=raw_output.strip()
        )
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON 块"""
        # 尝试提取 ```json ... ``` 代码块
        if "```json" in text:
            return text.split("```json")[1].split("```")[0].strip()
        # 尝试提取 { ... } 
        start = text.index("{")
        end = text.rindex("}") + 1
        return text[start:end]
    
    def _parse_xml_tags(self, text: str) -> ReActStep:
        """解析 XML 标签格式的输出"""
        import re
        thought = re.search(r'<thought>(.*?)</thought>', text, re.DOTALL)
        action = re.search(r'<action>(.*?)</action>', text, re.DOTALL)
        action_input = re.search(r'<action_input>(.*?)</action_input>', text, re.DOTALL)
        final = re.search(r'<final_answer>(.*?)</final_answer>', text, re.DOTALL)
        
        return ReActStep(
            thought=thought.group(1).strip() if thought else "",
            action=action.group(1).strip() if action else None,
            action_input=action_input.group(1).strip() if action_input else None,
            final_answer=final.group(1).strip() if final else None,
        )
    
    def _parse_regex(self, text: str) -> ReActStep:
        """改进的正则解析（处理更多边界情况）"""
        import re
        # 使用更宽松的匹配模式
        thought = re.search(r'Thought\s*:\s*(.+?)(?=\n\s*Action\s*:|\n\s*Final\s*Answer\s*:|$)', 
                           text, re.DOTALL)
        action = re.search(r'Action\s*:\s*([^\[]+)\[(.+?)\]', text, re.DOTALL)
        final = re.search(r'Final\s*Answer\s*:\s*(.+)', text, re.DOTALL)
        
        return ReActStep(
            thought=thought.group(1).strip() if thought else "",
            action=action.group(1).strip() if action else None,
            action_input=action.group(2).strip() if action else None,
            final_answer=final.group(1).strip() if final else None,
        )

# ===== 两种方案的对比 =====
"""
| 维度           | 正则解析（原方案）          | JSON + 多层 Fallback（改进方案）    |
|---------------|--------------------------|----------------------------------|
| 可靠性         | 低（格式稍有变化就失败）    | 高（多层 fallback 兜底）           |
| 可维护性       | 低（正则难以阅读和修改）    | 高（Pydantic schema 即文档）       |
| 类型安全       | 无（全是字符串）           | 有（Pydantic 自动类型转换和验证）    |
| 错误恢复       | 无（失败即终止）           | 有（多层降级策略）                 |
| 模型兼容性     | 通用                     | 通用（JSON 模式几乎所有模型都支持）   |
| 性能开销       | 极低                     | 略高（JSON 解析 + 验证）            |
"""
```

---

## 练习 3：工具调用的扩展实践

### 3.1 添加"计算器"工具

```python
import ast
import math
import operator

class CalculatorTool:
    """
    安全的数学计算器工具。
    使用 AST 解析而非 eval()，避免代码注入风险。
    """
    
    # 支持的运算符白名单
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
    }
    
    # 支持的数学函数白名单
    FUNCTIONS = {
        'sqrt': math.sqrt,
        'abs': abs,
        'round': round,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'pi': math.pi,
        'e': math.e,
    }
    
    @staticmethod
    def calculate(expression: str) -> str:
        """
        安全地计算数学表达式。
        
        示例:
            calculate("(123 + 456) * 789 / 12")  -> "38088.75"
            calculate("sqrt(144) + 2**3")         -> "20.0"
        """
        try:
            # 预处理：替换中文符号
            expression = expression.replace('×', '*').replace('÷', '/')
            expression = expression.replace('（', '(').replace('）', ')')
            
            # 使用 AST 安全解析
            tree = ast.parse(expression, mode='eval')
            result = CalculatorTool._eval_node(tree.body)
            
            # 格式化输出
            if isinstance(result, float) and result == int(result):
                return str(int(result))
            return str(result)
            
        except Exception as e:
            return f"计算错误: {e}。请检查表达式格式是否正确。"
    
    @classmethod
    def _eval_node(cls, node):
        """递归评估 AST 节点"""
        if isinstance(node, ast.Constant):  # 数字常量
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型: {type(node.value)}")
        
        elif isinstance(node, ast.BinOp):  # 二元运算
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            op_func = cls.OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op_func(left, right)
        
        elif isinstance(node, ast.UnaryOp):  # 一元运算
            operand = cls._eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        
        elif isinstance(node, ast.Call):  # 函数调用
            if not isinstance(node.func, ast.Name):
                raise ValueError("只支持简单的函数调用")
            func_name = node.func.id
            if func_name not in cls.FUNCTIONS:
                raise ValueError(f"不支持的函数: {func_name}")
            args = [cls._eval_node(arg) for arg in node.args]
            return cls.FUNCTIONS[func_name](*args)
        
        elif isinstance(node, ast.Name):  # 常量名称（如 pi, e）
            if node.id in cls.FUNCTIONS:
                return cls.FUNCTIONS[node.id]
            raise ValueError(f"未知变量: {node.id}")
        
        else:
            raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


# 注册到 ToolExecutor
# tool_executor.registerTool(
#     "Calculator",
#     "一个安全的数学计算器。当需要计算数学表达式时使用。输入应为数学表达式字符串，如 '(123 + 456) * 789 / 12'",
#     CalculatorTool.calculate
# )
```

**测试验证**：

```python
# 测试用例
test_cases = [
    ("(123 + 456) × 789 / 12", "38088.75"),
    ("2**10", "1024"),
    ("sqrt(144) + abs(-8)", "20"),
    ("log10(1000)", "3.0"),
]

for expr, expected in test_cases:
    result = CalculatorTool.calculate(expr)
    print(f"  {expr} = {result}  (期望: {expected})  {'✅' if result == expected else '❌'}")
```

---

### 3.2 "工具选择失败"的处理机制

> **设计原则**：智能体犯错不可怕，关键是系统能 **检测到错误** 并 **引导纠正**，而不是直接崩溃。

```python
class ToolFailureHandler:
    """
    工具调用失败处理机制。
    采用"渐进式引导"策略：提醒 → 提示 → 强制纠正。
    """
    
    def __init__(self, max_consecutive_failures=3):
        self.max_consecutive_failures = max_consecutive_failures
        self.failure_count = 0
        self.failure_history = []
    
    def record_failure(self, tool_name: str, error: str, attempted_input: str):
        """记录一次失败"""
        self.failure_count += 1
        self.failure_history.append({
            "tool": tool_name,
            "error": error,
            "input": attempted_input,
        })
    
    def record_success(self):
        """成功后重置计数器"""
        self.failure_count = 0
        self.failure_history = []
    
    def get_guidance(self, available_tools: list[str]) -> str:
        """
        根据失败次数返回不同级别的引导信息。
        这些信息会被注入到下一次 LLM 调用的 prompt 中。
        """
        if self.failure_count == 0:
            return ""
        
        if self.failure_count == 1:
            # 级别 1：温和提醒
            last = self.failure_history[-1]
            return (
                f"\n⚠️ 提示：上一次工具调用失败了。\n"
                f"  你尝试调用 '{last['tool']}'，但发生了错误：{last['error']}\n"
                f"  请仔细检查工具名称和参数是否正确。\n"
                f"  可用工具：{', '.join(available_tools)}\n"
            )
        
        elif self.failure_count == 2:
            # 级别 2：明确纠正 + 提供示例
            last = self.failure_history[-1]
            return (
                f"\n🚨 警告：你已经连续失败 {self.failure_count} 次了！\n"
                f"  最近一次错误：调用 '{last['tool']}' 时出错 - {last['error']}\n"
                f"  请停下来重新审视你的策略：\n"
                f"  1. 确认你要解决的问题是什么\n"
                f"  2. 从以下可用工具中选择最合适的：{', '.join(available_tools)}\n"
                f"  3. 确保参数格式正确\n"
            )
        
        else:
            # 级别 3：强制干预 - 提供完整的历史和明确指令
            history_str = "\n".join([
                f"  - 尝试 {i+1}: 工具='{f['tool']}', 错误={f['error']}"
                for i, f in enumerate(self.failure_history)
            ])
            return (
                f"\n🛑 严重警告：已连续失败 {self.failure_count} 次，达到上限！\n"
                f"  失败历史：\n{history_str}\n"
                f"  你必须立即改变策略。请：\n"
                f"  1. 重新分析用户的问题\n"
                f"  2. 如果确实无法完成，请诚实告知用户\n"
                f"  3. 可用工具：{', '.join(available_tools)}\n"
            )
    
    def should_terminate(self) -> bool:
        """是否应该终止执行"""
        return self.failure_count >= self.max_consecutive_failures
```

**在 ReAct 循环中集成**：

```python
# 在 ReAct 的主循环中集成失败处理
failure_handler = ToolFailureHandler(max_consecutive_failures=3)

while True:
    # 将失败引导信息注入 prompt
    guidance = failure_handler.get_guidance(available_tool_names)
    enhanced_prompt = original_prompt + guidance
    
    response = llm.think(enhanced_prompt)
    step = parser.parse(response)
    
    if step.final_answer:
        break
    
    if step.action:
        tool_func = tool_executor.getTool(step.action)
        if tool_func:
            try:
                observation = tool_func(step.action_input)
                failure_handler.record_success()
            except Exception as e:
                failure_handler.record_failure(step.action, str(e), step.action_input)
                observation = f"工具调用失败: {e}"
        else:
            failure_handler.record_failure(
                step.action, f"工具 '{step.action}' 不存在", step.action_input
            )
            observation = f"错误：不存在的工具 '{step.action}'"
        
        if failure_handler.should_terminate():
            step.final_answer = "抱歉，我在尝试解决这个问题时遇到了困难，无法找到合适的工具。请尝试重新描述您的问题。"
            break
```

---

### 3.3 大规模工具的组织与检索优化

> **核心问题**：当工具从 5 个增长到 100 个时，把所有工具描述塞进 prompt 会导致 **token 爆炸** 和 **选择困难**。

**问题量化**：

```
假设每个工具描述平均 100 tokens：
  - 10 个工具  →  ~1,000 tokens  ✅ 完全可行
  - 50 个工具  →  ~5,000 tokens  ⚠️ 占用大量上下文窗口
  - 100 个工具 → ~10,000 tokens ❌ 可能超出限制，且模型选择准确率下降
```

**工程优化方案（三层递进）**：

```
┌─────────────────────────────────────────────────────────┐
│                   工具检索三层架构                        │
│                                                         │
│  Layer 1: 语义检索（粗筛）                               │
│  ┌───────────────────────────────────────────────┐      │
│  │  用户输入 → Embedding → 向量相似度搜索          │      │
│  │  从 100 个工具中选出 Top-K 候选（如 K=10）      │      │
│  └───────────────────────┬───────────────────────┘      │
│                          │                               │
│  Layer 2: 分类过滤（精筛）                               │
│  ┌───────────────────────▼───────────────────────┐      │
│  │  按工具类别（搜索/计算/通信/文件...）过滤       │      │
│  │  结合任务类型缩小候选集                          │      │
│  └───────────────────────┬───────────────────────┘      │
│                          │                               │
│  Layer 3: LLM 精选（最终选择）                            │
│  ┌───────────────────────▼───────────────────────┐      │
│  │  将 Top-K 工具描述提供给 LLM                   │      │
│  │  LLM 从中选择 1-3 个最合适的工具               │      │
│  └───────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

**具体实现思路**：

```python
class ToolRetriever:
    """
    基于语义检索的工具选择器。
    解决大规模工具集下的选择效率问题。
    """
    
    def __init__(self, tool_executor: ToolExecutor, embedding_model):
        self.tool_executor = tool_executor
        self.embedding_model = embedding_model
        self.tool_embeddings = {}
        self._build_index()
    
    def _build_index(self):
        """预计算所有工具的 embedding 向量"""
        for name, info in self.tool_executor.tools.items():
            # 将工具名 + 描述组合作为检索文本
            text = f"{name}: {info['description']}"
            self.tool_embeddings[name] = self.embedding_model.encode(text)
    
    def retrieve(self, query: str, top_k: int = 10) -> list[str]:
        """
        根据用户查询，语义检索最相关的 top_k 个工具。
        
        原理：将用户查询和工具描述都映射到同一向量空间，
              通过余弦相似度找到最匹配的工具。
        """
        query_embedding = self.embedding_model.encode(query)
        
        # 计算与所有工具的相似度
        similarities = {}
        for name, tool_emb in self.tool_embeddings.items():
            sim = cosine_similarity(query_embedding, tool_emb)
            similarities[name] = sim
        
        # 返回 Top-K
        sorted_tools = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_tools[:top_k]]
```

**其他优化策略**：

| 策略 | 描述 | 适用场景 |
|------|------|---------|
| **工具分组** | 将工具按领域分组（如"邮件工具"、"搜索工具"），先选组再选工具 | 工具自然形成领域聚类 |
| **工具别名** | 为同一工具注册多个名称/描述，提高匹配率 | 用户表述方式多样 |
| **动态加载** | 按需加载工具，不活跃的工具不注入 prompt | 工具数量极大（100+） |
| **工具缓存** | 缓存常用的工具组合，减少检索开销 | 重复性任务场景 |
| **层级工具** | 高层工具封装低层工具链，减少暴露给 LLM 的工具数 | 复杂工作流场景 |

---

## 练习 4：Plan-and-Solve 范式深入分析

### 4.1 动态重规划机制设计

> **当前问题**：4.3 节的实现是"一次性规划，顺序执行"——如果第 3 步失败了，整个计划就卡住了。就像 GPS 导航遇到道路施工，不会自动绕路。

**动态重规划的核心思路**：

```
原计划: [A] → [B] → [C] → [D] → [E]
                    ↑
               步骤 C 失败！

传统方式: 整个计划失败 ❌
动态重规划: [A] → [B] → [C 失败] → [C' 替代方案] → [D'] → [E'] ✅
                                              ↑
                                        后续步骤也要调整
```

**实现方案**：

```python
class DynamicPlanner:
    """
    支持动态重规划的规划器。
    核心：在每个步骤执行后增加"检查点"，根据执行结果决定是否重规划。
    """
    
    def __init__(self, llm_client, replan_threshold=1):
        self.llm_client = llm_client
        self.replan_threshold = replan_threshold  # 连续失败 N 次后触发重规划
        self.failure_count = 0
    
    REPLAN_PROMPT = """
    你是一个任务规划专家。原计划在执行过程中遇到了问题。
    
    # 原始问题:
    {question}
    
    # 原始计划:
    {original_plan}
    
    # 已完成的步骤及结果:
    {completed_steps}
    
    # 当前失败的步骤:
    {failed_step}
    
    # 失败原因:
    {failure_reason}
    
    请基于当前已取得的进展，重新制定从当前状态到完成目标的剩余计划。
    注意：
    1. 保留已完成步骤的成果，不要重复
    2. 根据失败原因调整策略
    3. 输出格式仍为 Python 列表
    
    请输出新的剩余计划：
    """
    
    def execute_with_replan(self, question: str, plan: list[str], executor) -> str:
        """带动态重规划的执行"""
        history = ""
        completed_steps = []
        remaining_plan = list(plan)
        
        while remaining_plan:
            current_step = remaining_plan[0]
            
            # 执行当前步骤
            result = executor.execute_step(question, plan, history, current_step)
            
            # 检查执行结果
            if self._is_successful(result):
                self.failure_count = 0
                completed_steps.append((current_step, result))
                history += f"步骤: {current_step}\n结果: {result}\n\n"
                remaining_plan.pop(0)
            else:
                self.failure_count += 1
                
                if self.failure_count >= self.replan_threshold:
                    # 触发重规划
                    print("⚠️ 触发动态重规划...")
                    new_plan = self._replan(
                        question, plan, completed_steps, 
                        current_step, result
                    )
                    if new_plan:
                        remaining_plan = new_plan
                        self.failure_count = 0
                    else:
                        print("❌ 重规划失败，任务终止")
                        break
                else:
                    # 未达阈值，重试当前步骤
                    remaining_plan.pop(0)  # 移除失败步骤，下次循环会处理
        
        return history
    
    def _replan(self, question, original_plan, completed, failed_step, reason):
        """调用 LLM 生成新的剩余计划"""
        prompt = self.REPLAN_PROMPT.format(
            question=question,
            original_plan=original_plan,
            completed_steps=completed,
            failed_step=failed_step,
            failure_reason=reason,
        )
        # ... 调用 LLM 并解析结果
```

---

### 4.2 Plan-and-Solve vs ReAct：商务旅行预订场景对比

> **场景**：预订一次从北京到上海的商务旅行（包括机票、酒店、租车）

| 维度 | Plan-and-Solve | ReAct | **推荐** |
|------|---------------|-------|---------|
| **任务分解** | ✅ 天然支持：先分解为"查机票→订酒店→租车" | ❌ 需要模型自行分解，可能遗漏 | Plan-and-Solve |
| **步骤依赖** | ✅ 可以显式表达依赖（先确定日期再订酒店） | ⚠️ 隐式依赖，靠 Thought 传递 | Plan-and-Solve |
| **实时查询** | ⚠️ 每步独立查询，不灵活 | ✅ 可以根据上一步结果调整查询 | ReAct |
| **错误处理** | ❌ 某步失败后整个计划受阻 | ✅ 可以实时调整策略 | ReAct |
| **用户交互** | ❌ 不适合中途询问用户偏好 | ✅ 可以在任意步骤暂停询问 | ReAct |

**结论**：**混合方案最优**。

```
Phase 1 (Plan-and-Solve): 高层规划
  → 步骤 1: 确认用户偏好（日期、预算、舱位等级）
  → 步骤 2: 查询并比较机票
  → 步骤 3: 根据航班时间查询酒店
  → 步骤 4: 根据酒店位置查询租车

Phase 2 (ReAct): 每步内部用 ReAct 执行
  → 步骤 2 内部：
    Thought: 需要查询北京到上海的机票，用户偏好商务舱
    Action: SearchFlight("北京", "上海", date, "商务舱")
    Observation: 找到 3 个航班选项
    Thought: 需要比较价格和时间，帮用户选择最优
    ...
```

---

### 4.3 分层规划系统设计

> **类比**：就像建房子——先有建筑蓝图（高层），再有水电设计图（中层），最后有施工方案（低层）。

```
┌─────────────────────────────────────────────────────────────┐
│                    分层规划架构                               │
│                                                             │
│  Level 0: 战略层（Strategic Planner）                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ "组织一次北京到上海的商务旅行"                         │    │
│  │ → 高层计划: [交通安排, 住宿安排, 地面交通, 行程管理]   │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  Level 1: 战术层（Tactical Planner）                         │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │ "交通安排" 的子计划:                                  │    │
│  │ → [查询航班, 比较价格, 确认时间, 预订机票]            │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  Level 2: 执行层（Operational Executor）                     │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │ "查询航班" 的具体操作:                                │    │
│  │ → [调用航班API, 设置筛选条件, 格式化结果]             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**分层规划的优势**：

| 优势 | 说明 |
|------|------|
| **关注点分离** | 每层只关心自己层级的细节，降低复杂度 |
| **局部重规划** | 低层失败只需重规划该层，不影响全局 |
| **资源效率** | 高层规划用强模型（需要推理），低层执行用弱模型（只需执行） |
| **可解释性** | 每层计划都是可审查的，便于调试 |
| **复用性** | 低层执行器可以复用于不同的高层计划 |

---

## 练习 5：Reflection 机制的优化设计

### 5.1 异构模型（强反思 + 快执行）的影响分析

> **类比**：执行者像一个"手快的工人"，反思者像一个"眼高的教授"。工人负责干活，教授负责挑毛病和指导。

| 维度 | 同模型（当前方案） | 异构模型（改进方案） |
|------|-----------------|-------------------|
| **执行速度** | 中等 | ⬆️ 快模型执行，延迟低 |
| **反思质量** | 中等 | ⬆️ 强模型反思，洞察更深 |
| **成本** | 中等 | ⚠️ 两次 API 调用，可能更贵 |
| **一致性** | ⬆️ 同一模型风格一致 | ⚠️ 不同模型可能"理解偏差" |
| **迭代效率** | 中等 | ⬆️ 快速执行 + 精准反馈 = 更少迭代次数 |

**推荐配置**：

```
执行模型: GPT-4o-mini / Qwen-7B（快速、低成本）
  → 负责：代码生成、内容创作等"体力活"

反思模型: GPT-4o / Claude-3.5-Sonnet（强推理、高质量）
  → 负责：代码审查、质量评估等"脑力活"
```

**为什么这样更好？**

1. **术业有专攻**：快速模型擅长遵循指令生成内容，强模型擅长发现问题和提出改进
2. **成本优化**：执行次数多（每轮都要生成），反思次数少（每轮一次），让快速模型做高频任务
3. **避免"自我盲区"**：同一模型容易反复犯同样的错误（模型偏差），不同模型能引入新视角

---

### 5.2 更智能的终止条件设计

> **当前方案的问题**：
> - "无需改进"是字符串匹配，太脆弱（模型换个说法就失效）
> - "最大迭代次数"是硬限制，可能过早停止或浪费资源

**改进方案：多维度终止条件**

```python
class SmartTermination:
    """
    智能终止条件判断器。
    综合考虑质量收敛、边际收益、资源消耗等多维度因素。
    """
    
    def __init__(self, max_iterations=5, quality_threshold=0.95):
        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        self.quality_scores = []
        self.feedback_similarities = []
    
    def should_stop(self, iteration: int, feedback: str, 
                    prev_feedback: str, quality_score: float) -> tuple[bool, str]:
        """
        综合判断是否应该终止。
        
        返回: (是否终止, 终止原因)
        """
        self.quality_scores.append(quality_score)
        
        # 条件 1：质量达标
        if quality_score >= self.quality_threshold:
            return True, f"质量分数 {quality_score:.2f} 已达到阈值 {self.quality_threshold}"
        
        # 条件 2：质量收敛（连续 N 轮提升 < 阈值）
        if len(self.quality_scores) >= 3:
            recent = self.quality_scores[-3:]
            improvements = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
            if all(imp < 0.02 for imp in improvements):
                return True, "质量提升已收敛（连续3轮提升 < 2%），继续迭代收益极低"
        
        # 条件 3：反馈退化（新反馈与旧反馈高度相似 = 在原地打转）
        if prev_feedback:
            similarity = cosine_similarity(
                embed(feedback), embed(prev_feedback)
            )
            self.feedback_similarities.append(similarity)
            if similarity > 0.9:
                return True, "反馈内容与前一轮高度相似（相似度 > 0.9），陷入循环"
        
        # 条件 4：硬限制
        if iteration >= self.max_iterations:
            return True, f"已达到最大迭代次数 {self.max_iterations}"
        
        return False, "继续迭代"
    
    def get_quality_trajectory(self) -> str:
        """返回质量变化轨迹，用于可视化"""
        return " → ".join([f"{s:.2f}" for s in self.quality_scores])
```

**终止条件对比**：

```
原方案:
  终止条件 = "无需改进" in feedback OR iteration >= max
  
新方案:
  终止条件 = 质量达标 
           OR 质量收敛（边际收益递减）
           OR 反馈循环（原地打转）
           OR 达到硬限制
```

---

### 5.3 多维度学术论文写作助手设计

> **核心思想**：将单一维度的 Reflection 扩展为 **多维度并行反思**，每个维度由专门的"评审员"负责。

```
┌─────────────────────────────────────────────────────────────┐
│              多维度学术论文 Reflection 架构                   │
│                                                             │
│                    ┌──────────────┐                         │
│                    │  论文初稿生成  │                         │
│                    └──────┬───────┘                         │
│                           │                                  │
│           ┌───────────────┼───────────────┐                 │
│           ▼               ▼               ▼                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 逻辑评审员  │  │ 创新评审员  │  │ 语言评审员  │            │
│  │            │  │            │  │            │             │
│  │ 检查:      │  │ 检查:      │  │ 检查:      │             │
│  │ ·段落衔接  │  │ ·方法新颖性│  │ ·语法正确  │             │
│  │ ·论证链    │  │ ·对比基线  │  │ ·表达清晰  │             │
│  │ ·因果关系  │  │ ·贡献声明  │  │ ·学术用语  │             │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘            │
│        │               │               │                    │
│        ▼               ▼               ▼                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 引用评审员  │  │ 结构评审员  │  │ 伦理评审员  │            │
│  │            │  │            │  │            │             │
│  │ 检查:      │  │ 检查:      │  │ 检查:      │             │
│  │ ·引用格式  │  │ ·章节完整  │  │ ·数据隐私  │             │
│  │ ·引用充分性│  │ ·篇幅平衡  │  │ ·偏见声明  │             │
│  │ ·时效性    │  │ ·逻辑流    │  │ ·可复现性  │             │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘            │
│        │               │               │                    │
│        └───────────────┼───────────────┘                    │
│                        ▼                                     │
│              ┌──────────────────┐                           │
│              │  综合协调器       │                           │
│              │  ·优先级排序      │                           │
│              │  ·冲突消解        │                           │
│              │  ·生成修改指令    │                           │
│              └────────┬─────────┘                           │
│                       ▼                                     │
│              ┌──────────────────┐                           │
│              │  论文修改生成     │                           │
│              └──────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

**各维度评审员提示词设计**（示例）：

```python
DIMENSION_PROMPTS = {
    "logic": """
    你是一位严谨的学术逻辑评审员。请审查论文的论证逻辑：
    1. 每个段落的中心论点是否清晰？
    2. 段落之间的过渡是否自然？
    3. 因果关系是否有充分证据支持？
    4. 是否存在逻辑跳跃或循环论证？
    
    输出格式：
    - 问题列表（按严重程度排序）
    - 具体修改建议
    - 逻辑质量评分（1-10）
    """,
    
    "innovation": """
    你是一位资深的学术创新评审员。请评估论文的创新性：
    1. 研究方法是否有新颖之处？
    2. 与现有工作的区别是否清晰阐述？
    3. 贡献声明是否具体且可验证？
    4. 实验设计是否能支撑创新主张？
    
    输出格式：
    - 创新点识别
    - 不足之处
    - 改进建议
    - 创新性评分（1-10）
    """,
    
    "language": """
    你是一位学术写作语言专家。请审查论文的语言表达：
    1. 语法和拼写是否正确？
    2. 句子结构是否清晰简洁？
    3. 是否使用了恰当的学术用语？
    4. 是否存在歧义或模糊表达？
    
    输出格式：
    - 语言问题列表
    - 逐句修改建议
    - 语言质量评分（1-10）
    """,
    
    "citation": """
    你是一位学术引用规范评审员。请检查论文的引用：
    1. 引用格式是否统一且符合目标期刊要求？
    2. 相关工作部分的引用是否充分？
    3. 是否遗漏了重要的参考文献？
    4. 引用是否时效性足够（近5年文献占比）？
    
    输出格式：
    - 引用问题列表
    - 建议补充的文献方向
    - 引用规范评分（1-10）
    """,
}
```

---

## 练习 6：提示词工程的对比与实践

### 6.1 ReAct vs Plan-and-Solve 提示词的结构差异分析

> **核心差异**：提示词结构是范式逻辑的"镜像"——提示词怎么写，反映了智能体怎么想。

| 维度 | ReAct 提示词 | Plan-and-Solve 提示词 |
|------|-------------|---------------------|
| **输出格式** | 强制 Thought/Action/Observation 交替 | 分两阶段：先输出计划列表，再逐步输出答案 |
| **推理引导** | 每步都要"先思考再行动" | 规划阶段全局思考，执行阶段专注执行 |
| **工具使用** | 在 Action 中直接调用工具 | 执行阶段可能需要工具，但规划阶段不涉及 |
| **历史管理** | 维护完整的 Thought-Action-Observation 链 | 维护"步骤-结果"历史，供后续步骤参考 |
| **终止条件** | 输出 Final Answer | 所有步骤执行完毕 |

**为什么这样设计？**

```
ReAct 提示词的核心约束：
  "每一步都必须先 Thought 再 Action"
  → 目的：强制模型在行动前推理，避免盲目行动
  → 对应范式逻辑：思考与行动交织

Plan-and-Solve 提示词的核心约束：
  "先输出完整计划，再逐步执行"
  → 目的：将规划和执行解耦，各自专注
  → 对应范式逻辑：思考与行动分离
```

**类比理解**：

- ReAct 提示词像「**驾驶考试评分表**」——每个操作前都要说出理由
- Plan-and-Solve 提示词像「**项目管理模板**」——先写项目计划，再按计划执行

---

### 6.2 角色设定对智能体行为的影响

> **实验设计**：修改 Reflection 中的角色设定，观察输出变化。

| 角色设定 | 关注重点 | 反馈风格 | 修改方向 |
|---------|---------|---------|---------|
| "极其严格的代码评审专家"（原设定） | 算法效率、时间复杂度 | 严厉、直接 | 偏向算法优化 |
| "注重代码可读性的开源维护者" | 命名规范、注释、代码风格 | 温和、建设性 | 偏向代码质量 |
| "关注安全漏洞的安全工程师" | 输入验证、注入风险、权限检查 | 谨慎、全面 | 偏向安全性 |
| "追求极致性能的系统架构师" | 内存使用、并发、缓存策略 | 技术深度高 | 偏向系统级优化 |

**实验结论**：

1. **角色设定决定了"注意力分配"**：模型会优先关注角色关心的方面
2. **角色强度影响反馈深度**："极其严格"比"普通评审"产生更详细的反馈
3. **角色一致性很重要**：如果角色是"安全工程师"但反馈在优化算法，说明角色设定不够强

**最佳实践**：

```
好的角色设定 = 身份 + 关注点 + 标准 + 输出格式

例如：
"你是一位有 10 年经验的 Python 安全工程师（身份），
 专注于发现代码中的安全漏洞（关注点），
 按照 OWASP Top 10 标准评估（标准），
 输出包含：漏洞描述、风险等级、修复代码（格式）"
```

---

### 6.3 Few-shot 示例的设计与实践

> **为什么 Few-shot 有效？**：LLM 是"模仿高手"——给它看好的例子，它就能模仿好的格式。

**为 ReAct 添加 Few-shot 示例**：

```python
REACT_PROMPT_WITH_FEWSHOT = """
你是一个能够进行推理并使用工具解决问题的智能体。

## 可用工具
{tools}

## 输出格式
你必须严格按照以下格式输出：
Thought: 你的推理过程
Action: 工具名称[工具输入]
Observation: 工具返回的结果（由系统提供）
...（可以重复多轮）
Thought: 我现在知道最终答案了
Final Answer: 最终答案

## 示例

### 示例 1
Question: 北京今天的气温比上海高多少度？
Thought: 我需要分别查询北京和上海今天的气温，然后计算差值。
Action: Search[北京今天气温]
Observation: 北京今天气温 28°C
Thought: 我已经知道北京的气温了，现在需要查询上海的。
Action: Search[上海今天气温]
Observation: 上海今天气温 25°C
Thought: 北京 28°C，上海 25°C，差值是 3°C。
Final Answer: 北京今天气温比上海高 3°C。

### 示例 2
Question: 计算 (123 + 456) × 789 / 12 的结果
Thought: 这是一个数学计算问题，我可以使用计算器工具。
Action: Calculator[(123 + 456) × 789 / 12]
Observation: 38088.75
Thought: 计算器已经给出了结果。
Final Answer: (123 + 456) × 789 / 12 = 38088.75

## 现在开始
Question: {question}
"""
```

**Few-shot 效果对比**：

| 指标 | 无 Few-shot | 有 Few-shot |
|------|-----------|-----------|
| 格式遵循率 | ~70%（经常漏掉 Thought 或格式错乱） | ~95%（几乎完美遵循格式） |
| 工具调用准确率 | ~60%（参数格式经常出错） | ~90%（参数格式正确） |
| 首次成功率 | ~40% | ~80% |
| 平均迭代次数 | 3-5 次 | 1-2 次 |

---

## 练习 7：电商客服智能体综合设计

### 7.1 核心架构选择

> **结论**：采用 **ReAct + Reflection 混合架构**，以 ReAct 为主干，Reflection 为决策质量兜底。

**架构选择理由**：

```
客服场景的核心需求：
  ✅ 需要实时理解用户意图      → ReAct（逐步推理）
  ✅ 需要调用多个工具查询信息    → ReAct（工具调用）
  ✅ 需要在争议决策时自我审视    → Reflection（自我反思）
  ❌ 不需要预规划复杂步骤       → 不需要 Plan-and-Solve
  
因此：ReAct（主干） + Reflection（决策兜底）
```

**系统架构图**：

```
┌─────────────────────────────────────────────────────────────┐
│                    电商客服智能体架构                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  用户输入层                          │    │
│  │  "我收到的商品有破损，想申请退款"                     │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              ReAct 主循环                            │    │
│  │                                                     │    │
│  │  Thought: 用户要退款，需要先理解退款理由              │    │
│  │  Action: 理解退款意图(用户消息)                       │    │
│  │  Observation: {理由: 商品破损, 订单号: XXX, ...}      │    │
│  │                                                     │    │
│  │  Thought: 需要查询订单信息和物流状态                   │    │
│  │  Action: 查询订单(订单号)                             │    │
│  │  Observation: {状态: 已签收, 金额: 299, ...}          │    │
│  │                                                     │    │
│  │  Thought: 需要查询退款政策判断是否符合条件              │    │
│  │  Action: 查询退款政策(商品类别, 退款理由)              │    │
│  │  Observation: {符合条件: true, 条件: 7天无理由}        │    │
│  │                                                     │    │
│  │  Thought: 需要做出退款决策，置信度可能不高              │    │
│  │  → 进入 Reflection 决策审查                          │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │          Reflection 决策审查（条件触发）              │    │
│  │                                                     │    │
│  │  if 决策置信度 < 阈值:                               │    │
│  │    → 反思决策是否合理                                │    │
│  │    → 检查是否遗漏了关键信息                           │    │
│  │    → 给出更审慎的建议                                │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              输出生成层                               │    │
│  │  → 生成得体的回复邮件                                │    │
│  │  → 发送邮件给用户                                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

### 7.2 工具设计

| 工具名称 | 功能描述 | 输入 | 输出 |
|---------|---------|------|------|
| `QueryOrderInfo` | 查询用户订单详情 | 订单号 / 用户ID | 订单状态、金额、商品列表、下单时间 |
| `QueryLogisticsStatus` | 查询物流实时状态 | 订单号 / 运单号 | 物流节点、当前位置、预计送达时间 |
| `CheckRefundPolicy` | 查询退款政策规则 | 商品类别、退款理由、购买时间 | 是否符合退款条件、退款比例、特殊规则 |
| `SendEmail` | 发送回复邮件 | 收件人、主题、正文 | 发送状态（成功/失败） |
| `CalculateRefundAmount` | 计算退款金额 | 订单金额、退款比例、优惠券抵扣 | 实际退款金额明细 |
| `EscalateToHuman` | 升级到人工客服 | 原因描述、用户信息 | 人工客服工单号 |

---

### 7.3 提示词设计

```python
CUSTOMER_SERVICE_PROMPT = """
## 角色定义
你是一位专业、友善且公正的电商客服专家。你的目标是：
1. 准确理解用户的需求和情绪
2. 基于事实和公司政策做出合理决策
3. 在维护公司利益的同时，让用户感受到被尊重和关怀

## 核心原则
- **用户至上**：始终尊重用户，即使拒绝也要给出合理解释
- **政策为准**：决策必须基于公司退款政策，不随意承诺
- **透明沟通**：清楚告知用户决策依据和后续流程
- **审慎决策**：对于不确定的情况，宁可升级到人工也不要草率决定

## 决策框架
1. 先理解：完整理解用户的诉求和情绪
2. 再调查：查询所有相关信息（订单、物流、政策）
3. 后判断：基于事实和政策做出判断
4. 终沟通：用温暖但专业的方式传达结果

## 情绪应对
- 用户愤怒时：先共情（"我完全理解您的不满"），再解决问题
- 用户焦虑时：给出明确的时间线和后续步骤
- 用户满意时：确认没有其他需要帮助的地方

## 输出格式
每次回复包含：
1. 对用户的回复（温暖、专业、简洁）
2. 内部决策记录（决策依据、置信度、是否需要反思）
"""
```

---

### 7.4 风险分析与技术应对

| 风险类别 | 具体风险 | 技术应对措施 |
|---------|---------|-------------|
| **决策风险** | 错误批准不应退款的申请 | 设置金额阈值，超过阈值必须人工审核 |
| **决策风险** | 错误拒绝合理退款 | Reflection 机制对低置信度决策进行二次审查 |
| **安全风险** | 用户通过 prompt 注入操纵决策 | 输入过滤 + 系统提示词与用户输入严格分离 |
| **安全风险** | 泄露内部政策或用户隐私 | 输出过滤 + 敏感信息脱敏 |
| **体验风险** | 回复过于机械，用户感受差 | Few-shot 示例 + 情绪识别 + 个性化回复模板 |
| **体验风险** | 响应时间过长 | 流式输出 + 异步工具调用 + 缓存常用查询 |
| **合规风险** | 承诺超出政策范围的内容 | 输出校验层：检查回复是否包含未授权的承诺 |
| **运营风险** | 无法处理新型/复杂问题 | 设置明确的升级到人工客服的触发条件 |
| **成本风险** | 大量 Reflection 调用增加成本 | 仅在低置信度时触发 Reflection，设置每日调用上限 |

**安全防线设计**：

```
用户输入 → [输入过滤层] → [ReAct 决策层] → [输出校验层] → 用户
                │                │                │
                ▼                ▼                ▼
          Prompt注入检测    决策合规检查      敏感信息脱敏
          情绪识别          金额阈值检查      承诺范围验证
```

---

## 附录：关键概念速查表

| 概念 | 一句话解释 | 类比 |
|------|----------|------|
| ReAct | 边想边做的智能体 | 出租车司机 |
| Plan-and-Solve | 先计划再执行的智能体 | 导航软件 |
| Reflection | 做完再反思改进的智能体 | 代码审查 |
| Tool Calling | 智能体使用外部工具的能力 | 人使用计算器 |
| Prompt Engineering | 通过提示词引导模型行为 | 给新员工写工作手册 |
| Few-shot Learning | 通过示例教模型格式 | 给模板让人照着填 |
| Dynamic Replanning | 执行中根据实际情况修改计划 | GPS 遇到堵车自动绕路 |
| Hierarchical Planning | 分层级的计划系统 | 蓝图→施工图→作业指导书 |

---

> **费曼检验**：如果你能把每个练习的答案讲给一个不懂 AI 的朋友听，并且他能理解核心思想，说明你真正掌握了这些概念。如果某个地方你自己也觉得模糊，那就是你需要回头重读的地方。
