# AutoLoop MVP

单任务、本地运行的 AI 自主循环执行引擎。核心场景：Python 代码 Bug 自动修复（给定测试用例，AI 自主循环修改直到全部通过）。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                     LoopEngine (主入口)                  │
├─────────────┬─────────────┬─────────────┬───────────────┤
│  TaskState  │ ContextMgr  │  Executor   │   Verifier    │
│  (状态机)   │ (上下文管理) │  (执行器)   │   (校验器)    │
├─────────────┴─────────────┼─────────────┼───────────────┤
│        LLMClient          │  ToolSandbox│  Controller   │
│       (LLM 抽象层)        │  (工具沙箱) │  (循环控制器) │
└───────────────────────────┴─────────────┴───────────────┘
```

## 核心设计决策

1. **多 tool call / turn**：每轮让 LLM 在一个 turn 内连续调用多个工具（读文件→改文件→跑测试），而非单动作/轮
2. **原生 function calling**：使用 OpenAI 兼容的 tool calling 接口，不自行解析 JSON
3. **硬校验每轮，语义校验终检**：pytest 每轮必跑（零成本），LLM 语义校验仅在硬校验全过后触发
4. **三级上下文压缩**：L0 完整（最近 3 轮）+ L1 摘要（更早轮次）+ L2 全局状态（始终保留）
5. **反思机制**：连续无进展时触发反思轮，让 LLM 复盘后再行动

## 快速开始

### 安装

```bash
pip install -e .
```

### 配置 API Key

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 可选，用于自定义端点 / 本地模型
```

### 运行示例（修复有 Bug 的计算器项目）

仓库自带一个 5 个 bug 的示例项目（`examples/buggy_project/`），可直接跑：

```bash
python -m autoloop.run \
    --goal "修复 calculator.py 的所有 bug，让 tests/test_calculator.py 中的所有测试用例通过" \
    --work-dir ./examples/buggy_project \
    --test-cmd "pytest tests/test_calculator.py -v"
```

### 运行自己的项目

```bash
python -m autoloop.run \
    --goal "修复 main.py 中的解析错误" \
    --work-dir /path/to/your/project \
    --test-cmd "pytest tests/ -v" \
    --model gpt-4o-mini \
    --max-rounds 15
```

### 编程方式调用

```python
from autoloop import LoopEngine, LoopConfig, TaskDefinition

config = LoopConfig(
    max_rounds=10,
    execution_model="gpt-4o-mini",
    verification_model="gpt-4o",
    work_dir="./workspace",
)
engine = LoopEngine(config=config)
engine.setup_llm()

result = engine.run(TaskDefinition(
    task_id="my-task",
    goal="修复所有测试失败",
    work_dir="/path/to/project",
    test_command="pytest tests/ -v",
))
print(result.status, result.current_round, result.total_tokens)
```

## 配置

见 `config.py` 的 `LoopConfig` dataclass。关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 10 | 最大循环轮次 |
| `max_total_tokens` | 100000 | Token 预算 |
| `timeout_seconds` | 300 | 总超时（秒） |
| `execution_model` | `gpt-4o-mini` | 执行模型 |
| `verification_model` | `gpt-4o` | 校验模型（仅终检用） |
| `max_tool_calls_per_turn` | 8 | 单轮最大工具调用次数 |
