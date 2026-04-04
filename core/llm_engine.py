import logging
import requests
import json
from utils.config import ConfigManager
from typing import Optional

logger = logging.getLogger("AiProofAgent.LlmEngine")

class LlmEngine:
    def __init__(self, config_path="config.yaml"):
        cfg = ConfigManager(config_path)
        
        # 智能读取：同时查找嵌套格式和扁平格式，防止旧的 config.yaml 干扰
        def _get_val(keys, default):
            for k in keys:
                v = cfg.get(k)
                if v is not None and str(v).strip() != "":
                    return v
            return default

        self.base_url = _get_val(["llm.base_url", "base_url"], "https://api.openai.com/v1")
        self.model = _get_val(["llm.model", "model"], "gpt-3.5-turbo")
        self.api_key = _get_val(["llm.api_key", "api_key"], "")
        self.timeout = int(_get_val(["llm.timeout", "timeout"], 120))

        logger.info(f"LLM配置读取结果: URL={self.base_url}, Model={self.model}, Key已填入={'是' if self.api_key else '否'}")
        
        # 初始化 requests Session
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def request_prompt(self, prompt: str, system_prompt: str = "You are a helpful assistant.", timeout: Optional[int] = None) -> str:
        """
        使用 requests 直接发送 LLM 请求，支持兼容 OpenAI 格式的所有大模型接口。
        """
        logger.info(f"发送 LLM 请求，prompt 长度: {len(prompt)}")
        
        try:
            # 构建 payload
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
            
            # 拼接 URL
            base_url_clean = str(self.base_url or "").rstrip("/").strip('`')
            url = f"{base_url_clean}/chat/completions"
            logger.info(f"发送请求到: {url}")
            
            # 发送请求
            response = self.session.post(
                url,
                json=payload,
                timeout=timeout or self.timeout
            )
            
            logger.info(f"响应状态码: {response.status_code}")
            # 截断响应内容到前200字符，避免日志过长
            response_preview = response.text[:200] + "..." if len(response.text) > 200 else response.text
            logger.info(f"响应内容: {response_preview}")
            
            # 检查 HTTP 状态码
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}: {response.text}")
            
            # 解析响应
            result = response.json()
            
            # 兼容处理 iflow.cn 格式
            if 'status' in result and result['status'] != '0':
                err_msg = result.get('msg') or "API 请求失败"
                raise ValueError(f"接口代理层拦截了请求或返回异常: {err_msg}")
            
            # 标准 OpenAI 格式
            if 'choices' in result:
                content = result['choices'][0]['message']['content']
                return content.strip() if content else ""
            # iflow.cn 格式
            elif 'body' in result and result['body']:
                body = result['body']
                if isinstance(body, dict) and 'choices' in body:
                    content = body['choices'][0]['message']['content']
                    return content.strip() if content else ""
            
            raise ValueError(f"返回结构缺失 choices 字段: {json.dumps(result, ensure_ascii=False)}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求失败: {e}")
            raise ValueError(f"网络请求失败: {e}")
        except Exception as e:
            logger.error(f"LLM 请求发生异常: {e}")
            raise e
