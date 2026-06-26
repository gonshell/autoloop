"""工具基类与注册表"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseTool(ABC):
    """工具基类"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, params: Dict[str, Any], work_dir: str) -> str:
        """执行工具，返回字符串结果"""
        ...

    def to_openai_schema(self) -> Dict:
        """导出为 OpenAI function calling 格式的 tool schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._parameters_schema(),
            },
        }

    @abstractmethod
    def _parameters_schema(self) -> Dict:
        """返回 JSON Schema 格式的参数定义"""
        ...


class ToolRegistry:
    """工具注册表"""

    def __init__(self, work_dir_base: str = "./workspace", allowed_commands: Optional[List[str]] = None):
        self._tools: Dict[str, BaseTool] = {}
        self.work_dir_base = os.path.abspath(work_dir_base)
        self.allowed_commands = allowed_commands or []

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def execute(self, tool_name: str, params: dict, work_dir: str) -> str:
        if tool_name not in self._tools:
            return f"错误: 未知工具 '{tool_name}'。可用工具: {list(self._tools.keys())}"

        full_work_dir = os.path.normpath(os.path.join(self.work_dir_base, work_dir))

        # 安全检查：确保工作目录在 base 下
        if not full_work_dir.startswith(self.work_dir_base):
            return f"错误: 工作目录越权访问"

        os.makedirs(full_work_dir, exist_ok=True)

        return self._tools[tool_name].execute(params, full_work_dir)

    def get_tool_schemas(self) -> List[Dict]:
        """获取所有工具的 OpenAI function calling schema"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_available_tools(self) -> List[str]:
        return list(self._tools.keys())
