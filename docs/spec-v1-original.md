# Loop MVP 深度设计与完整实现方案

---

## 第一部分：深度设计评估与优化补充

### 一、现有7模块设计的复盘评估

| 模块 | 现有设计评估 | 核心问题 | MVP优先级 |
|----|----|----|----|
| 任务调度与状态管理 | 方向正确，粒度偏粗 | 缺少**有限状态机（FSM）**的精确定义，状态流转规则不清晰 | P0 |
| 环境感知读取器 | 功能定义正确 | 缺少**上下文压缩策略**，长任务极易爆token，这是实际落地第一大坑 | P0 |
| 智能指令生成器 | 基础覆盖 | 缺少**Prompt模板分层体系**，执行/反思/校验混在一起难以调优 | P0 |
| 独立校验器 | 定位准确 | 缺少**校验层级设计**，硬校验与软校验的触发顺序、置信度融合未定义 | P0 |
| 循环决策控制器 | 基础覆盖 | 缺少**错误分类机制**，所有失败都同等重试是低效的；缺少**渐进式升级策略** | P0 |
| 工具沙箱与安全隔离 | 方向正确 | MVP阶段可**降级为目录隔离+命令白名单**，完整沙箱成本过高 | P1 |
| 监控复盘后台 | 功能完整 | MVP阶段**降级为结构化日志**即可，可视化后台非核心验证目标 | P2 |

**结论：现有设计覆盖了宏观骨架，但缺少5个决定系统能否真正跑通的关键细节设计。**

---

### 二、必须补充的 5 个关键设计点

#### 补充1：上下文窗口管理策略（第一优先级）
这是所有Loop系统的隐形瓶颈。一个10轮的循环，如果每轮都把全量历史塞进去，第10轮的上下文会膨胀到不可接受。

**三级上下文压缩策略：**
- **L0 完整上下文**：最近3轮的完整交互记录（指令+执行结果+校验反馈），保证短期记忆精度
- **L1 摘要上下文**：更早轮次的结构化摘要（做了什么、结果如何、为什么失败），用AI自动压缩生成
- **L2 全局状态**：任务目标、约束条件、累计进度、已验证通过的子任务清单，全程保留

**核心原则：永远只给执行Agent看它"刚好够用"的信息，而非全部历史。**

#### 补充2：校验层级与置信度体系
单一校验器容易出现两种极端：规则太严导致永远过不了，规则太松导致质量失控。

**三级校验漏斗：**
1. **硬规则校验（0成本，必过）**：单元测试、语法检查、字段完整性、格式校验——机器可100%客观判定，不消耗LLM Token
2. **LLM语义校验（中等成本）**：独立校验Agent做业务逻辑验收，输出 `pass/fail + 置信度 + 缺陷清单`
3. **渐进式严格度**：前N轮用宽松阈值（置信度≥0.7即通过），后N轮自动收紧阈值（置信度≥0.9），避免前期卡死在细节上

#### 补充3：错误分类与差异化重试策略
不是所有失败都值得重试，也不是所有失败都用同样方式重试。

| 错误类型 | 判定特征 | 处理策略 |
|----|----|----|
| 可修复错误 | 校验反馈明确指出问题在哪、怎么改 | 直接进入下一轮，带上缺陷清单 |
| 方向性错误 | 连续2轮犯同一类错误，说明理解偏了 | 触发**反思Prompt**，让Agent先复盘再行动 |
| 能力边界错误 | 工具/权限/知识不足导致的失败 | 直接熔断，标记为"需要人工介入"，不浪费算力 |
| 环境瞬态错误 | 网络超时、API限流、资源暂时不可用 | 指数退避重试，不消耗思考轮次 |

#### 补充4：Prompt模板分层体系
一套Loop系统至少需要4类完全不同的Prompt，各司其职，不能混写：

1. **系统角色Prompt**：定义Agent身份、能力边界、输出格式规范——全程不变
2. **执行任务Prompt**：每轮动态生成，包含目标+当前状态+历史摘要+本轮任务
3. **校验验收Prompt**：独立校验Agent使用，只做判定，不做修改
4. **反思复盘Prompt**：连续失败时触发，让Agent先总结教训再规划下一步

#### 补充5：渐进式能力升级机制
循环不是简单的"失败了再来一次"，而是每一轮都应该比上一轮更强：

- **模型升级**：前3轮用低成本快速模型（如GPT-4o-mini），失败后升级到高精度模型
- **工具升级**：前期只用基础工具，失败后开放更多工具权限
- **上下文升级**：前期只给摘要上下文，卡壳时解锁更多历史细节

---

### 三、MVP 范围界定与取舍原则

**MVP核心验证目标（必须全部验证）：**
1. ✅ AI能否在**零人工干预**下完成一个多步骤编码任务
2. ✅ 独立校验器能否**有效拦截AI自判通过的错误结果**
3. ✅ 循环机制能否**显著提升单次任务的成功率**（对比单次Prompt）
4. ✅ 系统能否**稳定运行不崩**，有基本的错误兜底

**MVP可以暂时砍掉的（不影响核心验证）：**
- ❌ 分布式架构、多任务并行 → MVP只跑单任务串行
- ❌ 完整容器沙箱 → 用工作目录隔离 + 命令白名单替代
- ❌ 可视化监控后台 → 用结构化日志 + 终端输出替代
- ❌ 权限体系、多租户 → 单用户本地运行
- ❌ 断点续跑 → MVP失败了就重来，状态持久化只用于日志复盘

---

## 第二部分：Loop MVP 完整技术规格（Spec v1.0）

### 1. 系统概述

