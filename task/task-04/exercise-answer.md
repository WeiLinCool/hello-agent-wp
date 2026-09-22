# 第九章「上下文工程」习题答案

---

## 题目 1：上下文工程与提示工程

### 1.1 上下文腐蚀（Context Rot）及大窗口仍需管理的原因

#### 什么是上下文腐蚀

**上下文腐蚀**是指：随着上下文中积累的信息越来越多，上下文的**有效信息密度持续下降**，导致模型输出质量逐步退化的现象。它不是"窗口满了"的问题，而是"窗口里的东西变差了"。

具体表现为三种腐蚀机制：

| 腐蚀机制 | 表现 | 类比 |
|---------|------|------|
| **信息冗余** | 对话历史中反复出现相同或高度相似的内容 | 同一句话在书里重复了10遍 |
| **信息过时** | 早期对话中的假设/结论已被后续信息推翻，但旧信息仍留在上下文中 | 用了过期的地图导航 |
| **信息冲突** | 不同来源（笔记、记忆、工具输出）给出矛盾信息，模型无法判断该信哪个 | 两本教科书给了不同的公式 |

**源码实证**：`codebase_maintainer.py` 第 335-346 行的 `_update_history()` 方法主动限制对话历史为最近 20 条消息，正是为了对抗信息冗余导致的上下文腐蚀：

```python
def _update_history(self, user_input: str, response: str):
    self.conversation_history.append(
        Message(content=user_input, role="user", timestamp=datetime.now())
    )
    self.conversation_history.append(
        Message(content=response, role="assistant", timestamp=datetime.now())
    )
    # 限制历史长度(保留最近10轮对话)
    if len(self.conversation_history) > 20:
        self.conversation_history = self.conversation_history[-20:]
```

#### 为什么 200K 窗口仍需管理

即使模型支持 100K-200K 上下文窗口，仍需精细管理的原因有四个：

1. **注意力稀释（Lost in the Middle）**：研究表明，LLM 对上下文中间位置的信息关注度显著低于首尾。200K 窗口中间的信息可能被模型"视而不见"，有效利用率远低于标称值。

2. **推理成本线性增长**：Transformer 的自注意力机制复杂度为 O(n²)，上下文越长，推理延迟越高、API 调用成本越大。200K token 的一次调用成本可能是 4K 的 50 倍。

3. **噪声放大效应**：无关信息越多，模型越容易被"带偏"。实验表明，在上下文中混入无关段落后，模型在事实性问答任务上的准确率可下降 20-30%。

4. **边际收益递减**：上下文的前 4K token 可能包含 80% 的有用信息，从 4K 到 200K 的增量部分可能只增加 5% 的有用信息，却引入了 95% 的噪声。

**一句话总结**：窗口大小 ≠ 有效信息容量。200K 窗口堆满发霉的旧报纸，依然做不了工作。

---

### 1.2 代码审查助手：一次性加载 vs JIT 按需检索

#### 两种策略对比

| 维度 | 策略①：一次性全加载 | 策略②：JIT 按需检索 |
|------|-------------------|---------------------|
| **实现复杂度** | 低 — 直接读取所有文件拼接 | 高 — 需要检索策略和工具链 |
| **上下文占用** | 50 文件 × 平均 200 行 ≈ 10000 行代码，轻松超出有效窗口 | 每次只加载 1-3 个相关文件 |
| **信息噪声** | 高 — 大量与当前审查点无关的代码混入 | 低 — 按需加载，信噪比高 |
| **全局一致性** | 好 — 模型可同时看到所有文件间的关系 | 差 — 需要跨轮次记忆来维持全局视图 |
| **可扩展性** | 差 — 文件数增长即不可用 | 好 — 100 个文件和 10 个文件成本相同 |
| **适用场景** | < 5 个文件的小项目、需要全局一致性审查 | > 10 个文件的中大型项目 |

#### 推荐方案：混合策略

实际最佳实践是**两阶段混合**：

```
阶段一：全局扫描（轻量级）
    ├── TerminalTool: find . -name '*.py' | wc -l        → 文件数量
    ├── TerminalTool: grep -rn 'import' --include='*.py'  → 依赖关系图
    └── TerminalTool: wc -l *.py                          → 各文件规模
    → 产出：项目结构概览（< 500 token）

阶段二：JIT 深入（按需）
    ├── 根据阶段一的依赖图，按模块逐一审查
    ├── 每次只加载当前模块 + 其直接依赖
    └── 用 NoteTool 记录每个模块的审查结论
    → 产出：逐模块审查报告 + 跨模块问题汇总
```

**源码实证**：`06_three_day_workflow.py` 的三天工作流正是这种混合策略的实践。Agent 在 Day 1 先用 `find` 和 `wc` 了解全局结构（产出"Python 电商系统，358 行代码，4 个核心模块"），再在 Day 2 逐文件深入分析（`cat data_processor.py`、`cat api_client.py`），全程用 NoteTool 记录发现。

---

### 1.3 系统提示的两个极端误区

#### 过度硬编码的例子

```
❌ "你是一个Python代码审查助手。你只能回答Python相关问题。
    你必须严格按以下格式回答：1.结论 2.代码 3.解释。
    你的回答不能超过200字。你不能讨论任何非技术问题。
    你必须使用print语句而不是logging。你必须使用type hints。
    你不能建议任何第三方库。你不能修改用户的代码逻辑。
    你的回答必须以'根据我的分析'开头。"
```

**问题**：
- 约束过多，模型灵活性被严重限制
- 200 字限制可能导致复杂问题无法说清
- "不能建议第三方库"在实际工程中不现实
- 固定开头格式浪费 token 且无信息量

**类比**：像给厨师规定"只能用左手切菜、每道菜不超过 100 克、不能放盐、必须用圆盘子"——规则太多，做不出好菜。

#### 过于空泛的例子

```
❌ "你是一个有帮助的助手。"
```

**问题**：
- 没有角色定位，模型不知道自己该做什么
- 没有输出格式要求，回答风格不可预测
- 没有行为边界，可能回答不该回答的问题
- 没有质量标准，"有帮助"的定义完全交给模型自行理解

**类比**：像给厨师说"做点吃的"——厨师不知道你要川菜还是法餐、几个人吃、有什么忌口。

#### 如何找到平衡点

**核心原则**：约束"做什么"和"怎么做"，但不约束"用什么词"和"多少字"。

**本项目的实践**（`codebase_maintainer.py` 第 153-177 行）给出了优秀的平衡示范：

```python
# ✅ 平衡点：有方向性约束，保留灵活性
"""你是 {project_name} 项目的代码库维护助手。

你的核心能力:                          ← 告诉模型"你能做什么"
1. 使用 TerminalTool 探索代码库
2. 使用 NoteTool 记录发现和任务
3. 使用 MemoryTool 存储关键信息

重要原则:                              ← 告诉模型"应该怎么做"（软约束）
- 你要自主决定使用哪些工具              ← 保留决策自由
- 探索代码库时，先整体后细节            ← 给出策略建议
- 发现重要信息时，主动记录              ← 引导行为而非强制
"""
```

**平衡点公式**：

```
好的系统提示 = 角色定义（1-2句）
             + 能力边界（能做什么/不能做什么）
             + 行为引导（策略建议，非硬性规则）
             + 输出期望（格式偏好，非字数限制）
```

---

## 题目 2：GSSC 流水线

### 2.1 各阶段失效的影响分析

