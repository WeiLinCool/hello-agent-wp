# NoteTool 改进解析：从 DSH `.agents/notes` 设计看 NoteTool 的进化方向

> **对比对象**
> - **A 系统**（hello-agent-wp NoteTool）：`task/task-04/` 中的 NoteTool 实现
> - **B 系统**（deepseek-harness Agent Notes）：`/Users/wlz/Documents/codeSpace/deepseek-harness/.agents/notes/` 的完整设计

---

## 〇、一句话定位差异

| 维度 | A: NoteTool | B: DSH Agent Notes |
|------|------------|-------------------|
| 本质 | **运行时工具** — Agent 在执行中 CRUD 笔记 | **治理基础设施** — 代码库级决策记录系统 |
| 类比 | 便签纸 + 文件夹 | RFC + 归档系统 + CI 门禁 |
| 生命周期 | 创建 → 更新 → 搜索 → 删除（扁平） | proposed → implemented → archived/rejected（状态机） |
| 身份标识 | `note_20260922_233343_0`（时间戳 ID） | `implemented/architecture/2026-06-11-tool-schemas-in-prompt-assembly.md`（路径即身份） |

---

## 一、命名约束设计：从"时间戳 ID"到"路径即元数据"

### 1.1 A 系统的命名方式

```
NoteTool 创建笔记 → 返回 ID: note_20260922_233343_0
存储位置: ./project_notes/ 目录下的 JSON 文件
```

**问题**：
- ID 只编码时间，不编码**分类**、**生命周期**、**主题**
- 要理解一条笔记的内容，必须读取其内容（`read` 操作）
- 无法通过路径直接判断"这是一条已归档的架构决策"还是"一个待处理的阻塞问题"
- 搜索完全依赖全文检索或标签匹配，没有结构性导航

### 1.2 B 系统的命名方式

```
.agents/notes/{lifecycle}/{class}/yyyy-mm-dd-topic-title.md
```

**路径编码了 5 个维度的元数据**：

| 路径段 | 编码的元数据 | 闭集约束 | 示例 |
|--------|------------|---------|------|
| `{lifecycle}` | 生命周期状态 | `proposed` / `implemented` / `rejected` / `archived` | `implemented` |
| `{class}` | 决策分类 | `feature` / `bug-fix` / `simplification` / `architecture` / `process` / `testing` | `architecture` |
| `yyyy-mm-dd` | 首次提出日期 | 日期格式校验 | `2026-06-11` |
| `topic-title` | 主题标识 | kebab-case，人类可读 | `tool-schemas-in-prompt-assembly` |
| `.md` | 格式 | 固定 | — |

**关键设计决策**：

1. **路径即索引**：不需要 `INDEX.md`（甚至明确禁止），浏览目录树就是索引
2. **闭集验证**：`agent-note-tree.ts` 中的 `AGENT_NOTE_CLASSES` 是封闭集合，新增分类需要同时更新代码和文档
3. **日期语义**：文件名日期是"首次提出日期"，不是"最后修改日期"——修改历史交给 git

### 1.3 对 NoteTool 的改进启示

**改进方向：引入路径编码的分类结构**

```
# 当前 NoteTool 的扁平存储
./project_notes/
├── note_20260922_233343_0.json
├── note_20260922_233343_1.json
└── note_20260923_001056_13.json

# 改进后的路径编码存储
./project_notes/
├── active/
│   ├── blocker/
│   │   └── 2026-09-22-dependency-version-conflict.md
│   ├── task-state/
│   │   └── 2026-09-23-refactoring-phase1.md
│   └── conclusion/
│       └── 2026-09-22-codebase-quality-assessment.md
└── archived/
    └── blocker/
        └── 2026-08-15-legacy-api-deprecation.md
```

**收益**：
- `ls active/blocker/` 就能看到所有未解决的阻塞问题
- 路径本身携带分类信息，不需要解析 JSON
- 归档是移动操作（`mv`），不是删除或标记

---

## 二、生命周期状态机：从"扁平类型"到"状态流转"

### 2.1 A 系统的生命周期

```
创建时指定 note_type: blocker | task_state | action | conclusion
    │
    ├── 可以 update 内容
    ├── 可以 search / list
    └── 可以 delete（不可恢复）
```