**系统名称**：AutoLoop MVP
**版本**：v0.1
**定位**：单任务、本地运行、代码场景优先的AI自主循环执行引擎
**核心验证场景**：Python代码Bug自动修复（给定测试用例，AI自主循环修改直到全部通过）

### 2. 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                     LoopEngine (主入口)                  │
├─────────────┬─────────────┬─────────────┬───────────────┤
│  TaskState  │ ContextMgr  │  Executor   │   Verifier    │
│  (状态机)   │ (上下文管理) │  (执行器)   │   (校验器)    │
├─────────────┴─────────────┴─────────────┼───────────────┤
│              ToolSandbox                │  Controller   │
│            (工具沙箱层)                 │  (循环控制器) │
└─────────────────────────────────────────┴───────────────┘
```

### 3. 模块详细规格

#### 3.1 任务状态机 (TaskState)

**状态定义：**
- `PENDING`：待初始化
- `RUNNING`：循环执行中
- `VERIFYING`：校验中
- `REFLECTING`：反思复盘（连续失败触发）
- `SUCCEEDED`：任务成功
- `FAILED`：任务失败（正常熔断）
- `ERROR`：系统异常终止

**状态流转规则：**
```
PENDING → RUNNING → VERIFYING → SUCCEEDED (终止)
                    ↓         ↘ FAILED (终止)
                  RUNNING (重试)
                    ↓
                REFLECTING → RUNNING (反思后重试)
```

**状态数据结构：**
```python
{
    "task_id": "uuid",
    "goal": "原始任务目标",
    "constraints": {"max_rounds": 10, "max_tokens": 100000, "timeout": 300},
    "status": "RUNNING",
    "current_round": 3,
    "total_tokens_used": 4500,
    "start_time": "timestamp",
    "round_history": [...],  # 每轮的完整记录
    "verified_items": [...], # 已确认通过的子目标
    "last_error": None
}
```

#### 3.2 上下文管理器 (ContextManager)

**三级上下文策略实现：**

| 层级 | 内容 | 保留轮数 | 生成方式 |
|----|----|----|----|
| L0 完整交互 | 最近N轮的完整prompt+执行结果+校验反馈 | 3轮 | 原始保留 |
| L1 结构化摘要 | 更早轮次的：动作、结果、失败原因、关键教训 | 所有轮次，每轮压缩到200字以内 | LLM自动摘要 |
| L2 全局状态 | 任务目标、约束、已验证通过项、累计进度 | 全程 | 结构化维护 |

**核心接口：**
- `build_execution_context() -> str`：组装给执行Agent的上下文
- `build_verification_context() -> str`：组装给校验Agent的上下文
- `after_round_completed(round_data)`：轮次结束后更新上下文，触发摘要压缩

#### 3.3 执行器 (Executor)

**职责：** 根据当前上下文，调用LLM生成行动计划，并执行工具调用。

**执行流程：**
1. 从ContextManager获取组装好的上下文
2. 拼接系统Prompt + 执行任务Prompt，调用LLM
3. 解析LLM输出的工具调用指令
4. 通过ToolSandbox执行工具
5. 返回执行结果（结构化）

**输出格式约束（强制LLM输出JSON）：**
```json
{
    "thought": "我当前的分析和判断",
    "action": "工具名称",
    "action_input": {"参数名": "参数值"},
    "expected_result": "我预期这步会得到什么"
}
```

**支持的基础工具集（MVP）：**
- `read_file`：读取文件内容
- `write_file`：写入/覆盖文件
- `run_command`：执行Shell命令（白名单限制）
- `view_test_result`：查看测试报告
- `finish`：宣告任务完成

#### 3.4 校验器 (Verifier)

**三级校验实现：**

**Level 1 - 硬规则校验（必跑，0 Token成本）：**
- 执行 `pytest` 命令，获取通过率、失败用例数
- 代码语法检查（`python -m py_compile`）
- 文件存在性检查

**Level 2 - LLM语义校验：**
- 独立的校验Agent（可以用不同模型）
- 输入：原始目标 + 当前代码 + 测试结果
- 输出结构化结果：
```json
{
    "passed": false,
    "confidence": 0.65,
    "defects": [
        {"severity": "critical", "description": "边界条件未处理", "location": "file.py:42"},
        {"severity": "minor", "description": "变量命名不规范"}
    ],
    "overall_assessment": "核心功能未实现"
}
```

**Level 3 - 渐进式阈值：**
- 第1-3轮：硬校验通过 + 语义置信度≥0.6 → 视为通过
- 第4-7轮：硬校验通过 + 语义置信度≥0.8 → 视为通过
- 第8-10轮：硬校验通过 + 语义置信度≥0.9 → 视为通过
- 硬校验永远是前置条件，语义校验是附加门槛

#### 3.5 循环控制器 (Controller)

**核心决策逻辑：**

```
每轮结束后：
1. 检查硬校验结果
   ├─ 硬校验失败 → 进入下一轮（带失败详情）
   └─ 硬校验通过 → 进入语义校验

2. 语义校验后：
   ├─ 通过（置信度≥当前轮阈值）→ 任务成功，终止
   └─ 未通过 → 检查是否需要反思

3. 反思触发条件：
   └─ 连续2轮犯同类错误 / 连续3轮无实质进展 → 触发反思轮

4. 熔断条件（任一触发即终止）：
   ├─ 达到最大轮次 max_rounds
   ├─ 累计Token超过预算 max_tokens
   ├─ 总运行时间超过 timeout
   └─ 连续N轮出现能力边界类错误
