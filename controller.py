"""循环决策控制器"""

from typing import Tuple
from .state import TaskState, RoundRecord, TaskStatus
from .config import LoopConfig


class LoopController:
    """循环决策控制器"""

    def __init__(self, config: LoopConfig):
        self.config = config

    def decide_next(self, state: TaskState, hard_result: dict) -> Tuple[str, str]:
        """每轮硬校验后决定下一步。

        Returns:
            (action, reason)
            action: "succeed" / "continue" / "reflect" / "fail"
        """
        # 1. 硬校验通过 → 可能成功
        if hard_result.get("passed"):
            return "succeed", "所有测试通过，进入终检"

        # 2. 检查熔断条件
        fail_reason = self._check_circuit_breaker(state)
        if fail_reason:
            return "fail", fail_reason

        # 3. 检查是否需要反思
        if self._should_reflect(state):
            return "reflect", f"连续 {state.consecutive_stagnant_rounds} 轮无进展，触发反思"

        # 4. 继续
        return "continue", f"测试未通过 (失败 {hard_result.get('failed_tests', '?')} 个)，继续尝试"

    def _check_circuit_breaker(self, state: TaskState) -> str:
        """检查熔断条件"""
        # 最大轮次
        if state.current_round >= self.config.max_rounds:
            return f"达到最大轮次限制 ({self.config.max_rounds} 轮)"

        # Token 预算
        if state.total_tokens >= self.config.max_total_tokens:
            return f"达到 Token 预算限制 ({self.config.max_total_tokens})"

        # 超时
        if state.elapsed_seconds >= self.config.timeout_seconds:
            return f"超时 ({self.config.timeout_seconds} 秒)"

        return ""

    def _should_reflect(self, state: TaskState) -> bool:
        """判断是否触发反思轮"""
        if state.consecutive_stagnant_rounds < self.config.reflection_trigger_stagnant_rounds:
            return False
        # 避免连续反思
        if state.last_round and state.last_round.round_type == "reflect":
            return False
        return True

    def update_stagnation(self, state: TaskState, hard_result: dict):
        """更新无进展计数器。

        进展判定：本轮失败用例数 < 上一轮失败用例数。
        """
        if len(state.round_history) < 2:
            # 第一轮默认算有进展
            state.consecutive_stagnant_rounds = 0
            return

        # 找上一个非反思轮的硬校验结果
        prev_hard = None
        for r in reversed(state.round_history[:-1]):
            if r.round_type != "reflect" and r.hard_check_passed is not None:
                prev_hard = r.hard_check_details
                break

        if prev_hard is None:
            state.consecutive_stagnant_rounds = 0
            return

        prev_failed = prev_hard.get("failed_tests", 999)
        curr_failed = hard_result.get("failed_tests", 999)

        if curr_failed < prev_failed:
            # 有进展：失败用例减少
            state.consecutive_stagnant_rounds = 0
        else:
            state.consecutive_stagnant_rounds += 1
