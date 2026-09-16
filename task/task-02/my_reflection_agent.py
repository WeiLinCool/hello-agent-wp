"""
my_reflection_agent.py
文档编写专用的 Reflection Agent

功能特性：
- 面向文档编写的迭代优化（README、技术文档、API 文档等）
- 多维度质量评分（清晰度、完整性、准确性、格式规范）
- 文档结构感知（标题层级、代码示例、链接等）
- 版本追踪（记录每轮迭代的文档版本）
- 提前终止（评分达到阈值时自动停止）
"""

from typing import Optional, List, Dict, Any
from hello_agents import ReflectionAgent, HelloAgentsLLM, Config, Message
from hello_agents.agents.reflection_agent import Memory


# ==============================================================================
# 文档编写专用的提示词模板
# ==============================================================================

DOC_PROMPTS = {
    "initial": """你是一位资深技术文档工程师。请根据以下要求编写文档。

## 任务
{task}

## 文档要求
1. **结构清晰**：使用合理的标题层级（# → ## → ###），逻辑递进
2. **内容完整**：覆盖背景、核心内容、示例、注意事项
3. **表达简洁**：避免冗余，每句话都有信息量
4. **代码示例**：涉及技术内容时，提供可运行的代码示例
5. **读者友好**：考虑目标读者的知识水平，适当解释专业术语

## 输出格式
请直接输出 Markdown 格式的文档内容，不要包含额外的解释说明。""",

    "reflect": """你是一位严格的文档评审专家。请从以下 5 个维度评审这篇文档，每个维度打 1-10 分。

## 原始任务
{task}

## 待评审文档
{content}

## 评审维度

### 1. 结构完整性 (Structure)
- 是否有清晰的标题层级？
- 章节划分是否合理？
- 段落长度是否适中？

### 2. 内容准确性 (Accuracy)
- 技术描述是否准确？
- 代码示例是否正确可运行？
- 是否有过时或错误的信息？

### 3. 表达清晰度 (Clarity)
- 句子是否简洁明了？
- 专业术语是否有解释？
- 逻辑是否连贯？

### 4. 读者体验 (Readability)
- 是否有足够的示例？
- 是否有适当的列表辅助说明？
- 入门读者是否能理解？

### 5. 格式规范 (Formatting)
- Markdown 语法是否正确？
- 代码块是否标注语言？
- 是否有一致性（空格、标点、术语）？

## 输出格式
请严格按以下格式输出：

评分：
- 结构完整性: X/10
- 内容准确性: X/10
- 表达清晰度: X/10
- 读者体验: X/10
- 格式规范: X/10
- 综合评分: X/10

具体问题：
1. [问题描述] → [改进建议]
2. [问题描述] → [改进建议]
...

亮点：
- [值得保留的优点]

结论：[需要改进 / 无需改进]""",

    "refine": """你是一位资深技术文档工程师。请根据评审反馈改进文档。

## 原始任务
{task}

## 上一版文档
{last_attempt}

## 评审反馈
{feedback}

## 改进要求
1. 逐一解决评审中提出的每个问题
2. 保留文档中的亮点部分
3. 不要引入新的问题
4. 保持文档的整体结构稳定，除非评审建议调整

请直接输出改进后的完整 Markdown 文档。"""
}


# ==============================================================================
# 文档质量评分器
# ==============================================================================

class DocQualityScorer:
    """文档质量评分器 —— 从 LLM 评审文本中提取结构化评分"""

    DIMENSIONS = ["结构完整性", "内容准确性", "表达清晰度", "读者体验", "格式规范"]

    @staticmethod
    def parse_scores(reflection_text: str) -> Dict[str, int]:
        """从评审文本中解析各维度评分

        Args:
            reflection_text: LLM 返回的评审文本

        Returns:
            各维度评分字典，解析失败时返回默认值
        """
        import re
        scores = {}
        for dim in DocQualityScorer.DIMENSIONS:
            pattern = rf'{dim}[:：]\s*(\d+)\s*/\s*10'
            match = re.search(pattern, reflection_text)
            if match:
                scores[dim] = int(match.group(1))
            else:
                scores[dim] = 5

        # 综合评分
        pattern = r'综合评分[:：]\s*(\d+)\s*/\s*10'
        match = re.search(pattern, reflection_text)
        if match:
            scores["综合评分"] = int(match.group(1))
        else:
            scores["综合评分"] = sum(scores.values()) // len(DocQualityScorer.DIMENSIONS)

        return scores

    @staticmethod
    def needs_improvement(reflection_text: str) -> bool:
        """判断是否需要继续改进"""
        no_improve_markers = ["无需改进", "no need for improvement", "已经很好", "质量优秀"]
        return not any(marker in reflection_text.lower() for marker in no_improve_markers)

    @staticmethod
    def format_scores(scores: Dict[str, int]) -> str:
        """格式化评分为可视化字符串"""
        lines = []
        for dim, score in scores.items():
            bar = "█" * score + "░" * (10 - score)
            emoji = "🟢" if score >= 8 else "🟡" if score >= 6 else "🔴"
            lines.append(f"  {emoji} {dim}: {bar} {score}/10")
        return "\n".join(lines)