```

**反思轮特殊处理：**
- 不执行实际动作，只让Agent输出复盘报告
- 复盘内容：之前哪里错了、根本原因是什么、接下来的修正策略
- 复盘结果作为下一轮执行的重要输入

#### 3.6 工具沙箱 (ToolSandbox)

**MVP简化版实现：**
1. **工作目录隔离**：每个任务有独立的工作目录，只能读写该目录下的文件
2. **命令白名单**：只允许执行 `python`、`pytest`、`ls`、`cat` 等安全命令
3. **路径校验**：禁止 `../` 越权访问，禁止绝对路径跳出工作目录
4. **超时控制**：每个命令执行有独立超时（默认30秒）
5. **操作日志**：所有工具调用全量记录

#### 3.7 成本监控 (CostTracker)

**统计维度：**
- 每轮Token消耗（输入+输出）
- 累计Token消耗
- 预估费用（按模型单价计算）
- 每轮耗时、总耗时

**作用：** 触发成本熔断、提供复盘数据

### 4. Prompt 模板体系

#### 4.1 系统角色Prompt（执行Agent）
```
你是一个自主代码修复工程师。你的任务是通过不断尝试，让所有测试用例通过。

工作规则：
1. 每一步只能执行一个动作，不要贪多
2. 修改代码前先读取文件，了解当前状态
3. 每次修改后必须运行测试验证效果
4. 如果连续两次修改都没有改善，停下来反思方向是否正确
5. 严格按照指定的JSON格式输出

可用工具：read_file, write_file, run_command, finish
```

#### 4.2 校验Agent系统Prompt
```
你是独立的代码质量验收员。你的职责是客观判断代码是否满足任务要求。

重要原则：
1. 你只做评判，不提供修改建议（除非明确要求）
2. 必须基于事实判断，不能猜测
3. 严格区分"功能正确性"和"代码风格"
4. 输出必须是指定的JSON格式，不能有其他废话

评判维度：
- 功能正确性（权重70%）：是否实现了需求，测试是否通过
- 边界处理（权重20%）：异常情况、边界条件是否考虑
- 代码质量（权重10%）：可读性、规范性
```

#### 4.3 反思Prompt
```
你已经连续尝试了N次，但效果不理想。请先停下来做一次深度复盘。

请从以下维度分析：
1. 你之前的修改思路是什么？
2. 为什么这些修改没有解决问题？根本原因在哪？
3. 你是不是忽略了什么重要信息？
4. 接下来你打算换什么思路？给出具体的下一步计划

输出格式：结构化的复盘报告
```

### 5. 接口定义

**主入口：**
```python
class LoopEngine:
    def __init__(self, config: LoopConfig): ...
    def run(self, task: TaskDefinition) -> TaskResult: ...
```

**配置对象：**
```python
@dataclass
class LoopConfig:
    max_rounds: int = 10
    max_tokens: int = 100000
    timeout_seconds: int = 300
    execution_model: str = "gpt-4o-mini"
    verification_model: str = "gpt-4o"
    reflection_trigger_rounds: int = 3  # 连续几轮无进展触发反思
    work_dir: str = "./workspace"
```

### 6. 输出产物

每次运行产出：
1. **终端实时输出**：每轮的状态、动作、结果
2. **结构化日志文件**：`./logs/{task_id}.json`，包含完整的每轮数据
3. **最终报告**：成功/失败状态、总轮次、总Token、总耗时、失败原因分析

---

## 第三部分：代码框架实现

### 项目结构

```
autoloop/
├── __init__.py
├── engine.py          # 主引擎入口
├── config.py          # 配置定义
├── state.py           # 状态管理
├── context.py         # 上下文管理器
├── executor.py        # 执行器
├── verifier.py        # 校验器
├── controller.py      # 循环控制器
├── tools/
│   ├── __init__.py
│   ├── base.py        # 工具基类
│   ├── file_tools.py  # 文件操作工具
│   └── shell_tools.py # 命令执行工具
├── prompts/
│   ├── __init__.py
│   ├── executor.py    # 执行Agent提示词
│   ├── verifier.py    # 校验Agent提示词
│   └── reflection.py  # 反思提示词
└── utils/
    ├── __init__.py
    ├── cost_tracker.py # 成本统计
    └── logger.py       # 日志工具
```

---

### 核心代码框架

#### 1. `config.py` - 配置定义

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LoopConfig:
    """Loop引擎全局配置"""
    # 循环约束
    max_rounds: int = 10
    max_total_tokens: int = 100000
    timeout_seconds: int = 300
    
    # 模型配置
    execution_model: str = "gpt-4o-mini"
    verification_model: str = "gpt-4o"
    reflection_model: str = "gpt-4o"
    
    # 策略配置
    reflection_trigger_stagnant_rounds: int = 3  # 连续无进展轮次触发反思
    hard_check_only_rounds: int = 0  # 前N轮只跑硬校验，省Token
    
    # 环境配置
    work_dir: str = "./workspace"
    log_dir: str = "./logs"
    
    # 工具白名单
    allowed_commands: list = field(default_factory=lambda: [
        "python", "pytest", "ls", "cat", "head", "tail", "grep"
    ])

@dataclass
class TaskDefinition:
    """任务定义"""
    task_id: str
    goal: str
    work_dir: str  # 任务专属工作目录
    test_command: str = "pytest tests/ -v"  # 硬校验命令
    success_criteria: Optional[str] = None  # 额外的成功标准描述
```

#### 2. `state.py` - 状态管理

