# AiProofAgent

**AI 驱动的专业级翻译校对与 OCR 文档处理工具**

`AiProofAgent` 是一款专为文档本地化、游戏翻译审校及专业学术文档转换设计的重型武器。它深度整合了 **PaddleOCR-VL-1.5** 的版面分析能力与 **DeepSeek/OpenAI/Claude** 等顶级大语言模型的推理能力，为用户提供从原始 PDF 结构化提取到全自动 AI 审校，再到专业级文档导出的全生命周期解决方案。

在本地化翻译领域，传统的 OCR 提取往往会导致排版错乱、术语丢失。`AiProofAgent` 的出现正是为了解决这些痛点，让译者能从繁琐的格式调整中解放，专注于内容的打磨。

> [!IMPORTANT] **版本更新说明：推荐使用** **`test`** **分支** 当前 `test` 分支已经过深度重构，支持文字版与图片扫描版 PDF 的完美解析。它不仅优化了 Paratranz 平台的直入直出体验，还引入了全新的多线程并发调度算法，是追求极致效率用户的首选。

## ✨ 核心优势与亮点

### 1. 卓越的 PDF 感知与解析 (文字/扫描版全覆盖)

- **全能解析引擎**：无论是原生导出的文字版 PDF，还是清晰度欠佳的图片扫描版，系统均能通过高度优化的 OCR 管道进行还原。
- **极速识别体验**：利用 PaddleOCR-VL-1.5 的高性能推理，系统能以秒级速度完成单页解析。这种快速的预处理能力为后续的 AI 大规模处理夯实了基础。
- **完美表格与结构还原**：支持复杂表格（包括极难处理的**跨页表格**）的自动识别、合并与 Markdown 化。系统能敏锐捕捉文档的分级标题结构，确保提取后的内容逻辑清晰，不再是散乱的文本块。

### 2. Paratranz 平台生态深度集成

- **直入直出，无缝对接**：深度支持 Paratranz 翻译平台的标准 JSON/CSV 格式。用户可以直接将平台导出的待译文件导入本工具进行 AI 处理，完成后直接写回原格式上传。
- **“翻译+校对”一条龙**：本工具不仅是简单的校对器，更是一个完整的翻译中转站。通过一校（初步翻译/术语提取）和二校（精修/润色）的组合，极大地优化了本地化流水线。

### 3. “奇迹般”的并发处理性能

- **高并发秒级响应**：通过自研的 `BatchTaskRunner` 并发架构，系统可以同时调度多个 AI 进程。
- **效率奇迹**：在合理配置 API 并发数的情况下，**仅需约一分钟即可完成一本 400 页书籍的 AI 二校任务**。
- **成本参考**：这种极速体验在带来巨大生产力提升的同时，成本也相当亲民（整个流程处理 400 页的书籍约需 160 元左右的 Token 费用，远低于人工校对的成本与时间支出）。

### 4. 专业级文档导出 (DOC/Docx)

- **结构化映射**：导出的 Word 文档不再是扁平的文字，而是完整保留了**分级标题**。
- **表格支持**：对表格的支持达到了工业级水准，复杂表项在导出后依然保持良好的可读性与编辑性。
- **体验升级**：致力于提供“最舒服”的导出体验，让技术产物直接转化为可以直接提交给客户的专业报告。

## 🏗️ 系统架构

项目采用**分层架构设计**，确保核心逻辑与界面解耦，方便开发者进行二次开发或 API 反代：

```
AiProofAgent/
├── models/               # 【数据模型层】定义统一的 DTO (TranslationBlock)，贯穿全生命周期
├── core/                 # 【核心引擎层】
│   ├── ocr_engine.py     # PaddleOCR 请求、自适应重试与 Markdown 分段逻辑
│   ├── llm_engine.py     # OpenAI 兼容接口封装，支持多种模型协议
│   ├── md2doc.py         # 核心转换逻辑：Markdown 标签精准映射至 Word 样式
│   ├── term_manager.py   # 术语模糊匹配引擎，解决 OCR 混淆字符问题
│   └── format_converter.py # 负责 Paratranz、JSON、CSV、JS 等格式的序列化
├── workflows/            # 【业务工作流】
│   ├── proofread1_flow.py# 一校自动化逻辑：负责大规模初译与术语发现
│   └── proofread2_flow.py# 二校交互式逻辑：支持断点续传与人工/AI 混合微调
├── ui/                   # 【表现层】基于 Tkinter 的响应式多标签页界面
├── utils/                # 【基础设施层】配置管理、自动化日志与错误处理
└── config.yaml           # 全局配置文件

```

## 📦 快速开始

### 环境要求

- Python 3.9+
- 依赖库：`pip install pandas requests pyyaml PyPDF2 python-docx beautifulsoup4`

