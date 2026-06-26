"""任务状态管理"""

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
class ToolCallRecord:
    """单次工具调用记录"""
    tool_name: str
    arguments: Dict
    result: str
    success: bool = True
    duration_ms: float = 0.0


@dataclass
class TurnRecord:
    """单轮（一个 LLM turn）执行记录"""
    turn_num: int
    round_num: int  # 所属的循环轮次
    turn_type: str = "execute"  # execute / reflect / verify

    # LLM 交互
    input_tokens: int = 0
    output_tokens: int = 0
    llm_reasoning: str = ""  # 模型的思考过程（如果支持）
    tool_calls: List[ToolCallRecord] = field(default_factory=list)

    # 时间
    start_time: float = 0.0
    end_time: float = 0.0

    def add_tool_call(self, record: ToolCallRecord):
        self.tool_calls.append(record)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0

    @property
    def all_tool_names(self) -> List[str]:
        return [tc.tool_name for tc in self.tool_calls]


@dataclass
class RoundRecord:
    """单循环轮次记录（包含 1~N 个 turn）"""
    round_num: int
    round_type: str = "execute"  # execute / reflect / final_verify

    turns: List[TurnRecord] = field(default_factory=list)

    # 校验结果（仅 execute/verify 轮有）
    hard_check_passed: Optional[bool] = None
    hard_check_details: Dict = field(default_factory=dict)

    # 语义终检（仅 final_verify 轮有）
    semantic_check_passed: Optional[bool] = None
    semantic_confidence: float = 0.0
    semantic_defects: List = field(default_factory=list)

    # 决策
    next_action: str = ""  # continue / succeed / fail / reflect
    next_action_reason: str = ""

    # 时间
    start_time: float = 0.0
    end_time: float = 0.0

    def add_turn(self, turn: TurnRecord):
        self.turns.append(turn)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0

    @property
    def last_turn(self) -> Optional[TurnRecord]:
        return self.turns[-1] if self.turns else None


@dataclass
class TaskState:
    """任务全局状态"""
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    current_round: int = 0
    current_turn: int = 0  # 全局 turn 计数
    start_time: float = 0.0
    end_time: float = 0.0

    round_history: List[RoundRecord] = field(default_factory=list)
    verified_items: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    final_summary: str = ""

    # 连续无进展计数器
    consecutive_stagnant_rounds: int = 0

    def start(self):
        self.status = TaskStatus.RUNNING
        self.start_time = time.time()

    def new_round(self, round_type: str = "execute") -> RoundRecord:
        self.current_round += 1
        record = RoundRecord(
            round_num=self.current_round,
            round_type=round_type,
            start_time=time.time(),
        )
        self.round_history.append(record)
        return record

    def new_turn(self, round_record: RoundRecord, turn_type: str = "execute") -> TurnRecord:
        self.current_turn += 1
        turn = TurnRecord(
            turn_num=self.current_turn,
            round_num=round_record.round_num,
            turn_type=turn_type,
            start_time=time.time(),
        )
        round_record.add_turn(turn)
        return turn

    def complete_turn(self, turn: TurnRecord):
        turn.end_time = time.time()

    def complete_round(self, round_record: RoundRecord):
        round_record.end_time = time.time()

    def mark_success(self, summary: str = ""):
        self.status = TaskStatus.SUCCEEDED
        self.end_time = time.time()
        self.final_summary = summary

    def mark_failed(self, reason: str):
        self.status = TaskStatus.FAILED
        self.end_time = time.time()
        self.last_error = reason
        self.final_summary = f"任务失败: {reason}"

    @property
    def total_input_tokens(self) -> int:
        return sum(r.total_input_tokens for r in self.round_history)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.total_output_tokens for r in self.round_history)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time if self.start_time else 0.0

    @property
    def last_round(self) -> Optional[RoundRecord]:
        return self.round_history[-1] if self.round_history else None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "current_round": self.current_round,
            "current_turn": self.current_turn,
            "duration_seconds": round(self.elapsed_seconds, 2),
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "round_history": [
                {
                    "round_num": r.round_num,
                    "round_type": r.round_type,
                    "turns": [
                        {
                            "turn_num": t.turn_num,
                            "input_tokens": t.input_tokens,
                            "output_tokens": t.output_tokens,
                            "tool_calls": [
                                {
                                    "tool_name": tc.tool_name,
                                    "arguments": tc.arguments,
                                    "result": tc.result[:500],
                                    "success": tc.success,
                                }
                                for tc in t.tool_calls
                            ],
                            "duration_ms": round(t.duration_seconds * 1000, 1),
                        }
                        for t in r.turns
                    ],
                    "hard_check_passed": r.hard_check_passed,
                    "hard_check_details": r.hard_check_details,
                    "semantic_check_passed": r.semantic_check_passed,
                    "semantic_confidence": r.semantic_confidence,
                    "next_action": r.next_action,
                    "next_action_reason": r.next_action_reason,
                    "duration_seconds": round(r.duration_seconds, 2),
                }
                for r in self.round_history
            ],
            "final_summary": self.final_summary,
            "last_error": self.last_error,
        }

    def save_to_file(self, filepath: str):
        import os
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