```python
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ERROR = "error"

@dataclass
class RoundRecord:
    """单轮执行记录"""
    round_num: int
    round_type: str = "execute"  # execute / reflect / verify
    start_time: float = 0.0
    end_time: float = 0.0
    
    # 执行相关
    input_tokens: int = 0
    output_tokens: int = 0
    llm_thought: str = ""
    action_taken: str = ""
    action_input: Dict = field(default_factory=dict)
    execution_result: str = ""
    
    # 校验相关
    hard_check_passed: Optional[bool] = None
    hard_check_details: Dict = field(default_factory=dict)
    semantic_check_passed: Optional[bool] = None
    semantic_confidence: float = 0.0
    semantic_defects: List = field(default_factory=list)
    
    # 决策
    next_action: str = ""  # continue / succeed / fail / reflect

@dataclass
class TaskState:
    """任务全局状态"""
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    current_round: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    round_history: List[RoundRecord] = field(default_factory=list)
    verified_items: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    final_summary: str = ""
    
    # 连续无进展计数器（用于触发反思）
    consecutive_stagnant_rounds: int = 0
    
    def start(self):
        self.status = TaskStatus.RUNNING
        self.start_time = time.time()
    
    def new_round(self, round_type: str = "execute") -> RoundRecord:
        self.current_round += 1
        round_record = RoundRecord(
            round_num=self.current_round,
            round_type=round_type,
            start_time=time.time()
        )
        self.round_history.append(round_record)
        return round_record
    
    def complete_round(self, round_record: RoundRecord):
        round_record.end_time = time.time()
        self.total_input_tokens += round_record.input_tokens
        self.total_output_tokens += round_record.output_tokens
    
    def mark_success(self, summary: str = ""):
        self.status = TaskStatus.SUCCEEDED
        self.end_time = time.time()
        self.final_summary = summary
    
    def mark_failed(self, reason: str):
        self.status = TaskStatus.FAILED
        self.end_time = time.time()
        self.last_error = reason
        self.final_summary = f"任务失败: {reason}"
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "current_round": self.current_round,
            "duration_seconds": round(self.end_time - self.start_time, 2) if self.end_time else 0,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "round_history": [asdict(r) for r in self.round_history],
            "final_summary": self.final_summary,
            "last_error": self.last_error
        }
    
    def save_to_file(self, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
```

#### 3. `context.py` - 上下文管理器

```python
from typing import List
from .state import TaskState, RoundRecord

class ContextManager:
    """三级上下文管理器"""
    
    def __init__(self, max_full_rounds: int = 3):
        self.max_full_rounds = max_full_rounds  # L0层保留的完整轮次数
    
    def build_execution_context(self, state: TaskState) -> str:
        """构建执行Agent的上下文"""
        parts = []
        
        # L2: 全局目标
        parts.append(f"## 任务目标\n{state.goal}\n")
        
        # L2: 已验证通过项
        if state.verified_items:
            parts.append(f"## 已确认完成的事项\n")
            for item in state.verified_items:
                parts.append(f"- [x] {item}")
            parts.append("")
        
        # L2: 当前进度
        parts.append(f"## 当前进度\n这是第 {state.current_round} 轮尝试。\n")
        
        # L1 + L0: 历史记录
        history = self._build_history_context(state.round_history)
        parts.append(f"## 历史执行记录\n{history}\n")
        
        # 行动指引
        parts.append("## 下一步\n请基于以上信息，决定下一步要做什么。严格按照JSON格式输出。")
        
        return "\n".join(parts)
    
    def build_verification_context(self, state: TaskState, hard_check_result: dict) -> str:
        """构建校验Agent的上下文"""
        parts = []
        
        parts.append(f"## 任务目标\n{state.goal}\n")
        parts.append(f"## 硬校验结果\n")
        parts.append(f"- 测试通过: {hard_check_result.get('passed', '未知')}")
        parts.append(f"- 失败用例数: {hard_check_result.get('failed_tests', 0)}")
        if hard_check_result.get('output'):
            parts.append(f"\n测试输出摘要:\n{hard_check_result['output'][:2000]}\n")
        
        # 最近一轮的代码修改摘要
        if state.round_history:
            last_round = state.round_history[-1]
            parts.append(f"## 本轮修改\n")
            parts.append(f"动作: {last_round.action_taken}")
            if last_round.execution_result:
                parts.append(f"结果: {last_round.execution_result[:1000]}")
        
        return "\n".join(parts)
    
    def build_reflection_context(self, state: TaskState) -> str:
        """构建反思Agent的上下文"""
        parts = []
        
        parts.append(f"## 任务目标\n{state.goal}\n")
        parts.append(f"## 问题\n你已经连续尝试了 {state.consecutive_stagnant_rounds} 轮，但没有实质进展。\n")
        parts.append(f"## 最近 {min(5, len(state.round_history))} 轮的尝试\n")
        
        # 最近5轮的摘要
        for r in state.round_history[-5:]:
            parts.append(f"第{r.round_num}轮:")
            parts.append(f"  动作: {r.action_taken}")
            parts.append(f"  结果: {r.execution_result[:200]}")
            if r.hard_check_passed is not None:
                parts.append(f"  校验: {'通过' if r.hard_check_passed else '失败'}")
            parts.append("")
        
        parts.append("请深度复盘：为什么一直没有进展？根本原因是什么？接下来应该换什么思路？")
        
        return "\n".join(parts)
    
    def _build_history_context(self, history: List[RoundRecord]) -> str:
        """组装历史记录：最近N轮完整，更早的给摘要"""
        if not history:
            return "（暂无历史记录，这是第一轮）"
        
        parts = []
        
        # 更早的轮次：摘要形式
        if len(history) > self.max_full_rounds:
            early_rounds = history[:-self.max_full_rounds]
            parts.append("### 早期尝试摘要\n")
            for r in early_rounds:
                status = "校验中"
                if r.hard_check_passed is True:
                    status = "硬校验通过"
                elif r.hard_check_passed is False:
                    status = "硬校验失败"
                parts.append(f"- 第{r.round_num}轮: {r.action_taken} → {status}")
            parts.append("")
        
        # 最近N轮：完整记录
        recent_rounds = history[-self.max_full_rounds:]
        parts.append("### 最近几轮详细记录\n")
        for r in recent_rounds:
            parts.append(f"--- 第 {r.round_num} 轮 ---")
            parts.append(f"思考: {r.llm_thought}")
            parts.append(f"动作: {r.action_taken}")
            parts.append(f"参数: {r.action_input}")
            parts.append(f"结果: {r.execution_result[:500]}")
            if r.hard_check_passed is not None:
                parts.append(f"硬校验: {'通过' if r.hard_check_passed else '失败'}")
            parts.append("")
        
        return "\n".join(parts)
```

