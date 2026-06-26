# Example: 使用 AutoLoop 修复一个有 bug 的 Python 项目
#
# 前提:
#   pip install openai
#   export OPENAI_API_KEY="sk-..."
#
# 用法:
#   python example_bugfix.py

from autoloop import LoopEngine, LoopConfig, TaskDefinition


def main():
    # 1. 配置
    config = LoopConfig(
        max_rounds=10,
        max_total_tokens=80_000,
        timeout_seconds=300,
        execution_model="gpt-4o-mini",
        verification_model="gpt-4o",
        max_tool_calls_per_turn=8,
        work_dir="./workspace",
        log_dir="./logs",
    )

    # 2. 定义任务
    task = TaskDefinition(
        task_id="bugfix-demo-001",
        goal=(
            "修复 calculator.py 中的所有 bug，让 tests/test_calculator.py 中的所有测试用例通过。"
            "注意：add() 函数需要处理负数，multiply() 函数不能用循环实现（会栈溢出），"
            "divide() 函数需要处理除零。"
        ),
        work_dir="bugfix-demo-001",  # 相对于 config.work_dir
        test_command="pytest tests/test_calculator.py -v",
        source_files=["calculator.py", "tests/test_calculator.py"],
    )

    # 3. 创建引擎并运行
    engine = LoopEngine(config=config)
    engine.setup_llm()  # 从环境变量读取 API Key

    result = engine.run(task)

    # 4. 输出结果
    print(f"\n最终状态: {result.status.value}")
    print(f"总轮次: {result.current_round}")
    print(f"总 Token: {result.total_tokens}")


if __name__ == "__main__":
    main()