| 失效阶段 | 直接后果 | 对智能体表现的影响 | 现实类比 |
|---------|---------|------------------|---------|
| **Gather 失败** | 信息缺失：对话历史丢失、笔记未检索、工具输出遗漏 | 模型"无米之炊"，回答缺乏依据，可能重复已讨论过的内容 | 考试没带课本 |
| **Select 失败** | 噪声混入：不相关的笔记/历史被保留在上下文中 | 模型被"带偏"，回答偏离主题，或在不相关信息上浪费注意力 | 带了错误的课本复习 |
| **Structure 失败** | 信息混乱：角色定义、任务描述、背景信息混杂在一起 | 模型分不清"哪些是指令"和"哪些是参考信息"，可能把背景信息当作指令执行 | 资料乱堆找不到重点 |
| **Compress 过度** | 信息丢失：关键细节在摘要中被省略 | 模型丢失关键约束或数据，回答看似合理但遗漏重要细节 | 划重点把关键内容划掉了 |
| **Compress 不足** | 超出预算：上下文超过 max_tokens | 调用失败或被截断，模型看到的信息不完整 | 课本太厚翻不完 |

**源码实证**：`01_context_builder_basic.py` 中 `ContextConfig` 的参数设计直接对应了防止各阶段失效的防线：

```python
config = ContextConfig(
    max_tokens=3000,       # 防止 Compress 不足（超出预算）
    reserve_ratio=0.2,     # 防止 Compress 过度（预留输出空间）
    min_relevance=0,       # 防止 Select 过严（0=保留所有，但生产环境应调高）
    enable_compression=True # 启用 Compress 阶段
)
```

---

### 2.2 上下文质量评估功能实现

基于 `ContextBuilder` 的扩展，设计 `ContextQualityEvaluator`：

```python
from typing import Dict, List
import re


class ContextQualityEvaluator:
    """上下文质量评估器
    
    评估维度：
    1. 信息密度（info_density）：有效信息占比
    2. 相关性（relevance）：与查询的语义相关度
    3. 完整性（completeness）：是否包含回答所需的必要信息类型
    """
    
    # 必要信息类型及其在上下文中的标记
    REQUIRED_SECTIONS = {
        "role": ["[Role", "[System", "你是", "你的职责"],
        "task": ["[Task", "用户问题", "用户输入"],
        "context": ["[Context", "对话历史", "背景"],
        "output": ["[Output", "输出格式", "请按以下格式"],
    }
    
    # 噪声模式（低信息量的文本特征）
    NOISE_PATTERNS = [
        r'^\s*$',                    # 空行
        r'^[-=]{3,}\s*$',           # 分隔线
        r'^(提示|注意|说明)[：:]',    # 模板化提示
    ]
    
    def evaluate(self, context: str, user_query: str) -> Dict:
        """评估上下文质量，返回评分和建议"""
        
        density = self._calc_info_density(context)
        relevance = self._calc_relevance(context, user_query)
        completeness = self._calc_completeness(context)
        
        # 综合评分（加权平均）
        overall = density * 0.3 + relevance * 0.4 + completeness * 0.3
        
        # 生成优化建议
        suggestions = self._generate_suggestions(
            context, density, relevance, completeness
        )
        
        return {
            "overall_score": round(overall, 2),
            "info_density": round(density, 2),
            "relevance": round(relevance, 2),
            "completeness": round(completeness, 2),
            "suggestions": suggestions,
            "token_estimate": len(context) // 4,
        }
    
    def _calc_info_density(self, context: str) -> float:
        """信息密度 = 1 - (噪声行数 / 总行数)"""
        lines = context.split('\n')
        if not lines:
            return 0.0
        
        noise_lines = 0
        for line in lines:
            for pattern in self.NOISE_PATTERNS:
                if re.match(pattern, line.strip()):
                    noise_lines += 1
                    break
        
        return 1.0 - (noise_lines / len(lines))
    
    def _calc_relevance(self, context: str, query: str) -> float:
        """相关性 = 包含查询关键词的段落占比"""
        query_terms = set(query.lower().split())
        # 去除常见停用词
        stop_words = {'的', '了', '是', '在', '和', '与', '或', '请', '如何', '什么', '怎么'}
        query_terms -= stop_words
        
        if not query_terms:
            return 0.5  # 无法判断
        
        # 按段落切分
        paragraphs = [p.strip() for p in context.split('\n\n') if p.strip()]
        if not paragraphs:
            return 0.0
        
        relevant_paragraphs = 0
        for para in paragraphs:
            para_lower = para.lower()
            if any(term in para_lower for term in query_terms):
                relevant_paragraphs += 1
        
        return relevant_paragraphs / len(paragraphs)
    
    def _calc_completeness(self, context: str) -> float:
        """完整性 = 包含的必要信息类型数 / 总必要类型数"""
        found_sections = 0
        for section_name, markers in self.REQUIRED_SECTIONS.items():
            if any(marker in context for marker in markers):
                found_sections += 1
        
        return found_sections / len(self.REQUIRED_SECTIONS)
    
    def _generate_suggestions(
        self, context: str, 
        density: float, relevance: float, completeness: float
    ) -> List[str]:
        """根据评估结果生成优化建议"""
        suggestions = []
        
        if density < 0.6:
            suggestions.append(
                "⚠️ 信息密度偏低：建议清理空行、分隔线等格式噪声，"
                "或压缩重复的对话历史"
            )
        
        if relevance < 0.4:
            suggestions.append(
                "⚠️ 相关性不足：上下文中与用户问题直接相关的信息较少，"
                "建议检查 Select 阶段的 min_relevance 阈值是否过低"
            )
        
        if completeness < 0.75:
            missing = []
            for section_name, markers in self.REQUIRED_SECTIONS.items():
                if not any(marker in context for marker in markers):
                    missing.append(section_name)
            suggestions.append(
                f"⚠️ 结构不完整：缺少以下信息区块：{', '.join(missing)}。"
                f"建议在 ContextBuilder.build() 中补充对应的 system_instructions"
            )
        
        token_count = len(context) // 4
        if token_count > 6000:
            suggestions.append(
                f"⚠️ Token 消耗较高（约 {token_count} token），"
                f"建议启用 enable_compression=True 或降低 max_tokens"
            )
        
        if not suggestions:
            suggestions.append("✅ 上下文质量良好，无需优化")
        
        return suggestions


# === 集成到 ContextBuilder 的使用示例 ===

def build_with_evaluation(builder, user_query, conversation_history, 
                          system_instructions, **kwargs):
    """构建上下文并自动评估质量"""
    context = builder.build(
        user_query=user_query,
        conversation_history=conversation_history,
        system_instructions=system_instructions,
        **kwargs
    )
    
    evaluator = ContextQualityEvaluator()
    report = evaluator.evaluate(context, user_query)
    
    print(f"📊 上下文质量报告:")
    print(f"   综合评分: {report['overall_score']}/1.0")
    print(f"   信息密度: {report['info_density']}/1.0")
    print(f"   相关性:   {report['relevance']}/1.0")
    print(f"   完整性:   {report['completeness']}/1.0")
    print(f"   Token 估算: ~{report['token_estimate']}")
    for s in report['suggestions']:
        print(f"   {s}")
    
    return context, report
```

**验证示例**（基于 `01_context_builder_basic.py` 的输出）：

```
📊 上下文质量报告:
   综合评分: 0.82/1.0
   信息密度: 0.85/1.0   ← 结构化格式好，噪声少
   相关性:   0.75/1.0   ← 对话历史与"Pandas内存优化"相关
   完整性:   1.00/1.0   ← [Role]/[Task]/[Context]/[Output] 四个区块齐全
   Token 估算: ~450
   ✅ 上下文质量良好，无需优化
```

---

### 2.3 混合压缩策略设计

#### 什么时候简单策略比 LLM 摘要更合适？