#### 4. `executor.py` - 执行器

```python
import json
from typing import Dict, Any
from .state import TaskState, RoundRecord
from .context import ContextManager
from .tools import ToolRegistry

class Executor:
    """执行Agent：负责生成行动计划并执行"""
    
    def __init__(self, llm_client, tool_registry: ToolRegistry, 
                 context_manager: ContextManager, system_prompt: str):
        self.llm = llm_client
        self.tools = tool_registry
        self.context = context_manager
        self.system_prompt = system_prompt
    
    def execute_round(self, state: TaskState, round_record: RoundRecord) -> RoundRecord:
        """执行一轮：生成指令 + 执行工具"""
        # 1. 构建上下文
        user_prompt = self.context.build_execution_context(state)
        
        # 2. 调用LLM
        response, input_tokens, output_tokens = self._call_llm(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt
        )
        
        round_record.input_tokens = input_tokens
        round_record.output_tokens = output_tokens
        
        # 3. 解析LLM输出
        try:
            parsed = self._parse_response(response)
            round_record.llm_thought = parsed.get("thought", "")
            round_record.action_taken = parsed.get("action", "")
            round_record.action_input = parsed.get("action_input", {})
        except Exception as e:
            round_record.execution_result = f"LLM输出解析失败: {str(e)}\n原始输出: {response[:500]}"
            return round_record
        
        # 4. 检查是否是finish动作
        if round_record.action_taken == "finish":
            round_record.execution_result = "Agent宣告任务完成"
            return round_record
        
        # 5. 执行工具
        try:
            result = self.tools.execute(
                tool_name=round_record.action_taken,
                params=round_record.action_input,
                work_dir=state.task_id  # 用task_id隔离工作目录
            )
            round_record.execution_result = str(result)
        except Exception as e:
            round_record.execution_result = f"工具执行失败: {str(e)}"
        
        return round_record
    
    def _call_llm(self, system_prompt: str, user_prompt: str):
        """调用大模型（此处为占位，需接入实际LLM SDK）"""
        # TODO: 接入实际的LLM API
        # 返回 (response_text, input_tokens, output_tokens)
        raise NotImplementedError("需要接入实际的LLM客户端")
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM的JSON输出"""
        # 尝试从响应中提取JSON
        response = response.strip()
        
        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试从markdown代码块中提取
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                return json.loads(response[start:end].strip())
        
        # 尝试找第一个{到最后一个}
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            return json.loads(response[start:end+1])
        
        raise ValueError("无法从LLM输出中解析JSON")
```

#### 5. `verifier.py` - 校验器

```python
import json
import re
from typing import Dict, Tuple
from .state import TaskState, RoundRecord
from .context import ContextManager
from .tools import ToolRegistry

class Verifier:
    """独立校验器：硬校验 + 语义校验"""
    
    def __init__(self, llm_client, tool_registry: ToolRegistry,
                 context_manager: ContextManager, 
                 verifier_system_prompt: str,
                 test_command: str = "pytest tests/ -v"):
        self.llm = llm_client
        self.tools = tool_registry
        self.context = context_manager
        self.system_prompt = verifier_system_prompt
        self.test_command = test_command
    
    def verify(self, state: TaskState, round_record: RoundRecord, 
               current_round: int, max_rounds: int,
               hard_only: bool = False) -> Tuple[bool, Dict]:
        """
        执行校验
        返回: (是否通过, 校验详情字典)
        """
        details = {}
        
        # Level 1: 硬校验
        hard_result = self._hard_check(state)
        details["hard_check"] = hard_result
        round_record.hard_check_passed = hard_result["passed"]
        round_record.hard_check_details = hard_result
        
        if not hard_result["passed"]:
            return False, details
        
        # 如果只跑硬校验（前N轮省Token策略），直接返回
        if hard_only:
            return True, details
        
        # Level 2: 语义校验
        semantic_result = self._semantic_check(state, hard_result)
        details["semantic_check"] = semantic_result
        round_record.semantic_check_passed = semantic_result["passed"]
        round_record.semantic_confidence = semantic_result.get("confidence", 0.0)
        round_record.semantic_defects = semantic_result.get("defects", [])
        
        # 计算当前轮的通过阈值（渐进式）
        threshold = self._calculate_threshold(current_round, max_rounds)
        details["threshold"] = threshold
        
        passed = semantic_result.get("confidence", 0) >= threshold
        return passed, details
    
    def _hard_check(self, state: TaskState) -> Dict:
        """硬校验：运行测试"""
        try:
            result = self.tools.execute(
                tool_name="run_command",
                params={"command": self.test_command},
                work_dir=state.task_id
            )
            
            # 解析pytest输出
            output = str(result)
            passed = "passed" in output and "failed" not in output
            
            # 提取失败用例数
            failed_match = re.search(r"(\d+) failed", output)
            failed_count = int(failed_match.group(1)) if failed_match else 0
            
            passed_match = re.search(r"(\d+) passed", output)
            passed_count = int(passed_match.group(1)) if passed_match else 0
            
            return {
                "passed": passed and failed_count == 0,
                "passed_tests": passed_count,
                "failed_tests": failed_count,
                "output": output[:3000],
                "error": None
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "output": ""
            }
    
    def _semantic_check(self, state: TaskState, hard_result: Dict) -> Dict:
        """语义校验：调用独立校验Agent"""
        user_prompt = self.context.build_verification_context(state, hard_result)
        
        response, _, _ = self._call_llm(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt
        )
        
        try:
            result = json.loads(response)
            return {
                "passed": result.get("passed", False),
                "confidence": float(result.get("confidence", 0.0)),
                "defects": result.get("defects", []),
                "overall_assessment": result.get("overall_assessment", "")
            }
        except:
            return {
                "passed": False,
                "confidence": 0.0,
                "defects": [],
                "overall_assessment": f"校验输出解析失败，原始输出: {response[:300]}"
            }
    
    def _calculate_threshold(self, current_round: int, max_rounds: int) -> float:
        """渐进式阈值：前期宽松，后期严格"""
        # 前30%轮次：0.6
        # 中间40%：0.8
        # 后30%：0.9
        progress = current_round / max_rounds
        if progress < 0.3:
            return 0.6
        elif progress < 0.7:
            return 0.8
        else:
            return 0.9
    
    def _call_llm(self, system_prompt: str, user_prompt: str):
        """调用大模型（占位）"""
        raise NotImplementedError("需要接入实际的LLM客户端")
```

