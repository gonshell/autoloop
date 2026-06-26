"""LoopEngine — 主引擎入口"""

import os
import time
from typing import Optional
from .config import LoopConfig, TaskDefinition
from .state import TaskState, TaskStatus
from .context import ContextManager
from .executor import Executor
from .verifier import Verifier
from .controller import LoopController
from .llm_client import LLMClient
from .tools import ToolRegistry, ReadFileTool, WriteFileTool, RunCommandTool
from .prompts import EXECUTOR_SYSTEM_PROMPT, VERIFIER_SYSTEM_PROMPT, REFLECTION_INSTRUCTION


class LoopEngine:
    """AutoLoop MVP 主引擎

    用法:
        engine = LoopEngine(config=LoopConfig(...))
        result = engine.run(TaskDefinition(...))
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        self.config = config or LoopConfig()
        self._setup_directories()

        # 上下文管理器
        self.context_manager = ContextManager(max_full_rounds=3)

        # 工具注册表
        self.tool_registry = ToolRegistry(
            work_dir_base=self.config.work_dir,
            allowed_commands=self.config.allowed_commands,
        )
        self._register_default_tools()

        # 循环控制器
        self.controller = LoopController(self.config)

        # LLM 客户端（延迟初始化）
        self._llm_client: Optional[LLMClient] = None
        self._executor: Optional[Executor] = None
        self._verifier: Optional[Verifier] = None

    def _setup_directories(self):
        os.makedirs(self.config.work_dir, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)

    def _register_default_tools(self):
        self.tool_registry.register(ReadFileTool())
        self.tool_registry.register(WriteFileTool())
        self.tool_registry.register(RunCommandTool(
            allowed_commands=self.config.allowed_commands,
        ))

    def setup_llm(self, llm_client: Optional[LLMClient] = None):
        """初始化 LLM 客户端、执行器和校验器。

        Args:
            llm_client: 可选的 LLMClient 实例。不传则自动从 config / 环境变量创建。
        """
        if llm_client is None:
            llm_client = LLMClient(
                api_key=self.config.openai_api_key,
                base_url=self.config.openai_base_url,
                default_model=self.config.execution_model,
                temperature=self.config.temperature,
            )
        self._llm_client = llm_client

        self._executor = Executor(
            llm_client=llm_client,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            model=self.config.execution_model,
        )

        self._verifier = Verifier(
            llm_client=llm_client,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            verifier_system_prompt=VERIFIER_SYSTEM_PROMPT,
            test_command="",  # 由 TaskDefinition 提供
            verification_model=self.config.verification_model,
        )

    def run(self, task: TaskDefinition) -> TaskState:
        """运行任务主循环。"""
        if not self._executor or not self._verifier:
            raise RuntimeError("请先调用 setup_llm() 初始化 LLM 客户端")

        # 设置校验器的 test_command
        self._verifier.test_command = task.test_command

        # 初始化状态
        state = TaskState(task_id=task.task_id, goal=task.goal)
        state.start()

        self._print_header(task)

        try:
            while True:
                # 决定轮次类型
                round_type = self._decide_round_type(state)
                round_record = state.new_round(round_type=round_type)

                self._print_round_start(round_record)

                if round_type == "reflect":
                    # ── 反思轮 ──
                    self._run_reflection_round(state, round_record)
                    # 反思后跑一次硬校验确认状态
                    hard_result = self._verifier.hard_check(state)
                    round_record.hard_check_passed = hard_result["passed"]
                    round_record.hard_check_details = hard_result
                else:
                    # ── 执行轮 ──
                    self._executor.execute_round(state, round_record)

                    # 每轮执行后跑硬校验
                    hard_result = self._verifier.hard_check(state)
                    round_record.hard_check_passed = hard_result["passed"]
                    round_record.hard_check_details = hard_result

                    # 更新无进展计数器
                    self.controller.update_stagnation(state, hard_result)

                state.complete_round(round_record)

                # 决策下一步
                action, reason = self.controller.decide_next(state, round_record.hard_check_details)
                round_record.next_action = action
                round_record.next_action_reason = reason

                self._print_round_result(round_record, action, reason)

                if action == "succeed":
                    # ── 终检：语义校验（可选）──
                    if self.config.semantic_verify_on_completion:
                        self._print("进入语义终检...")
                        passed, details = self._verifier.final_verify(state, round_record)
                        if passed:
                            state.mark_success(f"经过 {state.current_round} 轮循环，任务成功完成")
                        else:
                            # 语义终检未通过，但硬校验通过了 → 继续还是成功？
                            # MVP 策略：硬校验通过就算成功，语义终检只记录
                            self._print(f"  语义终检未完全通过，但测试已全部通过。置信度: {round_record.semantic_confidence}")
                            state.mark_success(
                                f"经过 {state.current_round} 轮循环，测试全部通过"
                                f"（语义置信度: {round_record.semantic_confidence}）"
                            )
                    else:
                        state.mark_success(f"经过 {state.current_round} 轮循环，任务成功完成")
                    break

                elif action == "fail":
                    state.mark_failed(reason)
                    break

                # continue / reflect → 继续循环
                self._save_state(state)

        except KeyboardInterrupt:
            state.status = TaskStatus.ERROR
            state.last_error = "用户中断 (Ctrl+C)"
            state.end_time = time.time()
        except Exception as e:
            state.status = TaskStatus.ERROR
            state.last_error = str(e)
            state.end_time = time.time()
            import traceback
            self._print(f"\n❌ 系统异常:\n{traceback.format_exc()}")

        self._save_state(state)
        self._print_summary(state)

        return state

    def _decide_round_type(self, state: TaskState) -> str:
        """决定本轮是执行还是反思"""
        if state.current_round == 0:
            return "execute"
        if self.controller._should_reflect(state):
            return "reflect"
        return "execute"

    def _run_reflection_round(self, state: TaskState, round_record):
        """运行反思轮"""
        reflection_prompt = self.context_manager.build_reflection_context(state)
        full_prompt = reflection_prompt + "\n\n" + REFLECTION_INSTRUCTION

        self._executor.execute_reflection(state, round_record, full_prompt)

        # 反思后重置无进展计数器
        state.consecutive_stagnant_rounds = 0

    def _save_state(self, state: TaskState):
        log_path = os.path.join(self.config.log_dir, f"{state.task_id}.json")
        state.save_to_file(log_path)

    # ── 终端输出 ──

    def _print(self, msg: str):
        print(msg)

    def _print_header(self, task: TaskDefinition):
        print("=" * 60)
        print("🚀 AutoLoop MVP 启动")
        print(f"  任务ID: {task.task_id}")
        print(f"  目标: {task.goal[:80]}")
        print(f"  工作目录: {task.work_dir}")
        print(f"  测试命令: {task.test_command}")
        print(f"  最大轮次: {self.config.max_rounds}")
        print(f"  执行模型: {self.config.execution_model}")
        print(f"  校验模型: {self.config.verification_model}")
        print("=" * 60)

    def _print_round_start(self, round_record):
        type_label = "反思" if round_record.round_type == "reflect" else "执行"
        print(f"\n── 第 {round_record.round_num} 轮 ({type_label}) ──")

    def _print_round_result(self, round_record, action: str, reason: str):
        icons = {"succeed": "✅", "continue": "🔄", "reflect": "🤔", "fail": "❌"}
        icon = icons.get(action, "❓")
        print(f"  {icon} {reason}")

        # 显示测试结果
        details = round_record.hard_check_details
        if details:
            passed = details.get("passed_tests", 0)
            failed = details.get("failed_tests", 0)
            if passed or failed:
                print(f"  测试: {passed} passed, {failed} failed")

        # 显示本轮工具调用摘要
        for turn in round_record.turns:
            if turn.tool_calls:
                tools_str = ", ".join(tc.tool_name for tc in turn.tool_calls)
                print(f"  工具调用 ({len(turn.tool_calls)}): {tools_str}")

    def _print_summary(self, state: TaskState):
        print("\n" + "=" * 60)
        print("📊 任务结束")
        print(f"  状态: {state.status.value}")
        print(f"  总轮次: {state.current_round}")
        print(f"  总 Turn: {state.current_turn}")
        print(f"  总耗时: {state.elapsed_seconds:.1f}s")
        print(f"  总 Token: {state.total_tokens} (入 {state.total_input_tokens} / 出 {state.total_output_tokens})")
        print(f"  总结: {state.final_summary}")
        print(f"  日志: {self.config.log_dir}/{state.task_id}.json")
        print("=" * 60)
