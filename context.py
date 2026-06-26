"""三级上下文管理器

L0: 完整上下文 — 最近 N 轮的完整交互记录
L1: 摘要上下文 — 更早轮次的结构化摘要（一行/轮）
L2: 全局状态 — 任务目标、约束、已验证项、累计进度（始终保留）
"""

from typing import List
from .state import TaskState, RoundRecord, TurnRecord, ToolCallRecord


class ContextManager:
    """三级上下文管理器"""

    def __init__(self, max_full_rounds: int = 3):
        self.max_full_rounds = max_full_rounds

    def build_execution_context(self, state: TaskState) -> str:
        """构建执行 Agent 的上下文（user message）"""
        parts = []

        # L2: 全局目标
        parts.append(f"## 任务目标\n{state.goal}\n")

        # L2: 已验证通过项
        if state.verified_items:
            parts.append("## 已确认完成的事项")
            for item in state.verified_items:
                parts.append(f"- [x] {item}")
            parts.append("")

        # L2: 当前进度
        parts.append(f"## 当前进度")
        parts.append(f"- 第 {state.current_round} 轮")
        parts.append(f"- 累计 Token: {state.total_tokens}")
        parts.append(f"- 已用时间: {state.elapsed_seconds:.1f}s")
        parts.append("")

        # L1 + L0: 历史记录
        history = self._build_history(state.round_history)
        parts.append(f"## 历史执行记录\n{history}\n")

        # 行动指引
        parts.append("## 下一步")
        parts.append("请基于以上信息，决定下一步要做什么。你可以连续调用多个工具来完成一个完整的操作。")
        parts.append("当你认为本轮修改完成时，调用 run_command 运行测试来验证。")

        return "\n".join(parts)

    def build_reflection_context(self, state: TaskState) -> str:
        """构建反思 Agent 的上下文"""
        parts = []

        parts.append(f"## 任务目标\n{state.goal}\n")
        parts.append(f"## 问题\n")
        parts.append(f"你已经连续尝试了 {state.consecutive_stagnant_rounds} 轮，但没有实质进展。")
        parts.append(f"请先停下来做一次深度复盘。\n")

        # 最近 5 轮的摘要
        recent = state.round_history[-5:]
        parts.append(f"## 最近 {len(recent)} 轮的尝试\n")
        for r in recent:
            parts.append(f"### 第 {r.round_num} 轮")
            for t in r.turns:
                for tc in t.tool_calls:
                    parts.append(f"- 调用 {tc.tool_name}: {self._summarize_args(tc.arguments)}")
                    parts.append(f"  结果: {tc.result[:200]}")
            if r.hard_check_passed is not None:
                status = "✅ 通过" if r.hard_check_passed else f"❌ 失败"
                failed = r.hard_check_details.get("failed_tests", "?")
                parts.append(f"- 测试: {status} (失败用例: {failed})")
            parts.append("")

        parts.append("## 请复盘以下问题")
        parts.append("1. 你之前的修改思路是什么？")
        parts.append("2. 为什么这些修改没有解决问题？根本原因在哪？")
        parts.append("3. 你是不是忽略了什么重要信息？")
        parts.append("4. 接下来你打算换什么思路？给出具体的下一步计划。")

        return "\n".join(parts)

    def build_final_verify_context(self, state: TaskState, hard_result: dict) -> str:
        """构建语义终检的上下文"""
        parts = []

        parts.append(f"## 任务目标\n{state.goal}\n")

        if state.success_criteria:
            parts.append(f"## 额外成功标准\n{state.success_criteria}\n")

        parts.append(f"## 硬校验结果")
        parts.append(f"- 测试通过: {'是' if hard_result.get('passed') else '否'}")
        parts.append(f"- 通过用例: {hard_result.get('passed_tests', 0)}")
        parts.append(f"- 失败用例: {hard_result.get('failed_tests', 0)}")

        if hard_result.get("output"):
            parts.append(f"\n测试输出:\n{hard_result['output'][:3000]}\n")

        parts.append(f"## 执行过程概要")
        parts.append(f"- 总轮次: {state.current_round}")
        parts.append(f"- 总 Token: {state.total_tokens}")

        return "\n".join(parts)

    def _build_history(self, history: List[RoundRecord]) -> str:
        """组装历史记录：最近 N 轮完整，更早的给摘要"""
        if not history:
            return "（暂无历史记录，这是第一轮）"

        parts = []

        # 更早的轮次：摘要形式（L1）
        if len(history) > self.max_full_rounds:
            early = history[: -self.max_full_rounds]
            parts.append("### 早期尝试摘要")
            for r in early:
                actions = []
                for t in r.turns:
                    for tc in t.tool_calls:
                        actions.append(tc.tool_name)
                action_str = ", ".join(actions) if actions else "无操作"
                status = ""
                if r.hard_check_passed is True:
                    status = " → 测试通过"
                elif r.hard_check_passed is False:
                    failed = r.hard_check_details.get("failed_tests", "?")
                    status = f" → 测试失败({failed}个)"
                parts.append(f"- 第{r.round_num}轮: [{action_str}]{status}")
            parts.append("")

        # 最近 N 轮：完整记录（L0）
        recent = history[-self.max_full_rounds:]
        parts.append("### 最近几轮详细记录")
        for r in recent:
            parts.append(f"\n--- 第 {r.round_num} 轮 ---")
            for t in r.turns:
                for tc in t.tool_calls:
                    parts.append(f"  调用 {tc.tool_name}({self._summarize_args(tc.arguments)})")
                    result_preview = tc.result[:500]
                    if len(tc.result) > 500:
                        result_preview += "..."
                    parts.append(f"  → {result_preview}")
            if r.hard_check_passed is not None:
                status = "✅ 通过" if r.hard_check_passed else "❌ 失败"
                parts.append(f"  测试: {status}")
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _summarize_args(args: dict) -> str:
        """简短展示工具参数"""
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 80:
                v_str = v_str[:80] + "..."
            parts.append(f"{k}={v_str}")
        return ", ".join(parts)