**问题**：
- 类型是**创建时固定**的，一条笔记从 `blocker` 变成已解决后，没有自然的流转路径
- 没有"已解决"状态——只能删除或手动更新内容
- 没有"被取代"的概念——新旧笔记可能共存且矛盾

### 2.2 B 系统的生命周期

```
                    ┌─────────────┐
                    │  proposed/  │ ← 提案，尚未实施
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼─────┐ ┌────▼────┐
              │implemented/│ │rejected/│
              │ (已实施)    │ │ (已拒绝) │
              └─────┬─────┘ └────┬────┘
                    │            │
              ┌─────▼─────┐     │
              │ archived/  │   删除
              │ (冻结归档)  │
              └────────────┘
```

**关键规则**：
1. **`proposed/` → `implemented/`**：必须重写 body——`## Proposal` 变为 `## Decision`（现在时），`## Acceptance criteria` 合并入 `## Consequences`
2. **`implemented/` 必须保持最新**：当代码移动了文件、重命名了包，Agent Note 在同一 PR 中更新（仅事实，不改决策）
3. **`archived/` 永久冻结**：SHA-256 哈希校验，任何编辑都会被门禁拒绝
4. **supersession 检查**：每条新 Note 必须搜索是否取代了旧 Note，完全取代则合并删除，部分取代则交叉链接

### 2.3 对 NoteTool 的改进启示

**改进方向：引入状态机 + supersession 检查**

```python
class NoteLifecycle(Enum):
    PROPOSED = "proposed"     # 计划/发现
    ACTIVE = "active"         # 正在执行/跟踪
    RESOLVED = "resolved"     # 已解决/已完成
    SUPERSEDED = "superseded" # 被新笔记取代
    ARCHIVED = "archived"     # 冻结归档

class NoteStateMachine:
    """笔记状态流转规则"""
    
    TRANSITIONS = {
        NoteLifecycle.PROPOSED:  [NoteLifecycle.ACTIVE, NoteLifecycle.RESOLVED],
        NoteLifecycle.ACTIVE:    [NoteLifecycle.RESOLVED, NoteLifecycle.SUPERSEDED],
        NoteLifecycle.RESOLVED:  [NoteLifecycle.ARCHIVED, NoteLifecycle.SUPERSEDED],
        NoteLifecycle.SUPERSEDED: [NoteLifecycle.ARCHIVED],
        NoteLifecycle.ARCHIVED:  [],  # 终态，不可流转
    }
    
    @classmethod
    def can_transition(cls, from_state: NoteLifecycle, to_state: NoteLifecycle) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, [])
    
    @classmethod
    def on_transition(cls, note: dict, to_state: NoteLifecycle) -> dict:
        """状态流转时的自动操作"""
        if to_state == NoteLifecycle.RESOLVED:
            # 解决时必须记录解决方案
            note["resolved_at"] = datetime.now().isoformat()
            note["resolution"] = note.get("resolution", "")  # 要求填写
        
        elif to_state == NoteLifecycle.SUPERSEDED:
            # 被取代时必须指向取代者
            note["superseded_by"] = note.get("superseded_by")  # 要求填写
        
        elif to_state == NoteLifecycle.ARCHIVED:
            # 归档时冻结，记录归档原因
            note["archived_at"] = datetime.now().isoformat()
            note["frozen_content_hash"] = cls._hash_content(note)
        
        note["lifecycle"] = to_state.value
        return note
```

**supersession 检查**（借鉴 DSH 的"每条新 Note 触发取代检查"）：

```python
def check_supersession(note_tool: NoteTool, new_note: dict) -> list:
    """创建新笔记时，检查是否取代了已有笔记
    
    Returns:
        需要被标记为 superseded 的旧笔记 ID 列表
    """
    # 搜索同主题的已有笔记
    title_keywords = extract_keywords(new_note["title"])
    existing = note_tool.run({
        "action": "search",
        "query": " ".join(title_keywords),
        "limit": 10,
    })
    
    superseded = []
    for note in existing:
        if note["note_id"] == new_note.get("note_id"):
            continue
        if note.get("lifecycle") in ("resolved", "archived", "superseded"):
            continue
        
        # 判断是否取代（基于标题相似度 + 内容重叠）
        if is_superseded(note, new_note):
            superseded.append(note["note_id"])
    
    return superseded
```

---

## 三、格式约束：从"自由文本"到"门禁验证的结构化文档"

### 3.1 A 系统的格式

