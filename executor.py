"""执行器 — 支持多 tool call / turn

核心设计：
- 使用 OpenAI function calling，让模型在一个 turn 内连续调用多个工具
- 每次工具执行结果通过 tool message 反馈给模型
- 模型自主决定何时停止调用工具
- 最多 max_tool_calls_per_turn 次工具调用后强制停止
"""

from typing import List
from .llm_client import LLMClient, LLMResponse
from .state import TaskState, RoundRecord, TurnRecord, ToolCallRecord
from .context import ContextManager
from .tools import ToolRegistry
from .prompts import EXECUTOR_SYSTEM_PROMPT


class Executor:
    """执行 Agent：使用 function calling 进行多工具调用"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        context_manager: ContextManager,
        system_prompt: str = EXECUTOR_SYSTEM_PROMPT,
        max_tool_calls_per_turn: int = 8,
        model: str = "gpt-4o-mini",
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.context = context_manager
        self.system_prompt = system_prompt
        self.max_tool_calls = max_tool_calls_per_turn
        self.model = model

    def execute_round(self, state: TaskState, round_record: RoundRecord) -> RoundRecord:
        """执行一轮：让 LLM 在一个 turn 内连续调用多个工具。

        返回更新后的 round_record。
        """
        turn = state.new_turn(round_record, turn_type="execute")

        # 1. 构建消息
        user_prompt = self.context.build_execution_context(state)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        tool_schemas = self.tools.get_tool_schemas()
        total_input_tokens = 0
        total_output_tokens = 0

        # 2. 多轮 tool calling 循环
        tool_call_count = 0
        while tool_call_count < self.max_tool_calls:
            response: LLMResponse = self.llm.chat(
                messages=messages,
                model=self.model,
                tools=tool_schemas if tool_schemas else None,
            )

            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            # 记录模型的思考文本（如果有）
            if response.content:
                turn.llm_reasoning = response.content

            # 没有工具调用 → 模型认为完成了
            if not response.has_tool_calls:
                break

            # 将 assistant 的 tool_calls 加入消息
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": self._serialize_args(tc["arguments"]),
                    },
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            # 执行每个工具调用
            for tc in response.tool_calls:
                tool_call_count += 1
                tool_name = tc["name"]
                tool_args = tc["arguments"]

                # 执行工具
                result = self.tools.execute(
                    tool_name=tool_name,
                    params=tool_args,
                    work_dir=state.task_id,
                )

                # 记录
                record = ToolCallRecord(
                    tool_name=tool_name,
                    arguments=tool_args,
                    result=result,
                    success=not result.startswith("错误"),
                )
                turn.add_tool_call(record)

                # 将工具结果加入消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result[:10_000],  # 截断过长结果
                })

            # 检查是否有 finish 工具调用（自定义的终止信号）
            if any(tc["name"] == "finish" for tc in response.tool_calls):
                break

        # 3. 记录 token 用量
        turn.input_tokens = total_input_tokens
        turn.output_tokens = total_output_tokens

        state.complete_turn(turn)
        return round_record

    def execute_reflection(self, state: TaskState, round_record: RoundRecord, reflection_prompt: str):
        """执行反思轮：让 LLM 复盘并输出新策略，然后继续行动。

        反思轮也使用 function calling，模型可以一边反思一边行动。
        """
        turn = state.new_turn(round_record, turn_type="reflect")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": reflection_prompt},
        ]

        tool_schemas = self.tools.get_tool_schemas()
        total_input_tokens = 0
        total_output_tokens = 0

        # 反思轮也允许工具调用（模型可以在反思后立即行动）
        tool_call_count = 0
        max_reflection_tools = self.max_tool_calls  # 反思轮同样允许多次调用

        while tool_call_count < max_reflection_tools:
            response: LLMResponse = self.llm.chat(
                messages=messages,
                model=self.model,
                tools=tool_schemas if tool_schemas else None,
            )

            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            if response.content:
                turn.llm_reasoning = response.content

            if not response.has_tool_calls:
                break

            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": self._serialize_args(tc["arguments"]),
                    },
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            for tc in response.tool_calls:
                tool_call_count += 1
                result = self.tools.execute(
                    tool_name=tc["name"],
                    params=tc["arguments"],
                    work_dir=state.task_id,
                )
                record = ToolCallRecord(
                    tool_name=tc["name"],
                    arguments=tc["arguments"],
                    result=result,
                    success=not result.startswith("错误"),
                )
                turn.add_tool_call(record)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result[:10_000],
                })

        turn.input_tokens = total_input_tokens
        turn.output_tokens = total_output_tokens
        state.complete_turn(turn)

    @staticmethod
    def _serialize_args(args: dict) -> str:
        """将参数 dict 序列化为 JSON 字符串（OpenAI API 要求）"""
        import json
        return json.dumps(args, ensure_ascii=False)