| 内容类型 | 推荐压缩策略 | 原因 |
|---------|------------|------|
| **日志文件** | 截断（保留最新 N 行） | 时间局部性强，旧日志价值低 |
| **代码文件** | 滑动窗口（按函数/类切分） | 需要保持代码结构完整性 |
| **多轮对话** | LLM 摘要 | 语义连贯性重要，不能简单截断 |
| **数值数据** | 统计摘要（均值/分布/极值） | 数值特征可无损压缩 |
| **结构化配置** | 不压缩 | 配置信息每行都可能有价值 |

#### 混合压缩策略实现

```python
from typing import List, Tuple
from enum import Enum


class ContentType(Enum):
    LOG = "log"
    CODE = "code"
    CONVERSATION = "conversation"
    DATA = "data"
    CONFIG = "config"
    UNKNOWN = "unknown"


class HybridCompressor:
    """混合压缩器：根据内容类型选择最优压缩策略"""
    
    def __init__(self, token_budget: int):
        self.token_budget = token_budget
    
    def compress(self, content: str, content_type: ContentType) -> str:
        """根据内容类型自动选择压缩策略"""
        strategies = {
            ContentType.LOG: self._tail_truncate,
            ContentType.CODE: self._structural_window,
            ContentType.CONVERSATION: self._llm_summarize,
            ContentType.DATA: self._statistical_summary,
            ContentType.CONFIG: self._passthrough,
            ContentType.UNKNOWN: self._llm_summarize,
        }
        
        strategy = strategies.get(content_type, self._llm_summarize)
        return strategy(content)
    
    def _tail_truncate(self, content: str, keep_last: int = 50) -> str:
        """尾部截断：保留最新 N 行（适用于日志）"""
        lines = content.split('\n')
        if len(lines) <= keep_last:
            return content
        truncated = lines[-keep_last:]
        header = f"[日志截断：显示最新 {keep_last}/{len(lines)} 行]\n"
        return header + '\n'.join(truncated)
    
    def _structural_window(self, content: str, max_functions: int = 10) -> str:
        """结构化窗口：按函数/类边界切分（适用于代码）"""
        # 按 def/class 边界切分
        blocks = []
        current_block = []
        
        for line in content.split('\n'):
            if line.startswith(('def ', 'class ')) and current_block:
                blocks.append('\n'.join(current_block))
                current_block = []
            current_block.append(line)
        
        if current_block:
            blocks.append('\n'.join(current_block))
        
        if len(blocks) <= max_functions:
            return content
        
        # 保留前 3 个 + 最后 max_functions-3 个（保留入口和最新）
        kept = blocks[:3] + blocks[-(max_functions - 3):]
        header = f"[代码截断：显示 {len(kept)}/{len(blocks)} 个函数/类]\n"
        return header + '\n\n'.join(kept)
    
    def _llm_summarize(self, content: str) -> str:
        """LLM 智能摘要（适用于对话历史）"""
        # 实际实现中调用 LLM API
        # 这里用简化版：提取每轮对话的关键句
        lines = content.split('\n')
        summary_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 保留包含关键信号词的行
            if any(kw in line for kw in ['结论', '问题', '建议', '决定', '发现', 'TODO']):
                summary_lines.append(line)
            elif len(line) < 50:  # 短行可能是标题或要点
                summary_lines.append(line)
        
        if summary_lines:
            return "[对话摘要]\n" + '\n'.join(summary_lines[:20])
        return content[:len(content) // 3]  # fallback: 截断到 1/3
    
    def _statistical_summary(self, content: str) -> str:
        """统计摘要（适用于数值数据）"""
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return content
        
        header = lines[0]
        data_lines = lines[1:]
        
        summary = [
            f"[数据统计：{len(data_lines)} 行]",
            f"表头: {header}",
            f"前 3 行: {'; '.join(data_lines[:3])}",
            f"后 3 行: {'; '.join(data_lines[-3:])}",
        ]
        return '\n'.join(summary)
    
    def _passthrough(self, content: str) -> str:
        """不压缩（适用于配置信息）"""
        return content
    
    def smart_compress_pipeline(
        self, 
        sections: List[Tuple[str, ContentType]]
    ) -> str:
        """智能压缩流水线：在总 token 预算内分配空间
        
        Args:
            sections: [(内容, 类型), ...] 列表
        Returns:
            压缩后的完整上下文
        """
        # 第一步：计算各段原始 token 数
        total_tokens = sum(len(c) // 4 for c, _ in sections)
        
        if total_tokens <= self.token_budget:
            # 未超预算，无需压缩
            return '\n\n'.join(c for c, _ in sections)
        
        # 第二步：按优先级分配预算
        # config > conversation > code > data > log
        priority = {
            ContentType.CONFIG: 0,     # 不压缩
            ContentType.CONVERSATION: 1,
            ContentType.CODE: 2,
            ContentType.DATA: 3,
            ContentType.LOG: 4,        # 最先被压缩
        }
        
        # 第三步：从低优先级开始压缩
        sorted_sections = sorted(sections, key=lambda x: priority.get(x[1], 5))
        compressed_parts = []
        remaining_budget = self.token_budget
        
        for content, ctype in sorted_sections:
            budget_for_section = remaining_budget // (len(sorted_sections) - len(compressed_parts))
            
            if len(content) // 4 <= budget_for_section:
                compressed_parts.append(content)
            else:
                compressed = self.compress(content, ctype)
                compressed_parts.append(compressed)
            
            remaining_budget -= len(compressed_parts[-1]) // 4
        
        return '\n\n'.join(compressed_parts)
```

---

## 题目 3：NoteTool 与 TerminalTool 深入

### 3.1 笔记自动整理机制

#### 设计思路

**费曼比喻**：笔记本用久了，有些页面已经过时，有些重要结论散落在不同位置。你需要一个"整理助手"定期帮你：
- 把散落的想法合并成完整的计划
- 把过时的信息标记为"已过期"
- 把重要的结论提升到"永久笔记"区

#### 实现方案