```python
# NoteTool 创建笔记时，内容完全自由
notes.run({
    "action": "create",
    "title": "重构项目 - 第一阶段",
    "content": """## 完成情况
已完成数据模型层的重构...

## 下一步
重构业务逻辑层""",
    "note_type": "task_state",
    "tags": ["refactoring", "phase1"]
})
```

**问题**：
- 内容格式完全由 Agent 自由发挥
- 没有强制的"问题描述"、"决策依据"、"替代方案"等结构化段落
- 无法通过程序验证笔记是否包含关键信息

### 3.2 B 系统的格式

```markdown
# Agent Note: Tool schemas are part of the system-prompt assembly

Status: implemented

## Problem
（必须：问题的动机，独立于解决方案来写）

## Decision
（必须：已实施的决策，现在时态）

## Alternatives considered
（必须：每个被否决的方案及其否决原因）

## Consequences
（必须：决策的代价和收益）
```

**门禁验证**（`verify-agent-note-format.ts`）：

```typescript
// 每个生命周期有强制的段落结构
const REQUIRED: Record<string, string[]> = {
  proposed: ['## Proposal', '## Acceptance criteria', '## Risks'],
  implemented: ['## Decision', '## Consequences'],
  rejected: ['## Proposal'],
}

// implemented/ 中禁止提案式段落名
const BANNED_IMPLEMENTED = /^## (?:Proposal\b|Plan\b|Migration plan\b|Acceptance criteria\b)/i

// 必须有 Alternatives considered（或 grandfather 注释）
if (!hasSection && !hasGrandfather) fail('missing `## Alternatives considered`')
```

### 3.3 对 NoteTool 的改进启示

**改进方向：按 note_type 强制段落骨架**

```python
# 每种笔记类型的强制段落
NOTE_TEMPLATES = {
    "blocker": {
        "required_sections": ["## 问题描述", "## 影响范围", "## 阻塞原因"],
        "optional_sections": ["## 临时解决方案", "## 需要的资源"],
        "banned_sections": [],  # blocker 没有禁止的段落
    },
    "action": {
        "required_sections": ["## 目标", "## 具体步骤", "## 验收标准"],
        "optional_sections": ["## 时间安排", "## 依赖"],
        "banned_sections": [],
    },
    "task_state": {
        "required_sections": ["## 当前状态", "## 下一步"],
        "optional_sections": ["## 完成情况", "## 遇到的问题"],
        "banned_sections": [],
    },
    "conclusion": {
        "required_sections": ["## 结论", "## 依据", "## 替代方案"],
        "optional_sections": ["## 风险与假设", "## 下一步建议"],
        "banned_sections": [],
    },
    "decision": {
        "required_sections": ["## 问题", "## 决策", "## 替代方案", "## 后果"],
        "optional_sections": ["## 测试", "## 延期项"],
        "banned_sections": ["## 计划", "## 迁移方案"],  # 决策后不应再有"计划"式段落
    },
}


def validate_note_format(note: dict) -> list[str]:
    """验证笔记格式是否符合其类型的骨架要求"""
    errors = []
    note_type = note.get("type", "general")
    template = NOTE_TEMPLATES.get(note_type)
    
    if not template:
        return []  # 无模板约束
    
    content = note.get("content", "")
    sections = [line.strip() for line in content.split('\n') if line.startswith('## ')]
    
    # 检查必须段落
    for required in template["required_sections"]:
        if required not in sections:
            errors.append(f"缺少必须段落: {required}")
    
    # 检查禁止段落
    for section in sections:
        for banned in template["banned_sections"]:
            if section.startswith(banned):
                errors.append(f"禁止段落: {section}（{note_type} 类型不应包含此类段落）")
    
    return errors
```

---

## 四、按需构建回写：从"静态注入"到"Prompt Assembly 瀑布"

### 4.1 A 系统的上下文注入方式

```python
# codebase_maintainer.py 的 run() 方法
def run(self, user_input: str, mode: str = "auto") -> str:
    # 1. 检索笔记（一次性）
    relevant_notes = self._retrieve_relevant_notes(user_input)
    note_packets = self._notes_to_packets(relevant_notes)
    
    # 2. 构建上下文（一次性）
    context = self.context_builder.build(
        user_query=user_input,
        conversation_history=self.conversation_history,
        system_instructions=self._build_system_instructions(mode),
        additional_packets=note_packets  # 静态注入
    )
    
    # 3. 传给 Agent
    self.agent.system_prompt = context  # 设置后不再变化
    response = self.agent.run(user_input)
