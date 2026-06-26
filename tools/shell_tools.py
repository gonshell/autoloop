"""Shell 命令执行工具"""

import shlex
import subprocess
from typing import Any, Dict, List, Optional
from .base import BaseTool


class RunCommandTool(BaseTool):
    name = "run_command"
    description = "执行 Shell 命令。仅允许白名单中的命令。返回 stdout + stderr + 退出码。"

    def __init__(self, allowed_commands: Optional[List[str]] = None, timeout: int = 30):
        self.allowed_commands = allowed_commands or []
        self.timeout = timeout

    def _parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令",
                },
            },
            "required": ["command"],
        }

    def execute(self, params: Dict[str, Any], work_dir: str) -> str:
        command = params.get("command", "")
        if not command:
            return "错误: 缺少 command 参数"

        # 安全检查 1：白名单
        cmd_name = self._extract_command_name(command)
        if not self._is_command_allowed(cmd_name):
            return f"错误: 命令 '{cmd_name}' 不在白名单中。允许的命令: {self.allowed_commands}"

        # 安全检查 2：危险模式
        danger = self._check_dangerous_patterns(command)
        if danger:
            return f"错误: 检测到危险操作 '{danger}'，已阻止"

        # 安全检查 3：命令注入（检查 shell 特殊字符组合）
        if self._has_injection_risk(command):
            return "错误: 检测到潜在的命令注入风险，已阻止。请使用简单命令。"

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            parts = []
            if result.stdout:
                # 截断过长输出
                stdout = result.stdout
                if len(stdout) > 10_000:
                    stdout = stdout[:10_000] + f"\n... [截断: 共 {len(result.stdout)} 字符]"
                parts.append(stdout)
            if result.stderr:
                stderr = result.stderr
                if len(stderr) > 5_000:
                    stderr = stderr[:5_000] + f"\n... [截断: 共 {len(result.stderr)} 字符]"
                parts.append(f"[stderr]\n{stderr}")
            parts.append(f"[exit code: {result.returncode}]")

            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"错误: 命令执行超时 ({self.timeout}秒)"
        except Exception as e:
            return f"命令执行失败: {e}"

    @staticmethod
    def _extract_command_name(command: str) -> str:
        """提取命令名（第一个词）"""
        try:
            tokens = shlex.split(command.strip())
            if not tokens:
                return ""
            # 取第一个非空非 flag 的 token（跳过 env, nice 等前缀）
            for tok in tokens:
                if not tok.startswith("-"):
                    return tok
            return tokens[0]
        except ValueError:
            # shlex 解析失败时 fallback
            return command.strip().split()[0] if command.strip() else ""

    def _is_command_allowed(self, cmd_name: str) -> bool:
        if not self.allowed_commands:
            return True
        # 去掉路径前缀，只看命令名
        base_name = cmd_name.rsplit("/", maxsplit=1)[-1]
        return base_name in self.allowed_commands

    @staticmethod
    def _check_dangerous_patterns(command: str) -> str:
        """检查危险操作模式，返回匹配的模式或空字符串"""
        dangerous = [
            "rm -rf /",
            "rm -rf ~",
            "mkfs",
            "dd if=",
            "> /dev/sd",
            "sudo rm",
            ":(){ :|:& };:",  # fork bomb
            "chmod -R 777 /",
            "wget | sh",
            "curl | sh",
        ]
        cmd_lower = command.lower()
        for pattern in dangerous:
            if pattern in cmd_lower:
                return pattern
        return ""

    @staticmethod
    def _has_injection_risk(command: str) -> bool:
        """检查命令注入风险（通过命令参数注入额外命令）

        这是一个保守的检查。允许正常的管道和重定向，
        但阻止通过 -c 参数等方式注入。
        """
        # 检查 python -c 中的 os.system / subprocess / __import__
        lower = command.lower()
        if "python" in lower and "-c" in lower:
            risky_calls = ["os.system", "os.popen", "subprocess", "__import__", "exec(", "eval("]
            for call in risky_calls:
                if call in lower:
                    return call
        return ""