### 配置设置

新建/编辑根目录下的 `config.yaml`：

```
llm:
  ai_max_workers: 1 # 并发数 (根据 API 限制调整)
  api_key: "你的 API Key"
  base_url: "兼容 OpenAI 格式"
  max_blocks: 12 # 单次请求包含的数据块数量
  max_chars: 8000 # 单次请求最大字符预算
  model: "使用的模型"
  time_wait: 60 # 批次间冷却时间 (秒)
  timeout: 600
ocr:
  api_url: https://ych83fn6yaveg1y3.aistudio-app.com/layout-parsing
  extra:
    max_num_input_imgs: null
  max_batch_pages: 90
  max_retries: 3
  mergeTables: true
  min_batch_pages: 10
  prettifyMarkdown: true
  relevelTitles: true
  restructurePages: true
  retry_interval: 30
  step_pages: 10
  timeout: 600
  token: "你的 OCR Token"
  useChartRecognition: false
  useDocOrientationClassify: false
  useDocUnwarping: false
  useLayoutDetection: true
  visualize: false
```

## 🚀 核心使用流程

### 阶段一：预处理 (PDF -> JSON)

1. 在“预处理”标签页上传 PDF。无论是扫描件还是文字版，系统都会调用 OCR api进行解析。
2. 开启版面分析功能，系统将输出带页码、带块序号的结构化 JSON。这是后续所有校对任务的“底片”。

### 阶段二：AI 一校 (翻译 + 术语匹配)

1. 载入原始（CSV/JSON）。如果已有术语表（JSON），一并载入。
2. **术语提取模式**：一校不仅能进行初步翻译，还能利用 AI 自动抓取文中出现的专有名词、地名、人名，并生成术语建议。
3. 导出专用于paratranslate平台的文件，用于人工校对的doc文档，支持后续二校的json文件和新术语表json文件

### 阶段三：AI 二校 (精修润色)

1. 载入一校json文件。在二校阶段，可以开启多并发校对。
2. **交互式校验**：二校支持在 GUI 界面中实时查看 AI 的校对理由。你可以使用网页版的 ChatGPT、Claude 或 Gemini 配合进行人工/AI 协同审校。
3. **高效产出**：通过设置并发数，实现对整本书的快速润色。
4. 导出专用于paratranslate平台的文件，用于人工校对的doc文档，和原始json文件

### 阶段四：导出最终文档

1. 点击“导出 DOC”或“导出报告”。
2. 系统将生成的 Markdown 流转换为带有分级标题、样式规范、表格完整的 Word 文件。

## 🛠️ 技术深度解析

1. **递归任务拆分算法**：当 AI 响应超时或格式错误时，系统会自动启动递归机制，将当前批次对半拆分并重新请求，直至每一行数据都得到处理。
2. **术语鲁棒性 (Fuzzy Term Matching)**：针对 OCR 将 "Sword" 误识别为 "Sw0rd" 等常见问题，内置模糊匹配算法，确保术语一致性检查依然有效。
3. **多并发冷却机制**：为了应对昂贵且限制 QPS 的顶级 API，系统内置了智能冷却等待功能，在最大化并发的同时避免被封禁 API Key。

## 📦 安装与平台支持

- **Windows**: 针对普通用户，后续我们将提供一键打包的 `.exe` 程序，免去配置 Python 环境的烦恼。
- **Linux/Server**: 推荐开发者克隆 `test` 分支进行编译。你可以通过反代 API 或部署私有模型来实现更深层次的定制化翻译。
- **依赖环境**: Python 3.9+，建议安装 `PyPDF2`、`python-docx` 等库。具体参考 `pip install -r requirements.txt` (如有)。

## 📄 导出格式说明

| 格式 | 用途 |
|------|------|
| **Paratranz JSON** | 用于上传至 Paratranz 在线协同翻译平台。 |
| **Word (.docx)** | 基于 `md2doc.py` 转换，生成包含原文、一校、二校、注释的精美对比报告。 |
| **新术语 JSON** | 汇总所有校对过程中 AI 发现的新专有名词，用于扩充原始术语库。 |
| **原始 JSON** | 包含原始内容与校对内容。 |
| **存档 JSON** | 包含当前进度内所有内容，用于程序从断点继续。 |

## 🤝 报错查找

如果你在使用过程中遇到 API 超时或 OCR 解析异常，请检查：

1. `config.yaml` 中的 `base_url` 是否包含 `/v1`。
2. PDF 文件是否受损。
3. 查看终端中的详细 Log 信息。

## 📝 版本信息

**版本**：1.0.0-Test_Branch **状态**：持续迭代中 **维护者**：Oas7pOo