```

**问题**：
- 笔记在 prompt 构建时**一次性注入**，之后不再变化
- 没有"按需加载"机制——所有相关笔记在构建时就全部加入
- Agent 在执行过程中发现新信息，无法**动态回写**到上下文中
- system prompt 在 `agent.run()` 期间是**冻结**的

### 4.2 B 系统的 Prompt Assembly 瀑布

DSH 的 `@deepseek-ai/dsh-system-prompt` 实现了一个**响应式瀑布（waterfall）**架构：

```
┌─────────────────────────────────────────────────────────────────┐
│              system-prompt/assemble 瀑布                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  每次 LLM 调用前触发                                             │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Registered Sections (有序)                              │    │
│  │  ├─ persona (order: 0)                                  │    │
│  │  ├─ runtime-context (order: 100)                        │    │
│  │  ├─ tool guidance (order: 200)                          │    │
│  │  └─ skill catalog (order: 300)                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Waterfall Listeners (可拦截、可修改)                     │    │
│  │  ├─ plan mode listener: 替换 prompt + 过滤工具          │    │
│  │  ├─ model selection listener: 根据 scope 切换模型       │    │
│  │  └─ tool search listener: 渐进式工具披露                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Tool Providers (工具 schema 也是 prompt 的一部分)       │    │
│  │  ├─ tool registry → 当前可见工具的 JSON Schema          │    │
│  │  └─ skill tool → 按需加载的 SKILL.md 内容               │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Variable Interpolation ({{variable}} 运行时替换)        │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  最终 system prompt → 发给 LLM                                  │
│                                                                  │
│  关键：system-prompt/change 事件 → 下一轮自动重新组装            │
│  关键：scope 过滤 → 不同 agent/scope 看到不同的 prompt           │
└─────────────────────────────────────────────────────────────────┘
```

**核心设计差异**：

| 维度 | A: 静态注入 | B: 瀑布组装 |
|------|-----------|-----------|
| 触发时机 | `run()` 开始时一次 | 每次 LLM 调用前 |
| 可变性 | 构建后冻结 | 每轮可被 waterfall listener 修改 |
| 工具 schema | 固定注册 | 动态过滤（ToolSearch 渐进披露） |
| 技能加载 | 全量注入 | 按需加载（`skill` 工具调用时才加载 SKILL.md） |
| scope 感知 | 无 | 不同 scope 看到不同 prompt |
| 响应式 | 无 | `system-prompt/change` 事件驱动重新组装 |

### 4.3 对 NoteTool 的改进启示

**改进方向：从"一次性注入"到"按需构建 + 执行中回写"**

```python
class PromptAssemblyNoteProvider:
    """按需笔记提供者：参与 prompt 组装瀑布
    
    核心改变：笔记不再是"构建时一次性注入"，
    而是"每轮 LLM 调用前按需检索和组装"。
    """
    
    def __init__(self, note_tool: NoteTool):
        self.note_tool = note_tool
        self._change_listeners = []
    
    def on_change(self, listener):
        """注册变更监听器（当笔记创建/更新/状态变化时触发）"""
        self._change_listeners.append(listener)
    
    def _notify_change(self):
        """笔记变更时通知所有监听器 → 触发下一轮 prompt 重新组装"""
        for listener in self._change_listeners:
            listener()
    
    def assemble(self, context: AssembleContext) -> str:
        """每轮 LLM 调用前按需组装笔记上下文
        
        与 A 系统的关键区别：
        1. 每轮调用，不是每会话一次
        2. 根据当前 context（用户输入、Agent 状态、当前步骤）动态检索
        3. 可以与其他 prompt section 协调（如工具 schema）
        """
        query = context.current_query
        agent_state = context.agent_state
        
        # 策略 1: blocker 始终注入（最高优先级）
        blockers = self.note_tool.run({
            "action": "list",
            "note_type": "blocker",
            "limit": 3,
        })
        
        # 策略 2: 当前任务状态按需注入
        task_states = self.note_tool.run({
            "action": "list", 
            "note_type": "task_state",
            "limit": 2,
        })
        
        # 策略 3: 相关结论按查询检索
        conclusions = self.note_tool.run({
            "action": "search",
            "query": query,
            "limit": 3,
        }) if context.step > 0 else []  # 第一步不检索结论
        
        # 策略 4: 根据 Agent 当前模式调整
        if agent_state.mode == "explore":
            # 探索模式：注入架构类笔记
            pass
        elif agent_state.mode == "debug":
            # 调试模式：注入 blocker 和最近的错误结论
            pass
        
        return self._format_notes(blockers, task_states, conclusions)


