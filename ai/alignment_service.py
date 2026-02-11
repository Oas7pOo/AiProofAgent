import json
import re
import requests
from typing import Any, Dict, List, Optional


class AIResponseParser:
    @staticmethod
    def clean_and_parse_batch_json(raw_text: str) -> List[Dict[str, Any]]:
        """专门解析 JSON 列表 (极简高效版)。"""
        if not isinstance(raw_text, str) or not raw_text.strip():
            return []

        # 1) 定位最外层的列表 [ ... ]
        start = raw_text.find("[")
        end = raw_text.rfind("]")

        if start != -1 and end != -1 and end > start:
            json_str = raw_text[start : end + 1]
        else:
            # 兼容：只返回了单个对象 { ... }
            start_obj = raw_text.find("{")
            end_obj = raw_text.rfind("}")
            if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
                json_str = f"[{raw_text[start_obj : end_obj + 1]}]"
            else:
                return []

        # 2) 直接解析
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 3) 清洗后再解析：处理控制字符与尾逗号
        def escape_control_chars(match):
            char = match.group(0)
            if char == "\n":
                return "\\n"
            if char == "\t":
                return "\\t"
            return ""

        sanitized = re.sub(r"[\x00-\x1f]", escape_control_chars, json_str)
        sanitized = re.sub(r",\s*([\]\}])", r"\1", sanitized)

        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            return []


class LLMClient:
    """纯 LLM 传输层：只负责请求/响应/解析，不拼 prompt，不认识业务 schema。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.parser = AIResponseParser()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.config.get('api_key', '')}",
                "Content-Type": "application/json",
            }
        )

    def request(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages 必须是非空 list。")

        base_url = str(self.config.get("base_url", "") or "").rstrip("/")
        model = self.config.get("model")
        if not base_url or not model:
            raise ValueError("config 必须包含 base_url 与 model。")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # max_tokens=None -> 不传，交给服务端默认
        if max_tokens is None:
            max_tokens = self.config.get("max_tokens")
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # temperature=None -> 不传，交给服务端默认（遵循 config.yaml）
        if temperature is None:
            temperature = self.config.get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature

        response = self.session.post(
            f"{base_url}/chat/completions",
            json=payload,
            timeout=timeout or self.config.get("timeout", 120),
        )

        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}: {response.text}")

        result = response.json()
        if "choices" not in result:
            if "error" in result:
                raise ValueError(f"API Error: {result['error']}")
            raise KeyError(f"No choices: {result}")

        content = result["choices"][0]["message"]["content"]
        parsed_list = self.parser.clean_and_parse_batch_json(content)
        if not parsed_list:
            raise ValueError(f"JSON解析为空或格式错误。原始内容前50字符: {str(content)[:50]}...")
        return parsed_list

    def request_prompt(
        self,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        return self.request(
            [{"role": "user", "content": str(prompt)}],
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
        )



# 兼容旧命名：外部若仍 import AlignmentService，将得到同一个 LLMClient。
AlignmentService = LLMClient
