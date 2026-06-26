"""LLM 客户端抽象层

支持 OpenAI 兼容接口（function calling + structured output）。
适配 OpenAI、Anthropic（via proxy）、本地模型（vLLM/Ollama）等。
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # 延迟报错，在首次使用时提示


@dataclass
class LLMResponse:
    """LLM 响应的统一结构"""
    content: str = ""  # 文本内容
    tool_calls: List[Dict] = field(default_factory=list)  # 工具调用列表
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    finish_reason: str = ""  # stop / tool_calls / length

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    """OpenAI 兼容的 LLM 客户端

    用法:
        client = LLMClient(api_key="sk-...", base_url="https://api.openai.com/v1")
        response = client.chat(
            messages=[{"role": "user", "content": "hello"}],
            tools=[{"type": "function", "function": {...}}],
            model="gpt-4o-mini",
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_retries: int = 3,
    ):
        if OpenAI is None:
            raise ImportError(
                "请安装 openai 包: pip install openai"
            )

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.default_model = default_model
        self.temperature = temperature
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError(
                "未配置 API Key。请设置 OPENAI_API_KEY 环境变量，或在构造时传入 api_key 参数。"
            )

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送聊天请求，返回统一的 LLMResponse。

        Args:
            messages: OpenAI 格式的消息列表
            model: 模型名称，默认用构造时的 default_model
            tools: 工具定义列表（function calling 格式）
            response_format: 响应格式约束（如 {"type": "json_object"}）
            temperature: 温度，默认用构造时的值
            max_tokens: 最大输出 token 数
        """
        kwargs: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if response_format:
            kwargs["response_format"] = response_format

        # 重试逻辑（处理速率限制和临时错误）
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.chat.completions.create(**kwargs)
                return self._parse_response(response)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # 速率限制或服务器错误时重试
                if any(kw in error_str for kw in ("rate_limit", "429", "500", "502", "503")):
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                # 其他错误直接抛
                raise

        raise RuntimeError(f"LLM 调用失败（重试 {self.max_retries} 次后）: {last_error}")

    def _parse_response(self, response) -> LLMResponse:
        """将 OpenAI 响应转换为统一的 LLMResponse"""
        choice = response.choices[0]
        message = choice.message

        result = LLMResponse(
            content=message.content or "",
            model=response.model,
            finish_reason=choice.finish_reason or "",
        )

        # 提取 token 用量
        if response.usage:
            result.input_tokens = response.usage.prompt_tokens
            result.output_tokens = response.usage.completion_tokens

        # 提取工具调用
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}

                result.tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return result

    def chat_json(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> Tuple[Dict, int, int]:
        """便捷方法：发送请求并要求 JSON 输出，直接返回解析后的 dict。

        Returns:
            (parsed_json, input_tokens, output_tokens)
        """
        response = self.chat(
            messages=messages,
            model=model,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块提取
            content = response.content.strip()
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end > start:
                    parsed = json.loads(content[start:end].strip())
                else:
                    parsed = {"error": "JSON 解析失败", "raw": content[:500]}
            elif "```" in content:
                start = content.find("```") + 3
                # 跳过语言标识符
                newline = content.find("\n", start)
                if newline > start:
                    start = newline + 1
                end = content.find("```", start)
                if end > start:
                    parsed = json.loads(content[start:end].strip())
                else:
                    parsed = {"error": "JSON 解析失败", "raw": content[:500]}
            else:
                parsed = {"error": "JSON 解析失败", "raw": content[:500]}

        return parsed, response.input_tokens, response.output_tokens