class NoteWritebackTool:
    """笔记回写工具：Agent 在执行中可以主动回写笔记
    
    与 A 系统的关键区别：
    1. 回写触发 system-prompt/change → 下一轮 prompt 自动重新组装
    2. Agent 的笔记操作会"立即"影响后续上下文
    3. 支持"临时笔记 → 提升为正式笔记"的流转
    """
    
    def __init__(self, note_provider: PromptAssemblyNoteProvider):
        self.note_provider = note_provider
    
    def create(self, title: str, content: str, note_type: str, **kwargs):
        """创建笔记并触发 prompt 重新组装"""
        result = self.note_provider.note_tool.run({
            "action": "create",
            "title": title,
            "content": content,
            "note_type": note_type,
            **kwargs,
        })
        # 关键：通知 prompt 组装器笔记已变更
        self.note_provider._notify_change()
        return result
    
    def update(self, note_id: str, **updates):
        """更新笔记并触发 prompt 重新组装"""
        result = self.note_tool.run({
            "action": "update",
            "note_id": note_id,
            **updates,
        })
        self.note_provider._notify_change()
        return result
    
    def resolve(self, note_id: str, resolution: str):
        """解决一条 blocker/action 并记录解决方案"""
        return self.update(
            note_id,
            lifecycle="resolved",
            resolution=resolution,
            resolved_at=datetime.now().isoformat(),
        )
```

**执行中回写的完整流程**：

```
Agent 开始执行任务
    │
    ▼
┌─ Prompt Assembly (第 1 轮) ─────────────────────────┐
│  检索 blocker 笔记 → 注入 prompt                    │
│  Agent 看到: "当前有 2 个未解决的 blocker"           │
└──────────────────────────────────────────────────────┘
    │
    ▼
Agent 使用 TerminalTool 分析代码
    │
    ▼
Agent 发现新问题 → NoteWritebackTool.create(blocker)
    │
    ├── 笔记创建成功
    └── system-prompt/change 事件触发
    │
    ▼
┌─ Prompt Assembly (第 2 轮) ─────────────────────────┐
│  重新检索 blocker 笔记 → 新 blocker 已包含          │
│  Agent 看到: "当前有 3 个未解决的 blocker"           │
│  Agent 可以基于最新笔记状态做决策                    │
└──────────────────────────────────────────────────────┘
    │
    ▼
Agent 解决问题 → NoteWritebackTool.resolve(note_id)
    │
    ├── 笔记状态变为 resolved
    └── system-prompt/change 事件触发
    │
    ▼
┌─ Prompt Assembly (第 3 轮) ─────────────────────────┐
│  重新检索 → resolved 的笔记不再出现在 active 列表   │
│  Agent 看到: "当前有 2 个未解决的 blocker"           │
└──────────────────────────────────────────────────────┘
```

---

## 五、归档与冻结：从"可删除"到"不可变快照"

### 5.1 A 系统的归档

```python
# NoteTool 的"归档"就是加个 tag
notes.run({
    "action": "update",
    "note_id": "note_xxx",
    "tags": ["archived"],
})
# 或者直接删除
notes.run({
    "action": "delete",
    "note_id": "note_xxx",
})
```

**问题**：
- 归档的笔记可以被再次修改
- 删除不可恢复
- 无法验证"归档时的内容是什么"

### 5.2 B 系统的归档

```
归档流程:
1. 移动完整三元组（en.md + zh.md + i18n.yaml）到 archived/{class}/
2. 在 Status: implemented 下方插入 Archived: YYYY-MM-DD
3. 重新记录 sidecar 哈希
4. 修复或删除入站链接
5. 运行 pnpm run verify-archived-agent-notes --write 追加哈希到 manifest

归档后:
- SHA-256 内容哈希写入 manifest.json
- 任何编辑都会被 verify-archived-agent-notes 拒绝
- 文档门禁跳过归档笔记的出链检查
- 归档笔记不再作为"当前权威"
```

### 5.3 对 NoteTool 的改进启示

```python
import hashlib
import json