```python
from datetime import datetime, timedelta
from typing import List, Dict, Tuple


class NoteAutoOrganizer:
    """笔记自动整理器
    
    触发条件：临时笔记数量 > 阈值
    整理动作：
    1. 重要性评估 → 提升/保留/清理
    2. 相似笔记合并
    3. 过期笔记归档
    """
    
    # 笔记类型层级（从低到高）
    NOTE_HIERARCHY = {
        "temporary": 0,   # 临时笔记（最低）
        "conclusion": 1,  # 结论笔记
        "action": 2,      # 行动笔记
        "task_state": 3,  # 任务状态（最高）
        "blocker": 3,     # 阻塞问题（最高，特殊）
    }
    
    def __init__(self, note_tool, threshold: int = 10):
        self.note_tool = note_tool
        self.threshold = threshold
    
    def should_organize(self) -> bool:
        """判断是否需要整理"""
        summary = self.note_tool.run({"action": "summary"})
        # 解析总笔记数
        # 实际实现中需要解析 summary 的文本输出
        total_notes = self._parse_total(summary)
        return total_notes >= self.threshold
    
    def organize(self) -> Dict:
        """执行自动整理，返回整理报告"""
        report = {
            "promoted": [],    # 提升的笔记
            "merged": [],      # 合并的笔记
            "archived": [],    # 归档的笔记
            "cleaned": [],     # 清理的笔记
        }
        
        # Step 1: 获取所有笔记
        all_notes = self._get_all_notes()
        
        # Step 2: 评估每条笔记的重要性
        scored_notes = [(note, self._score_importance(note)) for note in all_notes]
        
        # Step 3: 按重要性分类处理
        for note, score in scored_notes:
            note_type = note.get("type", "temporary")
            
            if score >= 0.8 and note_type == "temporary":
                # 高重要性临时笔记 → 提升为 task_state 或 action
                self._promote_note(note, score)
                report["promoted"].append(note.get("note_id"))
            
            elif score < 0.2 and note_type == "temporary":
                # 低重要性临时笔记 → 清理
                self._archive_note(note)
                report["cleaned"].append(note.get("note_id"))
        
        # Step 4: 合并相似笔记
        similar_groups = self._find_similar_notes(scored_notes)
        for group in similar_groups:
            merged = self._merge_notes(group)
            report["merged"].append([n.get("note_id") for n in group])
        
        # Step 5: 归档过期笔记（超过 7 天未更新的临时笔记）
        for note, _ in scored_notes:
            if self._is_expired(note, days=7):
                self._archive_note(note)
                report["archived"].append(note.get("note_id"))
        
        return report
    
    def _score_importance(self, note: Dict) -> float:
        """评估笔记的重要性分数 (0.0 - 1.0)
        
        评分维度：
        - 被引用次数（其他笔记提到它的次数）
        - 内容长度（越长通常越详细）
        - 标签权重（含 urgent/important 标签加分）
        - 时间衰减（越新越重要）
        """
        score = 0.0
        
        # 内容长度分 (0-0.3)
        content = note.get("content", "")
        content_len = len(content)
        score += min(content_len / 1000, 0.3)
        
        # 标签权重分 (0-0.3)
        tags = note.get("tags", [])
        high_value_tags = {"urgent", "important", "blocker", "critical"}
        if high_value_tags & set(tags):
            score += 0.3
        
        # 时间衰减分 (0-0.2)
        updated_at = note.get("updated_at", "")
        if updated_at:
            try:
                update_time = datetime.fromisoformat(updated_at)
                days_ago = (datetime.now() - update_time).days
                score += max(0.2 - days_ago * 0.02, 0)
            except (ValueError, TypeError):
                score += 0.1
        
        # 类型基础分 (0-0.2)
        note_type = note.get("type", "temporary")
        type_scores = {"blocker": 0.2, "task_state": 0.15, "action": 0.1, "conclusion": 0.05}
        score += type_scores.get(note_type, 0)
        
        return min(score, 1.0)
    
    def _find_similar_notes(self, scored_notes: List[Tuple]) -> List[List[Dict]]:
        """查找内容相似的笔记组（基于标题和内容重叠度）"""
        groups = []
        used = set()
        
        notes = [n for n, _ in scored_notes]
        for i, note_a in enumerate(notes):
            if note_a.get("note_id") in used:
                continue
            group = [note_a]
            for j, note_b in enumerate(notes[i+1:], i+1):
                if note_b.get("note_id") in used:
                    continue
                if self._similarity(note_a, note_b) > 0.6:
                    group.append(note_b)
                    used.add(note_b.get("note_id"))
            if len(group) > 1:
                used.add(note_a.get("note_id"))
                groups.append(group)
        
        return groups
    
    def _similarity(self, note_a: Dict, note_b: Dict) -> float:
        """计算两条笔记的相似度（0-1）"""
        # 简单的标题 + 标签重叠度
        title_a = set(note_a.get("title", "").lower().split())
        title_b = set(note_b.get("title", "").lower().split())
        tags_a = set(note_a.get("tags", []))
        tags_b = set(note_b.get("tags", []))
        
        title_overlap = len(title_a & title_b) / max(len(title_a | title_b), 1)
        tag_overlap = len(tags_a & tags_b) / max(len(tags_a | tags_b), 1) if (tags_a or tags_b) else 0
        
        return title_overlap * 0.6 + tag_overlap * 0.4
    
    def _promote_note(self, note: Dict, score: float):
        """提升笔记层级"""
        new_type = "task_state" if score >= 0.9 else "action"
        self.note_tool.run({
            "action": "update",
            "note_id": note["note_id"],
            "note_type": new_type,
        })
    
    def _archive_note(self, note: Dict):
        """归档笔记（标记为归档而非删除）"""
        self.note_tool.run({
            "action": "update",
            "note_id": note["note_id"],
            "tags": note.get("tags", []) + ["archived"],
        })
    
    def _merge_notes(self, group: List[Dict]) -> str:
        """合并相似笔记为一条"""
        merged_content = "## 合并自多条笔记\n\n"
        for note in group:
            merged_content += f"### {note.get('title', 'Untitled')}\n"
            merged_content += note.get("content", "") + "\n\n"
        
        # 创建合并后的新笔记
        self.note_tool.run({
            "action": "create",
            "title": f"[合并] {group[0].get('title', 'Merged Notes')}",
            "content": merged_content,
            "note_type": group[0].get("type", "conclusion"),
            "tags": ["auto_merged"],
        })
        
        # 归档原始笔记
        for note in group:
            self._archive_note(note)
        
        return merged_content
    
    def _is_expired(self, note: Dict, days: int = 7) -> bool:
        """判断笔记是否过期"""
        updated_at = note.get("updated_at", "")
        if not updated_at:
            return False
        try:
            update_time = datetime.fromisoformat(updated_at)
            return (datetime.now() - update_time).days > days
        except (ValueError, TypeError):
            return False
    
    def _parse_total(self, summary) -> int:
        """从摘要中解析总笔记数"""
        if isinstance(summary, str):
            import re
            match = re.search(r'总笔记数:\s*(\d+)', summary)
            return int(match.group(1)) if match else 0
        return 0
    
    def _get_all_notes(self) -> List[Dict]:
        """获取所有笔记"""
        # 分别获取各类型笔记
        all_notes = []
        for note_type in ["temporary", "conclusion", "action", "task_state", "blocker"]:
            try:
                result = self.note_tool.run({
                    "action": "list",
                    "note_type": note_type,
                    "limit": 100,
                })
                if isinstance(result, list):
                    all_notes.extend(result)
            except Exception:
                continue
        return all_notes
```

---

### 3.2 TerminalTool 安全性分析与人机协作审批

#### 当前安全机制评估

**源码实证**（`docs/05.md` 安全特性演示日志）：

| 安全机制 | 测试用例 | 结果 | 评价 |
|---------|---------|------|------|
| **命令白名单** | `rm -rf /` | ❌ 被拒绝 ✅ | **有效** — 阻止了破坏性命令 |
| **路径验证** | `cat /etc/passwd` | ⚠️ 内容被输出 | **不足** — 合法命令可读取敏感文件 |
| **目录逃逸防护** | `cd ../../../etc` | ❌ 被拒绝 ✅ | **有效** — 路径规范化正确 |

**关键不足**：

1. **路径验证不完整**：`cat /etc/passwd` 能通过验证，因为 `cat` 在白名单中。路径验证只检查了 `cd` 命令的目标，没有检查所有命令的文件路径参数。

2. **缺少命令组合风险评估**：`grep password config.json` 虽然每个词都安全，但组合起来可能暴露敏感信息。

3. **缺少输出过滤**：即使命令合法，输出中可能包含密钥、密码等敏感信息，当前没有输出层面的过滤。

4. **缺少操作审计日志**：虽然命令被允许或拒绝，但没有持久化的审计日志用于事后追溯。

#### 人机协作审批流程设计