#### 6. `controller.py` - 循环控制器

```python
from typing import Tuple
from .state import TaskState, RoundRecord, TaskStatus
from .config import LoopConfig

class LoopController:
    """循环决策控制器"""
    
    def __init__(self, config: LoopConfig):
        self.config = config
    
    def should_continue(self, state: TaskState, verify_passed: bool, 
                        verify_details: dict) -> Tuple[str, str]:
        """
        判断下一步动作
        返回: (动作类型, 原因说明)
        动作类型: succeed / continue / reflect / fail
        """
        # 1. 校验通过 → 成功
        if verify_passed:
            return "succeed", "所有校验通过，任务完成"
        
        # 2. 检查熔断条件
        fail_reason = self._check_circuit_breaker(state)
        if fail_reason:
            return "fail", fail_reason
        
        # 3. 检查是否需要反思
        if self._should_reflect(state):
            return "reflect", "连续多轮无进展，触发反思"
        
        # 4. 继续下一轮
        return "continue", "校验未通过，继续尝试"
    
    def _check_circuit_breaker(self, state: TaskState) -> str:
        """检查熔断条件，返回失败原因，未触发返回空字符串"""
        # 最大轮次
        if state.current_round >= self.config.max_rounds:
            return f"已达到最大轮次限制 ({self.config.max_rounds}轮)"
        
        # Token预算
        total_tokens = state.total_input_tokens + state.total_output_tokens
        if total_tokens >= self.config.max_total_tokens:
            return f"已达到Token预算限制 ({self.config.max_total_tokens})"
        
        # 超时
        import time
        elapsed = time.time() - state.start_time
        if elapsed >= self.config.timeout_seconds:
            return f"已超时 ({self.config.timeout_seconds}秒)"
        
        return ""
    
    def _should_reflect(self, state: TaskState) -> bool:
        """判断是否应该触发反思轮"""
        if state.consecutive_stagnant_rounds >= self.config.reflection_trigger_stagnant_rounds:
            # 确保不会连续触发反思（上一轮不能已经是反思）
            if state.round_history and state.round_history[-1].round_type != "reflect":
                return True
        return False
    
    def update_stagnation_counter(self, state: TaskState, made_progress: bool):
        """更新无进展计数器"""
        if made_progress:
            state.consecutive_stagnant_rounds = 0
        else:
            state.consecutive_stagnant_rounds += 1
    
    def detect_progress(self, state: TaskState, current_hard_result: dict) -> bool:
        """判断本轮是否有实质进展"""
        # 简单策略：对比最近两轮的失败用例数
        if len(state.round_history) < 2:
            return True  # 前两轮默认算有进展
        
        prev_round = state.round_history[-2]  # 上一轮（因为当前轮还在进行中，-1是当前轮）
        prev_failed = prev_round.hard_check_details.get("failed_tests", 999)
        curr_failed = current_hard_result.get("failed_tests", 999)
        
        # 失败用例减少了 → 有进展
        return curr_failed < prev_failed
```

#### 7. `engine.py` - 主引擎

