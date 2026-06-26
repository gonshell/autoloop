"""校验器

核心设计变更（相比原版）：
- 硬校验（pytest）每轮必跑，零 LLM 成本
- 语义校验仅在硬校验全部通过后作为终检触发
- 渐进式阈值逻辑保留但仅用于终检
"""

import re
from typing import Dict, Tuple
from .llm_client import LLMClient
from .state import TaskState, RoundRecord
from .context import ContextManager
from .tools import ToolRegistry
from .prompts import VERIFIER_SYSTEM_PROMPT


class Verifier:
    """校验器：硬校验 + 可选语义终检"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        context_manager: ContextManager,
        verifier_system_prompt: str = VERIFIER_SYSTEM_PROMPT,
        test_command: str = "pytest tests/ -v",
        verification_model: str = "gpt-4o",
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.context = context_manager
        self.system_prompt = verifier_system_prompt
        self.test_command = test_command
        self.model = verification_model

    def hard_check(self, state: TaskState) -> Dict:
        """Level 1 — 硬校验：运行测试命令。

        零 LLM 成本，每轮必跑。
        返回 {"passed": bool, "passed_tests": int, "failed_tests": int, "output": str, "error": str|None}
        """
        try:
            result = self.tools.execute(
                tool_name="run_command",
                params={"command": self.test_command},
                work_dir=state.task_id,
            )
        except Exception as e:
            return {"passed": False, "passed_tests": 0, "failed_tests": 0, "output": "", "error": str(e)}

        output = str(result)

        # 解析 pytest 输出
        passed_count = 0
        failed_count = 0

        # "X passed" 模式
        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            passed_count = int(passed_match.group(1))

        # "X failed" 模式
        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            failed_count = int(failed_match.group(1))

        # "X error" 模式
        error_match = re.search(r"(\d+) error", output)
        error_count = int(error_match.group(1)) if error_match else 0

        # 判断通过：有 passed 且没有 failed/error
        # 也处理"no tests ran"的情况
        has_tests = passed_count > 0 or failed_count > 0
        all_passed = has_tests and failed_count == 0 and error_count == 0

        # 检查退出码（在 output 末尾）
        exit_code_match = re.search(r"\[exit code: (\d+)\]", output)
        if exit_code_match:
            exit_code = int(exit_code_match.group(1))
            # pytest exit code 0 = all passed, 1 = test failures, 5 = no tests collected
            if exit_code == 0 and has_tests:
                all_passed = True
            elif exit_code == 5:
                # no tests collected — 不算通过
                all_passed = False

        return {
            "passed": all_passed,
            "passed_tests": passed_count,
            "failed_tests": failed_count,
            "error_tests": error_count,
            "output": output[:5000],
            "error": None,
        }

    def semantic_check(self, state: TaskState, hard_result: Dict) -> Dict:
        """Level 2 — 语义终检：仅在硬校验全过后调用。

        独立校验 Agent 做业务逻辑验收。
        返回 {"passed": bool, "confidence": float, "defects": list, "overall_assessment": str}
        """
        user_prompt = self.context.build_final_verify_context(state, hard_result)

        try:
            parsed, input_tokens, output_tokens = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
            )
        except Exception as e:
            return {
                "passed": False,
                "confidence": 0.0,
                "defects": [],
                "overall_assessment": f"语义校验调用失败: {e}",
            }

        return {
            "passed": parsed.get("passed", False),
            "confidence": float(parsed.get("confidence", 0.0)),
            "defects": parsed.get("defects", []),
            "overall_assessment": parsed.get("overall_assessment", ""),
        }

    def final_verify(self, state: TaskState, round_record: RoundRecord) -> Tuple[bool, Dict]:
        """终检流程：硬校验 + 语义校验（如果配置了）。

        仅在 Controller 判断"可能已成功"时调用。
        返回 (是否通过, 详情)
        """
        details = {}

        # 硬校验
        hard_result = self.hard_check(state)
        details["hard_check"] = hard_result
        round_record.hard_check_passed = hard_result["passed"]
        round_record.hard_check_details = hard_result

        if not hard_result["passed"]:
            return False, details

        # 语义终检（可选）
        if state.verified_items or hard_result.get("passed_tests", 0) > 0:
            # 只有确实有测试通过时才做语义校验
            semantic_result = self.semantic_check(state, hard_result)
            details["semantic_check"] = semantic_result
            round_record.semantic_check_passed = semantic_result["passed"]
            round_record.semantic_confidence = semantic_result["confidence"]
            round_record.semantic_defects = semantic_result["defects"]

            # 渐进式阈值（基于总轮次）
            threshold = self._calculate_threshold(state.current_round, 10)  # 用默认 max_rounds
            details["threshold"] = threshold

            if semantic_result["confidence"] < threshold:
                return False, details

        return True, details

    @staticmethod
    def _calculate_threshold(current_round: int, max_rounds: int) -> float:
        """渐进式阈值：前期宽松，后期严格"""
        progress = current_round / max(max_rounds, 1)
        if progress < 0.3:
            return 0.6
        elif progress < 0.7:
            return 0.8
        else:
            return 0.9
