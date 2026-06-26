"""文件操作工具"""

import os
from typing import Any, Dict
from .base import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取文件内容。返回文件的完整文本。"

    def _parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "文件路径（相对于工作目录）",
                },
            },
            "required": ["filename"],
        }

    def execute(self, params: Dict[str, Any], work_dir: str) -> str:
        filename = params.get("filename", "")
        if not filename:
            return "错误: 缺少 filename 参数"

        filepath = self._safe_path(filename, work_dir)
        if filepath.startswith("错误"):
            return filepath

        if not os.path.exists(filepath):
            return f"错误: 文件不存在: {filename}"

        if not os.path.isfile(filepath):
            return f"错误: 不是文件: {filename}"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            # 截断过大的文件
            if len(content) > 50_000:
                content = content[:50_000] + f"\n\n... [截断: 文件共 {len(content)} 字符，只显示前 50000]"
            return content
        except Exception as e:
            return f"读取文件失败: {e}"

    @staticmethod
    def _safe_path(filename: str, work_dir: str) -> str:
        """路径安全检查：禁止越权访问"""
        if filename.startswith("/"):
            return "错误: 不允许使用绝对路径"
        if ".." in filename:
            return "错误: 不允许使用 .. 路径"
        filepath = os.path.normpath(os.path.join(work_dir, filename))
        if not filepath.startswith(os.path.normpath(work_dir)):
            return "错误: 路径越权访问"
        return filepath


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "写入文件内容（覆盖已有内容）。自动创建父目录。"

    def _parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "文件路径（相对于工作目录）",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容",
                },
            },
            "required": ["filename", "content"],
        }

    def execute(self, params: Dict[str, Any], work_dir: str) -> str:
        filename = params.get("filename", "")
        content = params.get("content", "")

        if not filename:
            return "错误: 缺少 filename 参数"

        filepath = ReadFileTool._safe_path(filename, work_dir)
        if filepath.startswith("错误"):
            return filepath

        try:
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"成功写入: {filename} ({len(content)} 字符)"
        except Exception as e:
            return f"写入文件失败: {e}"