class NoteArchive:
    """笔记归档管理器：冻结 + 哈希校验"""
    
    def __init__(self, archive_dir: str):
        self.archive_dir = archive_dir
        self.manifest_path = os.path.join(archive_dir, "manifest.json")
    
    def archive(self, note: dict) -> str:
        """归档一条笔记：冻结内容 + 计算哈希"""
        # 1. 冻结内容
        frozen_content = json.dumps(note, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(frozen_content.encode()).hexdigest()
        
        # 2. 写入归档文件
        archive_path = os.path.join(
            self.archive_dir,
            note.get("type", "general"),
            f"{note['note_id']}.json"
        )
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)
        with open(archive_path, 'w') as f:
            json.dump({
                **note,
                "archived_at": datetime.now().isoformat(),
                "content_hash": f"sha256:{content_hash}",
                "frozen": True,
            }, f, ensure_ascii=False, indent=2)
        
        # 3. 更新 manifest
        self._update_manifest(archive_path, content_hash)
        
        return archive_path
    
    def verify(self) -> list[str]:
        """验证所有归档笔记的完整性"""
        errors = []
        manifest = self._load_manifest()
        
        for path, expected_hash in manifest.items():
            with open(path, 'r') as f:
                content = f.read()
            actual_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
            if actual_hash != expected_hash:
                errors.append(f"{path}: 内容哈希不匹配 (期望 {expected_hash}, 实际 {actual_hash})")
        
        return errors
```

---

## 六、总结：改进路线图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NoteTool 改进路线图                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Level 1: 命名约束 (路径即元数据)                                    │
│  ├─ 从 note_20260922_xxx.json → {lifecycle}/{class}/yyyy-mm-dd-*.md │
│  ├─ 闭集分类验证                                                    │
│  └─ 复杂度: 低 | 收益: 高（结构性导航）                              │
│                                                                      │
│  Level 2: 生命周期状态机                                             │
│  ├─ 从扁平 type → proposed/active/resolved/superseded/archived      │
│  ├─ 状态流转规则 + 流转时自动操作                                    │
│  ├─ supersession 检查（新笔记创建时检查是否取代旧笔记）              │
│  └─ 复杂度: 中 | 收益: 高（消除矛盾笔记）                            │
│                                                                      │
│  Level 3: 格式约束                                                   │
│  ├─ 按 note_type 强制段落骨架                                        │
│  ├─ 门禁验证（创建/更新时自动检查格式）                              │
│  ├─ "Alternatives considered" 强制（决策类笔记必须记录替代方案）     │
│  └─ 复杂度: 中 | 收益: 中（提升笔记质量）                            │
│                                                                      │
│  Level 4: 按需构建回写                                               │
│  ├─ 从"一次性注入" → "每轮 LLM 调用前按需组装"                     │
│  ├─ system-prompt/change 事件驱动重新组装                           │
│  ├─ Agent 执行中的笔记操作立即影响后续上下文                         │
│  └─ 复杂度: 高 | 收益: 极高（真正的动态上下文管理）                  │
│                                                                      │
│  Level 5: 归档冻结                                                   │
│  ├─ 归档 = 冻结 + SHA-256 哈希校验                                  │
│  ├─ manifest.json 不可变清单                                         │
│  ├─ 归档笔记不再作为当前权威                                         │
│  └─ 复杂度: 低 | 收益: 中（保证历史可信性）                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心洞察

DSH 的 Agent Notes 系统本质上是一个**将治理思维注入 Agent 记忆层**的设计：

1. **路径即元数据** → 不需要额外的索引系统，目录树本身就是最好的索引
2. **状态机而非类型标签** → 笔记有"生命"，会成长、被取代、被归档
3. **门禁验证** → 格式不是靠约定，而是靠 CI 门禁强制执行
4. **按需组装** → 笔记不是一次性灌入 prompt，而是每轮动态检索、按需加载
5. **执行中回写** → Agent 的笔记操作会触发 prompt 重新组装，形成"感知-记录-决策"闭环
6. **归档不可变** → 历史决策记录是可信的，不会被事后篡改

这些设计原则从"代码库治理"领域迁移到"Agent 运行时记忆"领域，可以将 NoteTool 从一个简单的 CRUD 工具提升为一个**结构化的 Agent 认知基础设施**。