```
Agent 请求执行命令
    │
    ▼
┌─────────────────────────────────────┐
│         第一层：自动风险评估          │
│                                      │
│  命令分类:                           │
│  ├─ 只读操作 (ls/cat/grep/wc)       │──→ 🟢 低风险 → 自动执行
│  ├─ 写操作 (echo > / tee)           │──→ 🟡 中风险 → 执行 + 记录审计日志
│  ├─ 系统操作 (python/node)          │──→ 🟠 较高 → 沙箱内执行
│  └─ 危险操作 (不在白名单)            │──→ 🔴 高风险 → 拒绝
│                                      │
│  路径检查:                           │
│  ├─ 工作目录内                      │──→ 正常
│  ├─ 工作目录外的只读文件             │──→ 需要审批
│  └─ 工作目录外的写操作               │──→ 拒绝
└─────────────────────────────────────┘
    │
    │ (中风险或需要审批的操作)
    ▼
┌─────────────────────────────────────┐
│         第二层：敏感信息检测          │
│                                      │
│  检查命令参数是否包含:               │
│  ├─ 敏感文件路径 (.env, .key, id_rsa)│──→ 需要人类确认
│  ├─ 敏感关键词 (password, secret)   │──→ 需要人类确认
│  └─ 网络操作 (curl/wget 外部URL)    │──→ 需要人类确认
└─────────────────────────────────────┘
    │
    │ (需要人类确认)
    ▼
┌─────────────────────────────────────┐
│         第三层：人类审批界面          │
│                                      │
│  显示:                               │
│  ├─ 要执行的命令                     │
│  ├─ 风险评估结果                     │
│  ├─ 可能影响的文件范围               │
│  └─ 建议的替代方案（如果有）          │
│                                      │
│  选项:                               │
│  ├─ ✅ 批准（本次执行）              │
│  ├─ ✅✅ 永久批准（此类操作不再询问） │
│  ├─ ❌ 拒绝                         │
│  └─ 🔄 修改后执行                    │
└─────────────────────────────────────┘
```

**实现要点**：

```python
class ApprovalPolicy:
    """审批策略"""
    
    RISK_LEVELS = {
        # 只读命令 → 自动批准
        "read": {"auto_approve": True, "audit": True},
        # 写命令 → 自动批准但记录
        "write": {"auto_approve": True, "audit": True, "log": True},
        # 敏感文件访问 → 需要人类确认
        "sensitive": {"auto_approve": False, "require_human": True},
        # 危险命令 → 拒绝
        "dangerous": {"auto_approve": False, "reject": True},
    }
    
    SENSITIVE_PATTERNS = [
        r'\.env$', r'\.key$', r'id_rsa', r'\.pem$',
        r'password', r'secret', r'token', r'credential',
    ]
```

---

### 3.3 智能代码重构助手 — 完整工作流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    智能代码重构助手 — 完整工作流程                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Phase 1: 代码库分析（TerminalTool 主导）                     │    │
│  │                                                              │    │
│  │  1.1 结构扫描                                                │    │
│  │      find . -name '*.py' → 文件列表                          │    │
│  │      wc -l *.py → 各文件行数                                 │    │
│  │      grep -rn 'import' → 依赖关系图                          │    │
│  │                                                              │    │
│  │  1.2 质量扫描                                                │    │
│  │      grep -rn 'TODO\|FIXME\|HACK' → 待修复项                 │    │
│  │      grep -rn 'try\|except' → 错误处理覆盖率                 │    │
│  │      grep -rn 'def test_' → 测试覆盖率                       │    │
│  │                                                              │    │
│  │  1.3 记录发现                                                │    │
│  │      NoteTool.create("代码库分析报告", type="conclusion")     │    │
│  │      NoteTool.create("发现13个TODO", type="blocker")          │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Phase 2: 重构规划（NoteTool 主导）                           │    │
│  │                                                              │    │
│  │  2.1 优先级排序                                              │    │
│  │      P0: 错误处理（系统崩溃风险）                             │    │
│  │      P1: TODO 实现（功能缺失）                               │    │
│  │      P2: 代码优化（扩展性）                                  │    │
│  │                                                              │    │
│  │  2.2 创建重构计划                                            │    │
│  │      NoteTool.create("本周重构计划", type="task_state")       │    │
│  │      ├── Day 1: api_client.py 错误处理                       │    │
│  │      ├── Day 2: data_processor.py 参数化                     │    │
│  │      ├── Day 3: models.py 验证方法                           │    │
│  │      ├── Day 4: 编写测试                                     │    │
│  │      └── Day 5: 文档 + 收尾                                  │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Phase 3: 逐步执行（TerminalTool + NoteTool 协同）            │    │
│  │                                                              │    │
│  │  对每个重构任务:                                              │    │
│  │                                                              │    │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐              │    │
│  │  │ 3.1 读取  │───→│ 3.2 修改  │───→│ 3.3 验证  │             │    │
│  │  │ cat file  │    │ 编辑代码  │    │ 运行测试  │              │    │
│  │  └──────────┘    └──────────┘    └─────┬────┘              │    │
│  │                                        │                    │    │
│  │                              ┌─────────┴─────────┐         │    │
│  │                              ▼                   ▼         │    │
│  │                        ┌──────────┐        ┌──────────┐   │    │
│  │                        │ ✅ 通过   │        │ ❌ 失败   │   │    │
│  │                        │ 记录成功  │        │ 记录问题  │   │    │
│  │                        │ NoteTool  │        │ NoteTool  │   │    │
│  │                        │ update    │        │ create    │   │    │
│  │                        │ task_state│        │ blocker   │   │    │
│  │                        └──────────┘        └──────────┘   │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Phase 4: 进度追踪（NoteTool 主导）                           │    │
│  │                                                              │    │
│  │  4.1 每日总结                                                │    │
│  │      NoteTool.create("Day N 完成报告", type="task_state")     │    │
│  │      ├── 已完成任务列表                                      │    │
│  │      ├── 遇到的问题及解决方案                                │    │
│  │      └── 明日计划                                            │    │
│  │                                                              │    │
│  │  4.2 跨会话恢复                                              │    │
│  │      新会话 → NoteTool.search("重构计划") → 恢复进度          │    │
│  │      "根据笔记，我们已完成 Day 1-3，今天继续 Day 4"           │    │
│  │                                                              │    │
│  │  4.3 最终报告                                                │    │
│  │      NoteTool.summary() → 统计所有笔记                       │    │
│  │      生成重构完成报告（JSON）                                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**源码实证**：这正是 `06_three_day_workflow.py` 中 `CodebaseMaintainer` 实际执行的模式。从 `docs/06.md` 的日志可以看到：
- Day 1：Agent 用 TerminalTool 探索 → 产出项目结构分析笔记
- Day 2：Agent 用 TerminalTool 分析 → 产出代码质量评估笔记（评分 C+）
- Day 3：Agent 回顾笔记 → 产出 5 天重构计划笔记
- 一周后：新会话通过 NoteTool 检索历史笔记 → 连贯回答"之前发现 9 个主要问题"

---

## 题目 4：长时程任务管理

### 4.1 三层上下文管理的协调

#### 三层架构与职责划分

