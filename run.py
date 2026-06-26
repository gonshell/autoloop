"""AutoLoop CLI 入口

用法:
    python -m autoloop.run --goal "修复 calculator.py 的 bug" --work-dir ./my_project
    python -m autoloop.run --goal "..." --test-cmd "pytest tests/ -v" --max-rounds 15
"""

import argparse
import os
import sys
import uuid

from .config import LoopConfig, TaskDefinition
from .engine import LoopEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="AutoLoop MVP — AI 自主循环执行引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 修复一个 Python 项目的 bug
  python -m autoloop.run \\
      --goal "修复 calculator.py 中 add() 函数不处理负数的 bug" \\
      --work-dir ./my_project \\
      --test-cmd "pytest tests/test_calculator.py -v"

  # 使用自定义模型
  python -m autoloop.run \\
      --goal "..." \\
      --model gpt-4o \\
      --max-rounds 15
        """,
    )

    parser.add_argument("--goal", required=True, help="任务目标描述")
    parser.add_argument("--work-dir", default="./workspace", help="任务工作目录 (默认: ./workspace)")
    parser.add_argument("--test-cmd", default="pytest tests/ -v", help="测试命令 (默认: pytest tests/ -v)")
    parser.add_argument("--task-id", default=None, help="任务 ID (默认: 自动生成)")

    # 模型配置
    parser.add_argument("--model", default="gpt-4o-mini", help="执行模型 (默认: gpt-4o-mini)")
    parser.add_argument("--verify-model", default="gpt-4o", help="校验模型 (默认: gpt-4o)")

    # 循环配置
    parser.add_argument("--max-rounds", type=int, default=10, help="最大轮次 (默认: 10)")
    parser.add_argument("--max-tokens", type=int, default=100_000, help="Token 预算 (默认: 100000)")
    parser.add_argument("--timeout", type=int, default=300, help="超时秒数 (默认: 300)")
    parser.add_argument("--max-tools-per-turn", type=int, default=8, help="每轮最大工具调用 (默认: 8)")

    # 输出
    parser.add_argument("--log-dir", default="./logs", help="日志目录 (默认: ./logs)")

    return parser.parse_args()


def main():
    args = parse_args()

    # 配置
    config = LoopConfig(
        max_rounds=args.max_rounds,
        max_total_tokens=args.max_tokens,
        timeout_seconds=args.timeout,
        execution_model=args.model,
        verification_model=args.verify_model,
        max_tool_calls_per_turn=args.max_tools_per_turn,
        work_dir=args.work_dir,
        log_dir=args.log_dir,
    )

    # 任务定义
    task = TaskDefinition(
        task_id=args.task_id or f"task-{uuid.uuid4().hex[:8]}",
        goal=args.goal,
        work_dir=".",  # 相对于 config.work_dir
        test_command=args.test_cmd,
    )

    # 创建引擎
    engine = LoopEngine(config=config)

    # 初始化 LLM
    try:
        engine.setup_llm()
    except (ImportError, ValueError) as e:
        print(f"❌ 初始化失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 运行
    result = engine.run(task)

    # 退出码
    sys.exit(0 if result.status.value == "succeeded" else 1)


if __name__ == "__main__":
    main()