```python
import os
import time
from typing import Optional
from .config import LoopConfig, TaskDefinition
from .state import TaskState, TaskStatus
from .context import ContextManager
from .executor import Executor
from .verifier import Verifier
from .controller import LoopController
from .tools import ToolRegistry
from .prompts import EXECUTOR_SYSTEM_PROMPT, VERIFIER_SYSTEM_PROMPT

class LoopEngine:
    """Loop MVP 主引擎"""
    
    def __init__(self, config: Optional[LoopConfig] = None):
        self.config = config or LoopConfig()
        self._setup_directories()
        
        # 初始化各模块
        self.context_manager = ContextManager(max_full_rounds=3)
        self.tool_registry = ToolRegistry(
            work_dir_base=self.config.work_dir,
            allowed_commands=self.config.allowed_commands
        )
        self.controller = LoopController(self.config)
        
        # 注意：Executor和Verifier需要LLM客户端，
        # 实际使用时需要在子类或工厂方法中注入
        self.executor = None
        self.verifier = None
    
    def _setup_directories(self):
        """创建必要的目录"""
        os.makedirs(self.config.work_dir, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)
    
    def setup_llm(self, llm_client):
        """注入LLM客户端，初始化执行器和校验器"""
        self.executor = Executor(
            llm_client=llm_client,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            system_prompt=EXECUTOR_SYSTEM_PROMPT
        )
        self.verifier = Verifier(
            llm_client=llm_client,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            verifier_system_prompt=VERIFIER_SYSTEM_PROMPT,
            test_command="pytest tests/ -v"
        )
    
    def run(self, task: TaskDefinition) -> TaskState:
        """运行任务主循环"""
        if not self.executor or not self.verifier:
            raise RuntimeError("请先调用 setup_llm() 注入LLM客户端")
        
        # 1. 初始化状态
        state = TaskState(
            task_id=task.task_id,
            goal=task.goal
        )
        state.start()
        
        self._print_header(task)
        
        try:
            while True:
                # 2. 判断本轮类型（执行 / 反思）
                round_type = self._decide_round_type(state)
                
                # 3. 创建新一轮记录
                round_record = state.new_round(round_type=round_type)
                
                self._print_round_start(round_record)
                
                if round_type == "reflect":
                    # 反思轮
                    self._run_reflection_round(state, round_record)
                else:
                    # 执行轮
                    self._run_execution_round(state, round_record, task)
                
                # 4. 完成本轮记录
                state.complete_round(round_record)
                
                # 5. 决策下一步
                action, reason = self.controller.should_continue(
                    state, 
                    verify_passed=round_record.hard_check_passed or False,
                    verify_details=round_record.hard_check_details
                )
                
                self._print_round_result(round_record, action, reason)
                
                # 6. 执行决策
                if action == "succeed":
                    state.mark_success(f"经过{state.current_round}轮循环，任务成功完成")
                    break
                elif action == "fail":
                    state.mark_failed(reason)
                    break
                # continue / reflect → 继续循环
                
                # 保存中间状态
                self._save_state(state)
                
        except Exception as e:
            state.status = TaskStatus.ERROR
            state.last_error = str(e)
            state.end_time = time.time()
        
        # 7. 保存最终状态
        self._save_state(state)
        self._print_summary(state)
        
        return state
    
    def _decide_round_type(self, state: TaskState) -> str:
        """决定本轮是执行还是反思"""
        if state.current_round == 0:
            return "execute"
        
        # 检查是否需要反思
        if self.controller._should_reflect(state):
            return "reflect"
        
        return "execute"
    
    def _run_execution_round(self, state: TaskState, round_record, task: TaskDefinition):
        """运行一轮执行"""
        # 执行
        self.executor.execute_round(state, round_record)
        
        # 如果Agent说finish了，直接跑校验
        if round_record.action_taken == "finish":
            # 执行硬校验
            hard_result = self.verifier._hard_check(state)
            round_record.hard_check_passed = hard_result["passed"]
            round_record.hard_check_details = hard_result
        else:
            # 每轮结束后跑硬校验
            hard_result = self.verifier._hard_check(state)
            round_record.hard_check_passed = hard_result["passed"]
            round_record.hard_check_details = hard_result
        
        # 更新无进展计数器
        made_progress = self.controller.detect_progress(state, hard_result)
        self.controller.update_stagnation_counter(state, made_progress)
    
    def _run_reflection_round(self, state: TaskState, round_record):
        """运行一轮反思"""
        # 构建反思上下文
        reflection_prompt = self.context_manager.build_reflection_context(state)
        
        # 调用LLM反思（此处简化，实际应走Executor的反思模式）
        round_record.llm_thought = "反思中..."
        round_record.action_taken = "reflect"
        round_record.execution_result = "反思完成，将调整策略继续尝试"
        
        # 反思轮重置无进展计数器
        state.consecutive_stagnant_rounds = 0
    
    def _save_state(self, state: TaskState):
        """保存状态到日志文件"""
        log_path = os.path.join(self.config.log_dir, f"{state.task_id}.json")
        state.save_to_file(log_path)
    
    def _print_header(self, task: TaskDefinition):
        print("=" * 60)
        print(f"🚀 AutoLoop MVP 启动")
        print(f"任务ID: {task.task_id}")
        print(f"任务目标: {task.goal[:80]}...")
        print(f"最大轮次: {self.config.max_rounds}")
        print("=" * 60)
    
    def _print_round_start(self, round_record):
        print(f"\n── 第 {round_record.round_num} 轮 ({round_record.round_type}) ──")
    
    def _print_round_result(self, round_record, action: str, reason: str):
        status_icon = {"succeed": "✅", "continue": "🔄", "reflect": "🤔", "fail": "❌"}
        icon = status_icon.get(action, "❓")
        print(f"   {icon} {reason}")
        if round_record.hard_check_passed is not None:
            details = round_record.hard_check_details
            print(f"   测试结果: {details.get('passed_tests', 0)} passed, "
                  f"{details.get('failed_tests', 0)} failed")
    
    def _print_summary(self, state: TaskState):
        print("\n" + "=" * 60)
        print(f"📊 任务结束")
        print(f"状态: {state.status.value}")
        print(f"总轮次: {state.current_round}")
        print(f"总耗时: {round(state.end_time - state.start_time, 2)}秒")
        print(f"总Token: {state.total_input_tokens + state.total_output_tokens}")
        print(f"总结: {state.final_summary}")
        print(f"日志文件: {self.config.log_dir}/{state.task_id}.json")
        print("=" * 60)
```

#### 8. `tools/base.py` - 工具基类

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseTool(ABC):
    """工具基类"""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def execute(self, params: Dict[str, Any], work_dir: str) -> Any:
        """执行工具"""
        pass