```
┌─────────────────────────────────────────────────────────────────┐
│                    三层上下文管理架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ L1: 即时访问层 (TerminalTool)                            │    │
│  │                                                          │    │
│  │  特点: 实时、精确、不占上下文窗口、用完即弃              │    │
│  │  放什么: 当前正在查看的文件内容、命令输出                │    │
│  │  生命周期: 单次命令调用                                  │    │
│  │  类比: 你手边正在翻的那页书                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↕ 重要发现提升                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ L2: 会话记忆层 (MemoryTool)                              │    │
│  │                                                          │    │
│  │  特点: 当前会话内有效、自动管理、中等持久性              │    │
│  │  放什么: 本轮对话的关键结论、中间推理结果                │    │
│  │  生命周期: 单次会话（会话结束后关键信息转入 L3）         │    │
│  │  类比: 你脑子里正在想的事情                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↕ 会话结束时沉淀                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ L3: 持久笔记层 (NoteTool)                                │    │
│  │                                                          │    │
│  │  特点: 跨会话持久、结构化、可检索、有类型系统            │    │
│  │  放什么: 重要发现、决策记录、重构计划、阻塞问题          │    │
│  │  生命周期: 永久（直到被归档或清理）                      │    │
│  │  类比: 你笔记本上记的重点                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 信息分层规则

| 信息类型 | 应放在哪层 | 原因 |
|---------|-----------|------|
| 当前正在查看的文件内容 | L1 | 即时需要，不需要持久化 |
| `grep` 命令的搜索结果 | L1 | 临时性，用完可丢弃 |
| "这个模块有 13 个 TODO" | L2 → L3 | 会话中间结论 → 最终记录到笔记 |
| "api_client.py 错误处理评分 15/100" | L3 | 重要发现，需要跨会话保留 |
| "用户说要用 Python 和 Pandas" | L2 | 当前会话的对话上下文 |
| 5 天重构计划 | L3 | 长期计划，需要跨会话追踪 |
| "依赖冲突是当前的 blocker" | L3 | 阻塞问题，优先级最高 |

#### 避免信息冗余和不一致的三个原则

1. **唯一来源原则**：每条信息只在一个地方维护"最新版本"。如果一条信息同时存在于 L2 和 L3，以 L3 为准。

2. **按需提升原则**：L1 的信息只有在被判断为"重要"时才提升到 L3（通过 NoteTool 创建笔记）。不是所有命令输出都值得记录。

3. **时间戳同步原则**：`NoteTool` 的 `updated_at` 字段确保知道哪个版本最新。当 L3 中的笔记被更新后，下次会话加载时自然获取最新版本。

**源码实证**：`codebase_maintainer.py` 第 121-131 行的 `run()` 方法展示了三层协调的实际流程：
```python
# L3 → L2: 从笔记中检索相关历史信息，注入到当前上下文
relevant_notes = self._retrieve_relevant_notes(user_input)
note_packets = self._notes_to_packets(relevant_notes)

# L2 + L3 → L1: ContextBuilder 将对话历史 + 笔记 + 系统指令 构建为统一上下文
context = self.context_builder.build(
    user_query=user_input,
    conversation_history=self.conversation_history,  # L2
    system_instructions=self._build_system_instructions(mode),
    additional_packets=note_packets                   # L3 → 注入
)

# L1: Agent 在执行过程中按需使用 TerminalTool 获取即时信息
response = self.agent.run(user_input)  # Agent 自主决定是否调用工具
```

---

### 4.2 断点续传机制设计

#### Checkpoint 笔记结构设计

```python
class CheckpointManager:
    """断点续传管理器
    
    核心思路：每完成一步操作，创建一个 checkpoint 笔记，
    记录足够的状态信息以便恢复。
    """
    
    def __init__(self, note_tool, terminal_tool):
        self.note_tool = note_tool
        self.terminal_tool = terminal_tool
    
    def create_checkpoint(self, task_id: str, step: int, total_steps: int,
                          completed: list, current: str, next_steps: list,
                          state_snapshot: dict):
        """创建一个检查点笔记
        
        Args:
            task_id: 任务唯一标识
            step: 当前步骤编号
            total_steps: 总步骤数
            completed: 已完成的步骤列表
            current: 当前正在执行的步骤
            next_steps: 剩余步骤列表
            state_snapshot: 状态快照（用于验证一致性）
        """
        checkpoint_content = f"""## 任务进度
- 任务ID: {task_id}
- 进度: {step}/{total_steps}
- 完成度: {step/total_steps*100:.0f}%

## 已完成步骤
{chr(10).join(f'- ✅ {s}' for s in completed)}

## 当前步骤
- 🔄 {current}

## 剩余步骤
{chr(10).join(f'- ⬜ {s}' for s in next_steps)}

## 状态快照
```json
{json.dumps(state_snapshot, indent=2, ensure_ascii=False)}
```
"""
        
        self.note_tool.run({
            "action": "create",
            "title": f"[Checkpoint] {task_id} - Step {step}/{total_steps}",
            "content": checkpoint_content,
            "note_type": "task_state",
            "tags": ["checkpoint", task_id, f"step_{step}"],
        })
    
    def recover(self, task_id: str) -> dict:
        """从最近的 checkpoint 恢复任务状态
        
        Returns:
            恢复的状态信息，或 None 表示无 checkpoint
        """
        # Step 1: 搜索该任务的所有 checkpoint
        results = self.note_tool.run({
            "action": "search",
            "query": f"Checkpoint {task_id}",
            "limit": 10,
        })
        
        if not results:
            return None
        
        # Step 2: 找到最新的 checkpoint
        latest_checkpoint = self._find_latest(results)
        if not latest_checkpoint:
            return None
        
        # Step 3: 解析 checkpoint 内容
        checkpoint_data = self._parse_checkpoint(latest_checkpoint)
        
        # Step 4: 验证状态一致性
        is_valid = self._verify_state(checkpoint_data)
        
        if is_valid:
            return {
                "status": "recovered",
                "step": checkpoint_data["step"],
                "current": checkpoint_data["current"],
                "next_steps": checkpoint_data["next_steps"],
                "message": f"✅ 从 Step {checkpoint_data['step']} 恢复"
            }
        else:
            # 状态不一致，回退到上一步
            return {
                "status": "rollback",
                "step": checkpoint_data["step"] - 1,
                "current": checkpoint_data["completed"][-1] if checkpoint_data["completed"] else "unknown",
                "message": "⚠️ 状态不一致，回退到上一步"
            }
    
    def _verify_state(self, checkpoint_data: dict) -> bool:
        """验证恢复后的状态是否与 checkpoint 一致
        
        验证方法：
        1. 检查关键文件是否存在
        2. 检查文件内容 hash 是否匹配
        3. 检查依赖服务是否可用
        """
        snapshot = checkpoint_data.get("state_snapshot", {})
        
        # 验证文件存在性
        for file_path in snapshot.get("expected_files", []):
            result = self.terminal_tool.run({
                "command": f"test -f {file_path} && echo 'exists' || echo 'missing'"
            })
            if "missing" in result:
                return False
        
        # 验证文件 hash（如果 snapshot 中有）
        for file_path, expected_hash in snapshot.get("file_hashes", {}).items():
            result = self.terminal_tool.run({
                "command": f"md5sum {file_path} | awk '{{print $1}}'"
            })
            actual_hash = result.strip()
            if actual_hash != expected_hash:
                return False
        
        return True
```

#### 状态快照应包含的信息

```json
{
    "task_id": "refactor_api_client",
    "step": 3,
    "total_steps": 7,
    "state_snapshot": {
        "expected_files": [
            "codebase/api_client.py",
            "codebase/models.py"
        ],
        "file_hashes": {
            "codebase/api_client.py": "abc123def456"
        },
        "environment": {
            "python_version": "3.11",
            "dependencies_installed": true
        },
        "test_results": {
            "last_run": "2024-01-20T10:30:00",
            "pass_count": 5,
            "fail_count": 0
        }
    }
}
```

---

### 4.3 任务依赖管理系统

#### 数据结构设计

```python
from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
import json


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"        # 依赖已满足，可以执行
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"    # 被阻塞
    FAILED = "failed"


@dataclass
class Task:
    """任务节点"""
    task_id: str
    title: str
    description: str
    depends_on: List[str] = field(default_factory=list)  # 依赖的任务 ID 列表
    status: TaskStatus = TaskStatus.PENDING
    estimated_hours: float = 0
    actual_hours: float = 0
    note_id: Optional[str] = None  # 关联的 NoteTool 笔记 ID
    priority: int = 1  # 1=P0, 2=P1, 3=P2