# ==============================================================================
# 文档版本追踪器
# ==============================================================================

class DocVersionTracker:
    """文档版本追踪器 —— 记录每轮迭代的文档快照"""

    def __init__(self):
        self.versions: List[Dict[str, Any]] = []

    def add_version(self, version_num: int, content: str, scores: Dict[str, int], phase: str):
        """记录一个文档版本"""
        self.versions.append({
            "version": version_num,
            "phase": phase,
            "content": content,
            "scores": scores,
            "word_count": len(content),
            "line_count": content.count("\n") + 1,
        })

    def get_improvement_summary(self) -> str:
        """生成改进摘要"""
        if len(self.versions) < 2:
            return "仅有一个版本，无法计算改进幅度。"

        first = self.versions[0]
        last = self.versions[-1]
        first_score = first["scores"].get("综合评分", 0)
        last_score = last["scores"].get("综合评分", 0)
        delta = last_score - first_score

        lines = [
            f"📊 文档迭代摘要（共 {len(self.versions)} 个版本）",
            f"  初始版本评分: {first_score}/10",
            f"  最终版本评分: {last_score}/10",
            f"  改进幅度: {'+' if delta >= 0 else ''}{delta} 分",
            f"  字数变化: {first['word_count']} → {last['word_count']} ({last['word_count'] - first['word_count']:+})",
        ]

        lines.append("\n  各维度评分变化:")
        for dim in DocQualityScorer.DIMENSIONS:
            first_dim = first["scores"].get(dim, 0)
            last_dim = last["scores"].get(dim, 0)
            d = last_dim - first_dim
            arrow = "↑" if d > 0 else "↓" if d < 0 else "→"
            lines.append(f"    {dim}: {first_dim} → {last_dim} {arrow}")

        return "\n".join(lines)

    def get_latest_content(self) -> str:
        """获取最新版本的文档内容"""
        if not self.versions:
            return ""
        return self.versions[-1]["content"]


# ==============================================================================
# 文档编写 Reflection Agent
# ==============================================================================

