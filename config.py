"""配置定义"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoopConfig:
    """Loop 引擎全局配置"""

    # 循环约束
    max_rounds: int = 10
    max_total_tokens: int = 100_000
    timeout_seconds: int = 300

    # 模型配置
    execution_model: str = "gpt-4o-mini"
    verification_model: str = "gpt-4o"
    reflection_model: str = "gpt-4o"

    # LLM 调用配置
    max_tool_calls_per_turn: int = 8  # 单轮最大工具调用次数
    temperature: float = 0.0

    # 策略配置
    reflection_trigger_stagnant_rounds: int = 3  # 连续无进展轮次触发反思
    semantic_verify_on_completion: bool = True  # 硬校验全过后是否跑语义终检
    hard_check_only_rounds: int = 0  # 前 N 轮只跑硬校验（已默认关闭语义逐轮校验）

    # 环境配置
    work_dir: str = "./workspace"
    log_dir: str = "./logs"

    # 工具白名单
    allowed_commands: list = field(
        default_factory=lambda: [
            "python", "python3", "pytest", "ls", "cat", "head", "tail", "grep",
            "find", "wc", "diff", "pip",
        ]
    )

    # LLM 客户端配置（从环境变量读取，也可显式传入）
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None


@dataclass
class TaskDefinition:
    """任务定义"""

    task_id: str
    goal: str
    work_dir: str  # 任务专属工作目录（绝对路径或相对于 autoloop work_dir）
    test_command: str = "pytest tests/ -v"  # 硬校验命令
    success_criteria: Optional[str] = None  # 额外的成功标准描述
    source_files: list = field(default_factory=list)  # 相关源文件列表（给上下文用）