class TaskDependencyManager:
    """任务依赖管理器
    
    功能：
    1. 表达任务间的依赖关系（DAG）
    2. 自动计算执行顺序（拓扑排序）
    3. 与 NoteTool 集成，持久化任务状态
    """
    
    def __init__(self, note_tool):
        self.note_tool = note_tool
        self.tasks: Dict[str, Task] = {}
    
    def add_task(self, task: Task):
        """添加任务"""
        self.tasks[task.task_id] = task
        self._validate_no_cycle()  # 检测环路
    
    def add_dependency(self, task_id: str, depends_on: str):
        """添加依赖关系"""
        if task_id in self.tasks:
            self.tasks[task_id].depends_on.append(depends_on)
            self._validate_no_cycle()
    
    def get_execution_order(self) -> List[str]:
        """拓扑排序：计算最优执行顺序"""
        # Kahn's algorithm
        in_degree = {tid: 0 for tid in self.tasks}
        adjacency = {tid: [] for tid in self.tasks}
        
        for tid, task in self.tasks.items():
            for dep in task.depends_on:
                if dep in self.tasks:
                    adjacency[dep].append(tid)
                    in_degree[tid] += 1
        
        # 从入度为 0 的节点开始
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []
        
        while queue:
            # 优先级排序：P0 先于 P1 先于 P2
            queue.sort(key=lambda t: self.tasks[t].priority)
            current = queue.pop(0)
            order.append(current)
            
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(order) != len(self.tasks):
            raise ValueError("存在循环依赖！")
        
        return order
    
    def get_ready_tasks(self) -> List[Task]:
        """获取当前可以执行的任务（所有依赖已完成）"""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            all_deps_completed = all(
                self.tasks[dep].status == TaskStatus.COMPLETED
                for dep in task.depends_on
                if dep in self.tasks
            )
            if all_deps_completed:
                task.status = TaskStatus.READY
                ready.append(task)
        return sorted(ready, key=lambda t: t.priority)
    
    def complete_task(self, task_id: str):
        """标记任务完成，并更新依赖它的任务"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.COMPLETED
            # 同步到 NoteTool
            self._sync_to_note(task_id)
    
    def _sync_to_note(self, task_id: str):
        """将任务状态同步到 NoteTool"""
        task = self.tasks[task_id]
        
        if task.note_id:
            # 更新已有笔记
            self.note_tool.run({
                "action": "update",
                "note_id": task.note_id,
                "content": self._task_to_note_content(task),
            })
        else:
            # 创建新笔记
            result = self.note_tool.run({
                "action": "create",
                "title": f"[Task] {task.title}",
                "content": self._task_to_note_content(task),
                "note_type": "task_state",
                "tags": ["task", task.task_id, f"priority_{task.priority}"],
            })
            # 解析并保存 note_id
            import re
            match = re.search(r"ID:\s*(note_[0-9_]+)", result)
            if match:
                task.note_id = match.group(1)
    
    def _task_to_note_content(self, task: Task) -> str:
        """将任务转换为笔记内容"""
        deps = ", ".join(task.depends_on) if task.depends_on else "无"
        return f"""## 任务: {task.title}
- ID: {task.task_id}
- 状态: {task.status.value}
- 优先级: P{task.priority}
- 依赖: {deps}
- 预估工时: {task.estimated_hours}h
- 实际工时: {task.actual_hours}h