class MyReflectionAgent(ReflectionAgent):
    """
    文档编写专用的 Reflection Agent

    相比通用 ReflectionAgent 的改进：
    1. 面向文档编写的提示词模板（结构、格式、示例等）
    2. 多维度质量评分（5 个维度，每轮可视化展示）
    3. 版本追踪（记录每轮迭代的文档快照和改进幅度）
    4. 提前终止（综合评分达到阈值时自动停止）
    5. 改进摘要（任务结束后输出完整的迭代改进报告）

    使用示例：
        >>> agent = MyReflectionAgent(
        ...     name="文档工程师",
        ...     llm=llm,
        ...     max_iterations=3,
        ...     quality_threshold=8.0,
        ... )
        >>> result = agent.run("编写一个 Python 项目的 README.md")
    """

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        max_iterations: int = 3,
        quality_threshold: float = 8.0,
        custom_prompts: Optional[Dict[str, str]] = None,
    ):
        """
        初始化文档编写 Reflection Agent

        Args:
            name: Agent 名称
            llm: LLM 实例
            system_prompt: 系统提示词（可选，覆盖默认）
            config: 配置对象
            max_iterations: 最大迭代次数（默认 3）
            quality_threshold: 质量阈值，综合评分达到此值时提前终止（默认 8.0）
            custom_prompts: 自定义提示词模板
        """
        super().__init__(
            name=name,
            llm=llm,
            system_prompt=system_prompt or "你是一位资深技术文档工程师，擅长编写清晰、完整、读者友好的技术文档。",
            config=config,
            max_iterations=max_iterations,
            custom_prompts=custom_prompts or DOC_PROMPTS,
        )
        self.quality_threshold = quality_threshold
        self.scorer = DocQualityScorer()
        self.version_tracker = DocVersionTracker()
        self.all_scores: List[Dict[str, int]] = []

        print(f"✅ {name} 初始化完成")
        print(f"   最大迭代: {max_iterations} 轮 | 质量阈值: {quality_threshold}/10")

    def run(self, input_text: str, **kwargs) -> str:
        """
        运行文档编写 Reflection Agent

        流程：
        1. 初始撰写 → 评分
        2. 循环：评审 → 评分 → 判断是否达标 → 优化
        3. 输出最终文档 + 改进摘要

        Args:
            input_text: 文档编写任务描述
            **kwargs: 传递给 LLM 的额外参数

        Returns:
            最终优化后的文档内容
        """
        print(f"\n{'='*60}")
        print(f"📝 {self.name} 开始文档编写任务")
        print(f"   任务: {input_text[:80]}{'...' if len(input_text) > 80 else ''}")
        print(f"{'='*60}")

        # 重置状态
        self.memory = Memory()
        self.version_tracker = DocVersionTracker()
        self.all_scores = []

        # ── 1. 初始撰写 ──
        print(f"\n{'─'*40}")
        print("📄 阶段 1: 初始撰写")
        print(f"{'─'*40}")

        initial_prompt = self.prompts["initial"].format(task=input_text)
        initial_result = self._get_llm_response(initial_prompt, **kwargs)
        self.memory.add_record("execution", initial_result)

        # 对初始版本进行评审和评分
        initial_scores = self._score_document(input_text, initial_result, **kwargs)
        self.version_tracker.add_version(0, initial_result, initial_scores, "initial")
        self.all_scores.append(initial_scores)

        print(f"\n📊 初始版本评分:")
        print(self.scorer.format_scores(initial_scores))

        # ── 2. 迭代优化循环 ──
        for i in range(self.max_iterations):
            print(f"\n{'─'*40}")
            print(f"🔄 阶段 2.{i+1}: 第 {i+1}/{self.max_iterations} 轮迭代")
            print(f"{'─'*40}")

            last_result = self.memory.get_last_execution()

            # a. 评审
            print("\n🔍 评审中...")
            reflect_prompt = self.prompts["reflect"].format(
                task=input_text,
                content=last_result,
            )
            feedback = self._get_llm_response(reflect_prompt, **kwargs)
            self.memory.add_record("reflection", feedback)

            # b. 解析评分
            scores = self.scorer.parse_scores(feedback)
            self.all_scores.append(scores)

            print(f"\n📊 第 {i+1} 轮评分:")
            print(self.scorer.format_scores(scores))

            # c. 检查是否需要停止
            overall = scores.get("综合评分", 0)
            if not self.scorer.needs_improvement(feedback):
                print(f"\n✅ 评审结论：文档已无需改进，提前终止。")
                break

            if overall >= self.quality_threshold:
                print(f"\n✅ 综合评分 {overall}/10 >= 阈值 {self.quality_threshold}/10，提前终止。")
                break

            # d. 优化
            print(f"\n✏️  根据反馈优化文档...")
            refine_prompt = self.prompts["refine"].format(
                task=input_text,
                last_attempt=last_result,
                feedback=feedback,
            )
            refined_result = self._get_llm_response(refine_prompt, **kwargs)
            self.memory.add_record("execution", refined_result)
            self.version_tracker.add_version(i + 1, refined_result, scores, "refined")

        # ── 3. 输出最终结果 ──
        final_result = self.memory.get_last_execution()

        print(f"\n{'='*60}")
        print("📊 文档迭代改进摘要")
        print(f"{'='*60}")
        print(self.version_tracker.get_improvement_summary())

        print(f"\n{'='*60}")
        print("📄 最终文档")
        print(f"{'='*60}")
        print(final_result)

        # 保存到历史记录
        self.add_message(Message(input_text, "user"))
        self.add_message(Message(final_result, "assistant"))

        return final_result

    def _score_document(self, task: str, content: str, **kwargs) -> Dict[str, int]:
        """对文档进行评分（复用评审提示词）"""
        reflect_prompt = self.prompts["reflect"].format(task=task, content=content)
        reflection = self._get_llm_response(reflect_prompt, **kwargs)
        return self.scorer.parse_scores(reflection)

    def get_version_history(self) -> List[Dict[str, Any]]:
        """获取文档版本历史"""
        return self.version_tracker.versions

    def get_all_scores(self) -> List[Dict[str, int]]:
        """获取所有轮次的评分"""
        return self.all_scores
