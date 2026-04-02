**  展现思考**

## Gemini said

在 `AiProofAgent` 项目中，LLM 请求的核心实现位于 `ai/alignment_service.py` 文件中。它主要通过 `LLMClient` 类（在代码中被赋予别名 `AlignmentService`）来管理。

以下是发出请求和接收响应的具体代码逻辑拆解，你可以对比检查你的重构代码：

### **1. 发出请求的准备与发送 (Sending)**

请求的发送主要依赖 `requests.Session` 来维持长连接，并从 `config.yaml` 中读取配置。

#### **初始化阶段**

在 `__init__` 中，程序会预设请求头，确保每个请求都带上正确的 `Authorization`：

**Python**

```
# ai/alignment_service.py
def __init__(self, config: Dict[str, Any]):
    self.config = config or {}
    self.parser = AIResponseParser()
    self.session = requests.Session()
    self.session.headers.update({
        "Authorization": f"Bearer {self.config.get('api_key', '')}",
        "Content-Type": "application/json",
    })

```

#### **构建 Payload 并发送**

`request` 方法是执行请求的核心：

1. **拼接 URL**：将 `base_url` 与 `/chat/completions` 组合。
2. **组装数据**：包含 `model`、`messages` 以及从配置中读取的 `max_tokens` 和 `temperature`。
3. **发出 POST**：使用 `self.session.post` 并传入 `timeout`。

**Python**

```
# ai/alignment_service.py
def request(self, messages, *, max_tokens=None, timeout=None, temperature=None):
    base_url = str(self.config.get("base_url", "") or "").rstrip("/")
    payload = {
        "model": self.config.get("model"),
        "messages": messages,
        "max_tokens": max_tokens or self.config.get("max_tokens"),
        "temperature": temperature or self.config.get("temperature"),
    }
    
    response = self.session.post(
        f"{base_url}/chat/completions",
        json=payload,
        timeout=timeout or self.config.get("timeout", 120),
    )
    # 检查 HTTP 状态码
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}: {response.text}")
    
    return response.json()

```

### **2. 接收与解析响应 (Receiving & Parsing)**

这是最容易出错的部分，因为 AI 返回的内容往往包含 Markdown 代码块或不规范的 JSON 格式。项目通过 `AIResponseParser` 进行容错处理。

#### **提取内容**

首先从标准的 API 响应结构中提取字符串：

**Python**

```
result = response.json()
content = result["choices"][0]["message"]["content"]

```

#### **清洗与解析 JSON (**`clean_and_parse_batch_json`**)**

由于该工具要求 AI 返回 JSON 列表，解析逻辑做了以下增强：

1. **正则定位**：寻找最外层的 `[` 和 `]`，剔除 AI 可能多说的废话（如 "Here is the JSON:"）。
2. **控制字符过滤**：使用正则 `[\x00-\x1f]` 替换掉非法控制字符。
3. **尾逗号修复**：通过 `re.sub(r",\s*([\]\}])", r"\1", sanitized)` 移除 JSON 对象末尾多余的逗号，这是 AI 经常犯的错误。

**Python**

```
# ai/alignment_service.py 中的关键解析片段
start = raw_text.find("[")
end = raw_text.rfind("]")
if start != -1 and end != -1:
    json_str = raw_text[start : end + 1]
    # 清洗掉非法控制字符和尾逗号后进行 json.loads()

```

### **3. 在业务流程中的调用逻辑**

在 `tools/proofread_service.py` 中，`StageRunner` 负责驱动这一过程，并包含了**自动重试**和**任务拆分**逻辑：

- **重试机制**：如果请求失败或解析失败，`process_recursive` 会尝试最多 3 次。
- **二分拆分**：如果单次请求的 Block 太多导致 AI 报错或返回格式混乱，程序会将该批次（Batch）平分为两半，分别再次递归请求，直到成功为止。
- **补齐逻辑**：如果 AI 返回的数量少于发送的数量，`StageRunner` 会调用 `fill_missing` 填充错误标记，保证数据对齐。

### **跑不通的常见排查点：**

1. **Base URL 格式**：确保 `config.yaml` 中的 `base_url` 不带末尾斜杠，代码中用的是 `rstrip("/")`。
2. **API 兼容性**：该代码假设 API 遵循 OpenAI 的 `/v1/chat/completions` 标准。
3. **JSON 格式限制**：AI 的 Prompt 中明确要求“不要包含 Markdown 标记”，如果你重构时修改了 Prompt，AI 返回了 `json ... ` ，原生解析器需要 `AIResponseParser` 提取中间部分才能工作。
4. **并发限制**：如果你在 UI 或 CLI 中开启了多线程（`ai_max_workers > 1`），请确认你的 API Key 支持足够的 QPS/RPM，否则会频繁触发 HTTP 429 错误。