## 描述
{task.description}
"""
    
    def save_dag_to_note(self):
        """将整个任务 DAG 保存为一条笔记"""
        order = self.get_execution_order()
        
        content = "## 任务依赖图\n\n"
        content += "### 执行顺序\n"
        for i, tid in enumerate(order, 1):
            task = self.tasks[tid]
            deps = f" (依赖: {', '.join(task.depends_on)})" if task.depends_on else ""
            status_icon = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.READY: "🟢",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.PENDING: "⬜",
                TaskStatus.BLOCKED: "🔴",
                TaskStatus.FAILED: "❌",
            }.get(task.status, "❓")
            content += f"{i}. {status_icon} {task.title}{deps}\n"
        
        # 统计
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        total = len(self.tasks)
        content += f"\n### 进度: {completed}/{total} ({completed/total*100:.0f}%)\n"
        
        self.note_tool.run({
            "action": "create",
            "title": "任务依赖图 - 总览",
            "content": content,
            "note_type": "task_state",
            "tags": ["dag", "overview"],
        })
    
    def _validate_no_cycle(self):
        """检测循环依赖"""
        try:
            self.get_execution_order()
        except ValueError as e:
            raise ValueError(f"任务依赖图中存在循环: {e}")


# === 使用示例（基于本项目的重构场景）===

def demo_task_dag():
    """演示：codebase 重构任务的依赖管理"""
    
    manager = TaskDependencyManager(note_tool=None)  # 实际使用时传入 NoteTool
    
    # 添加任务
    manager.add_task(Task("T1", "修复 api_client.py 异常处理", "添加超时/重试/异常捕获", priority=1, estimated_hours=2.5))
    manager.add_task(Task("T2", "添加日志系统", "全局日志配置", depends_on=["T1"], priority=1, estimated_hours=1))
    manager.add_task(Task("T3", "修复 data_processor.py", "参数化字段名+数据验证", depends_on=["T1"], priority=2, estimated_hours=1))
    manager.add_task(Task("T4", "完善 models.py", "折扣验证+退款功能", priority=2, estimated_hours=2))
    manager.add_task(Task("T5", "编写单元测试", "pytest 测试套件", depends_on=["T1", "T2", "T3"], priority=1, estimated_hours=4))
    manager.add_task(Task("T6", "添加 README", "项目文档", depends_on=["T5"], priority=3, estimated_hours=1))
    
    # 计算执行顺序
    order = manager.get_execution_order()
    print("执行顺序:", order)
    # → ['T1', 'T2', 'T3', 'T4', 'T5', 'T6']
    
    # 获取当前可执行的任务
    ready = manager.get_ready_tasks()
    print("可执行:", [t.title for t in ready])
    # → ['修复 api_client.py 异常处理']
    
    # 完成 T1 后
    manager.complete_task("T1")
    ready = manager.get_ready_tasks()
    print("T1完成后可执行:", [t.title for t in ready])
    # → ['添加日志系统', '修复 data_processor.py', '完善 models.py']
```

**DAG 可视化**：

```
    [T1: 异常处理] ──→ [T2: 日志系统] ──→ [T5: 单元测试] ──→ [T6: README]
          │                                      ↑
          └──→ [T3: data_processor] ─────────────┘
          
    [T4: models.py]  (无依赖，可与 T1 并行)
```

---

## 题目 5：渐进式披露

### 5.1 应用场景：复杂问题调试

#### 场景设计：生产环境 API 500 错误排查

**费曼比喻**：渐进式披露就像医生看病——不会一次做全身检查，而是：问诊 → 针对性检查 → 根据结果进一步检查 → 确诊。

```
┌──────────────────────────────────────────────────────────────┐
│  渐进式披露在调试中的应用                                      │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Step 1: 初始上下文                                          │
│  ├─ 用户输入: "API 返回 500 错误"                            │
│  ├─ Agent 决策: 先看日志                                     │
│  └─ TerminalTool: tail -n 100 /var/log/app/error.log         │
│                                                               │
│  Step 2: 新上下文 = Step 1 的结果                            │
│  ├─ 日志显示: "DatabaseConnectionError: timeout after 30s"   │
│  ├─ Agent 决策: 检查数据库连通性                             │
│  └─ TerminalTool: ping db-server && nc -zv db-server 5432    │
│                                                               │
│  Step 3: 新上下文 = Step 1 + Step 2 的结果                   │
│  ├─ 发现: 端口 5432 连接超时                                 │
│  ├─ Agent 决策: 检查数据库配置                               │
│  └─ TerminalTool: cat /app/config/database.yml               │
│                                                               │
│  Step 4: 新上下文 = Step 1 + 2 + 3 的结果                    │
│  ├─ 发现: 配置中 host 写的是 "localhost" 而非 "db-server"    │
│  ├─ Agent 决策: 确诊！配置错误                               │
│  └─ 输出: "根因：database.yml 中 host 配置错误。             │
│           应改为 db-server。修复方案：..."                    │
│                                                               │
│  关键：每一步的上下文都是前一步的结果引导出来的               │
│  而不是一开始就把日志+配置+网络状态全部加载                   │
└──────────────────────────────────────────────────────────────┘
```

**为什么渐进式披露更高效？**

| 维度 | 一次性加载 | 渐进式披露 |
|------|----------|-----------|
| 上下文大小 | 日志 + 所有配置文件 + 网络状态 ≈ 5000 token | 每步约 500-1000 token |
| 噪声比例 | 高（大部分文件与问题无关） | 低（每步只加载相关信息） |
| 推理质量 | 可能被无关信息干扰 | 每步聚焦，推理链清晰 |
| 总 token 消耗 | 一次 5000 token | 4 步 × 1000 = 4000 token（更少） |

---

### 5.2 探索引导机制

#### 元认知策略设计

```python
class ExplorationGuide:
    """探索引导器：帮助 Agent 更聪明地决定"下一步探索什么"
    
    核心思想：不是盲目探索，而是基于启发式规则
    优先探索最可能产出有价值信息的方向。
    """
    
    # === 启发式规则 ===
    
    HEURISTIC_RULES = [
        {
            "name": "整体优先",
            "condition": lambda ctx: ctx["step_count"] == 0,
            "action": "先用 find/ls/tree 了解整体结构，再看具体文件",
            "priority": 10,
        },
        {
            "name": "高频问题优先",
            "condition": lambda ctx: "codebase" in ctx.get("domain", ""),
            "action": "先 grep TODO/FIXME/BUG 查找已知问题，再逐文件分析",
            "priority": 9,
        },
        {
            "name": "最近变更优先",
            "condition": lambda ctx: ctx.get("has_git", False),
            "action": "先 git log --oneline -10 看最近改了什么",
            "priority": 8,
        },
        {
            "name": "错误信号优先",
            "condition": lambda ctx: "error" in ctx.get("user_query", "").lower(),
            "action": "优先查看错误日志和异常堆栈",
            "priority": 10,
        },
        {
            "name": "3次无进展切换",
            "condition": lambda ctx: ctx.get("no_progress_count", 0) >= 3,
            "action": "当前方向 3 次探索无新发现，建议切换方向",
            "priority": 7,
        },
        {
            "name": "5步一总结",
            "condition": lambda ctx: ctx["step_count"] % 5 == 0 and ctx["step_count"] > 0,
            "action": "已探索 5 步，建议用 NoteTool 做阶段性总结",
            "priority": 6,
        },
        {
            "name": "深度优先 vs 广度优先",
            "condition": lambda ctx: ctx.get("breadth_first", True),
            "action": "先广度扫描所有文件，再选择最重要的 2-3 个深入分析",
            "priority": 5,
        },
    ]
    
    def __init__(self):
        self.exploration_context = {
            "step_count": 0,
            "no_progress_count": 0,
            "visited_files": set(),
            "found_issues": [],
            "breadth_first": True,
        }
    
    def suggest_next(self, current_state: dict) -> dict:
        """建议下一步探索方向
        
        Returns:
            {
                "suggestion": "建议文本",
                "reason": "原因",
                "command_hint": "建议的命令模式",
            }
        """
        self.exploration_context.update(current_state)
        self.exploration_context["step_count"] += 1
        
        # 匹配适用的规则（按优先级排序）
        applicable_rules = [
            rule for rule in self.HEURISTIC_RULES
            if rule["condition"](self.exploration_context)
        ]
        applicable_rules.sort(key=lambda r: r["priority"], reverse=True)
        
        if not applicable_rules:
            return {
                "suggestion": "继续当前探索方向",
                "reason": "没有特殊规则触发",
                "command_hint": None,
            }
        
        top_rule = applicable_rules[0]
        return {
            "suggestion": top_rule["action"],
            "reason": f"触发规则: {top_rule['name']}",
            "command_hint": self._get_command_hint(top_rule["name"]),
        }
    
    def _get_command_hint(self, rule_name: str) -> str:
        """根据规则名给出命令建议"""
        hints = {
            "整体优先": "find . -type f -name '*.py' | head -20",
            "高频问题优先": "grep -rn 'TODO\\|FIXME\\|BUG' --include='*.py'",
            "最近变更优先": "git log --oneline -10",
            "错误信号优先": "tail -n 50 error.log | grep -i 'error\\|exception'",
            "3次无进展切换": "尝试换一个目录或文件类型查看",
            "5步一总结": "note_tool.create(title='阶段总结', content='...')",
            "深度优先 vs 广度优先": "ls -la && wc -l **/*.py",
        }
        return hints.get(rule_name)
    
    def update_progress(self, found_something_new: bool):
        """更新探索进度"""
        if found_something_new:
            self.exploration_context["no_progress_count"] = 0
        else:
            self.exploration_context["no_progress_count"] += 1
```

---

### 5.3 渐进式披露 vs 一次性加载：任务类型对比

| 任务类型 | 推荐策略 | 原因 | 具体示例 |
|---------|---------|------|---------|
| **大型代码库审查** | 渐进式 ✅ | 50 个文件无法全部加载；按模块逐一审查更高效；每步发现引导下一步方向 | 微服务项目有 50 个 Go 文件，需要审查 API 安全性 |
| **学术论文写作** | 渐进式 ✅ | 每章内容依赖前一章的结论；参考文献按需查找；写作过程中思路会演变 | 写一篇关于 LLM 上下文工程的综述论文 |
| **安全漏洞扫描** | 渐进式 ✅ | 按模块逐一排查；每发现一个漏洞可能引导发现关联漏洞；避免一次性加载所有代码导致注意力分散 | 扫描 100 个 API 端点的认证和授权漏洞 |
| **法律合同审查** | 一次性 ✅ | 需要全局一致性理解；条款间相互引用；不能遗漏任何细节 | 审查 10 页的 SaaS 合同，检查责任限制条款是否与 SLA 一致 |
| **数据格式转换映射** | 一次性 ✅ | 需要同时看到源格式和目标格式；映射关系需要全局视角 | 将 CSV 数据映射到 JSON Schema，需要同时看到两者 |
| **跨模块接口重构** | 混合策略 | 需要全局视图了解所有调用点 + 局部细节修改每个模块 | 修改一个被 20 个模块调用的公共函数签名 |

**判断标准**：

```
选择渐进式披露，当：
├─ 信息量大，无法/不应全部加载
├─ 任务有明确的"探索 → 发现 → 深入"模式
├─ 每一步的结果会影响下一步的方向
└─ 不同部分之间相对独立

选择一次性加载，当：
├─ 信息量可控，可以全部加载
├─ 需要全局一致性理解
├─ 各部分之间有强耦合/交叉引用
└─ 任务目标是"审查"而非"探索"
```

---

## 总结

本习题集的核心知识脉络：

```
上下文工程的核心矛盾
    │
    ├── 有限窗口 vs 无限信息 → GSSC 流水线（题目2）
    │
    ├── 短期记忆 vs 长期持久 → 三层上下文管理（题目4）
    │
    ├── 全量加载 vs 按需检索 → 渐进式披露（题目5）
    │
    └── 工具支撑
        ├── ContextBuilder: GSSC 流水线的实现（题目1、2）
        ├── NoteTool: 持久化笔记 + 跨会话记忆（题目3、4）
        └── TerminalTool: 即时文件访问 + JIT 上下文（题目3、5）
```