class ToolRegistry:
    """工具注册表"""
    
    def __init__(self, work_dir_base: str = "./workspace", allowed_commands: list = None):
        self._tools = {}
        self.work_dir_base = work_dir_base
        self.allowed_commands = allowed_commands or []
    
    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
    
    def execute(self, tool_name: str, params: dict, work_dir: str) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"未知工具: {tool_name}")
        
        # 构建完整工作目录路径
        full_work_dir = f"{self.work_dir_base}/{work_dir}"
        
        return self._tools[tool_name].execute(params, full_work_dir)
    
    def get_available_tools(self) -> list:
        return list(self._tools.keys())
```

#### 9. `tools/file_tools.py` - 文件工具

```python
import os
from .base import BaseTool

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取文件内容"
    
    def execute(self, params: dict, work_dir: str) -> str:
        filename = params.get("filename", "")
        if not filename:
            return "错误: 缺少filename参数"
        
        # 安全检查：禁止越权访问
        if ".." in filename or filename.startswith("/"):
            return "错误: 不允许访问工作目录外的文件"
        
        filepath = os.path.join(work_dir, filename)
        
        if not os.path.exists(filepath):
            return f"错误: 文件不存在: {filename}"
        
        if not os.path.isfile(filepath):
            return f"错误: 不是文件: {filename}"
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            return f"读取文件失败: {str(e)}"

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "写入文件内容（覆盖）"
    
    def execute(self, params: dict, work_dir: str) -> str:
        filename = params.get("filename", "")
        content = params.get("content", "")
        
        if not filename:
            return "错误: 缺少filename参数"
        
        if ".." in filename or filename.startswith("/"):
            return "错误: 不允许访问工作目录外的文件"
        
        filepath = os.path.join(work_dir, filename)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"成功写入文件: {filename} ({len(content)} 字符)"
        except Exception as e:
            return f"写入文件失败: {str(e)}"
```

#### 10. `tools/shell_tools.py` - Shell工具

```python
import subprocess
import os
from .base import BaseTool

class RunCommandTool(BaseTool):
    name = "run_command"
    description = "执行Shell命令（白名单限制）"
    
    def __init__(self, allowed_commands: list = None, timeout: int = 30):
        self.allowed_commands = allowed_commands or []
        self.timeout = timeout
    
    def execute(self, params: dict, work_dir: str) -> str:
        command = params.get("command", "")
        if not command:
            return "错误: 缺少command参数"
        
        # 提取命令名（第一个词）做白名单检查
        cmd_name = command.strip().split()[0] if command.strip() else ""
        
        # 安全检查
        if not self._is_command_allowed(cmd_name):
            return f"错误: 命令 '{cmd_name}' 不在白名单中，不允许执行"
        
        # 危险操作拦截
        dangerous_patterns = ["rm -rf", "mkfs", "dd if=", "> /dev/sd", "sudo rm"]
        for pattern in dangerous_patterns:
            if pattern in command:
                return f"错误: 检测到危险操作模式 '{pattern}'，已阻止"
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            output = f"命令执行完成 (退出码: {result.returncode})\n"
            if result.stdout:
                output += f"--- stdout ---\n{result.stdout}"
            if result.stderr:
                output += f"--- stderr ---\n{result.stderr}"
            
            return output
        except subprocess.TimeoutExpired:
            return f"错误: 命令执行超时 ({self.timeout}秒)"
        except Exception as e:
            return f"命令执行失败: {str(e)}"
    
    def _is_command_allowed(self, cmd_name: str) -> bool:
        """检查命令是否在白名单中"""
        if not self.allowed_commands:
            return True  # 没有配置白名单则全部允许
        return cmd_name in self.allowed_commands
```

---

### 使用示例

```python
# example_usage.py

from autoloop import LoopEngine, LoopConfig, TaskDefinition
from autoloop.tools import ToolRegistry, ReadFileTool, WriteFileTool, RunCommandTool

# 1. 配置
config = LoopConfig(
    max_rounds=10,
    max_total_tokens=50000,
    timeout_seconds=300,
    work_dir="./workspace",
    log_dir="./logs"
)

# 2. 创建引擎
engine = LoopEngine(config=config)

# 3. 注册工具
engine.tool_registry.register(ReadFileTool())
engine.tool_registry.register(WriteFileTool())
engine.tool_registry.register(RunCommandTool(
    allowed_commands=config.allowed_commands
))

# 4. 注入LLM客户端（需要自己实现LLM调用的适配层）
# engine.setup_llm(your_llm_client)

# 5. 定义任务
task = TaskDefinition(
    task_id="bugfix-demo-001",
    goal="修复 calculator.py 中的所有bug，让 tests/test_calculator.py 中的所有测试用例通过",
    work_dir="bugfix-demo-001",
    test_command="pytest tests/test_calculator.py -v"
)

# 6. 运行
# result = engine.run(task)
# print(f"最终状态: {result.status}")
```

---

## 总结

### 这套MVP设计的核心亮点

1. **三级上下文管理**：解决了长循环的Token爆炸问题，这是90%的Loop原型都会踩的第一个坑
2. **校验分层+渐进式阈值**：前期不卡细节快速迭代，后期收紧保证质量，平衡效率与质量
3. **错误分类与反思机制**：不是无脑重试，而是有策略地调整方向，大幅提升收敛速度
4. **状态机驱动**：清晰的状态流转，每一步都可追溯、可复盘
5. **工具沙箱（简化版）**：目录隔离+命令白名单，用最小成本保障基础安全

### 后续可扩展方向

1. 接入实际LLM SDK（OpenAI / Anthropic / 本地模型）
2. 增加更多工具（API调用、数据库操作、浏览器自动化）
3. 实现真正的容器级沙箱隔离
4. 增加多任务并行调度
5. 增加可视化Web监控后台
6. 增加Prompt版本管理与A/B测试框架

需要我帮你接入具体的LLM SDK（比如OpenAI API），把这个框架变成可直接运行的完整代码吗？