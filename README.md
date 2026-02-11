# AiProofAgent

**AI 驱动的翻译校对与 OCR 处理工具**

一个功能强大、易用的翻译校对和 PDF OCR 处理工具，专为文档本地化和翻译质量提升而设计。

## 🚀 功能亮点

### 核心功能
- **PDF 转文本**：使用 OCR 技术将 PDF 文档转换为可编辑的文本格式
- **AI 翻译校对**：集成 DeepSeek 等 AI 模型进行专业级翻译校对
- **术语管理**：自动提取、管理和应用专业术语
- **多格式转换**：支持 JSON、CSV 等格式之间的无缝转换
- **双界面支持**：同时提供直观的图形界面 (GUI) 和高效的命令行界面 (CLI)

### 技术特性
- **智能 AI 集成**：利用最新的 AI 模型提高翻译质量
- **精准 OCR 识别**：使用 PaddleOCR API 进行高质量文档识别
- **高效多线程**：支持多线程处理，大幅提高工作效率
- **灵活配置**：通过 YAML 配置文件轻松管理系统设置
- **完善的错误处理**：详细的错误信息和日志记录，让问题排查更简单

## 📁 项目结构

```
AiProofAgent/
├── ai/                 # AI 相关功能模块
│   ├── __init__.py
│   └── alignment_service.py  # 对齐服务实现
├── cli/                # 命令行界面
│   ├── __init__.py
│   └── cli_handler.py  # 命令行处理逻辑
├── tools/              # 核心工具模块
│   ├── __init__.py
│   ├── data_converter.py      # 数据格式转换
│   ├── export_manager.py      # 导出管理
│   ├── io_utils.py            # IO 工具函数
│   ├── ocr_client.py          # OCR 客户端
│   ├── proofread_service.py   # 校对服务
│   └── proofread2_service.py  # 二校服务
├── ui/                 # 图形用户界面
│   ├── __init__.py
│   ├── gui_app.py      # 主 GUI 应用
│   ├── tab_preprocess.py  # 预处理标签页
│   ├── tab_proof.py    # 校对标签页
│   ├── tab_proof2.py   # 二校标签页
│   └── tab_settings.py # 设置标签页
├── utils/              # 工具函数
│   ├── __init__.py
│   └── config_loader.py  # 配置加载器
├── config.yaml         # 配置文件
├── main.py             # 主入口文件
├── README.md           # 项目说明
└── .gitignore          # Git 忽略文件
```

## 🛠️ 安装与配置

### 系统要求
- Python 3.8 或更高版本
- 稳定的网络连接（用于 AI 和 OCR API 调用）

### 安装依赖

```bash
# 安装必要的依赖包
pip install pandas requests pyyaml

# 克隆项目代码
git clone https://github.com/Oas7pOo/AiProofAgent.git
cd AiProofAgent
```

### 配置文件设置

编辑 `config.yaml` 文件，填写你的 API 密钥和配置信息：

```yaml
# AI 配置
api_key: 你的 API 密钥  # 从 https://platform.iflow.cn 获取
base_url: https://apis.iflow.cn/v1
model: deepseek-v3.2

# OCR 配置
ocr:
  api_url: https://ych83fn6yaveg1y3.aistudio-app.com/layout-parsing
  token: 你的 OCR API 令牌

# 性能配置
ai_max_workers: 1  # 根据你的 CPU 核心数调整
max_blocks: 10
max_chars: 8000
time_wait: 10
timeout: 600
```

## 🎯 使用方法

### 图形界面模式（推荐）

直接运行主程序，默认启动 GUI 模式：

```bash
python main.py

# 或者显式指定 GUI 模式
python main.py --gui
```

GUI 界面包含四个主要标签页：

1. **预处理**：上传和处理 PDF 文件，转换为可编辑格式
2. **AI 校对**：执行 AI 辅助的翻译校对任务
3. **二校**：基于一校结果进行最终校对
4. **设置**：配置系统参数和 API 密钥

### 命令行模式

命令行模式适合自动化脚本和批处理操作：

```bash
# 查看帮助信息
python main.py --help

# 基本用法示例
python main.py \
  --archive "我的项目" \
  --in-pdf "文档.pdf" \
  --out-json "output.json" \
  --terms "术语表.csv" \
  --run-ai
```

### 常见操作示例

#### 1. PDF 转 JSON（使用 OCR）

```bash
python main.py \
  --archive "PDF处理" \
  --in-pdf "example.pdf" \
  --out-json "example.json"
```

#### 2. 翻译校对（批处理）

```bash
python main.py \
  --archive "校对任务" \
  --in-json "input.json" \
  --out-json "output.json" \
  --terms "terms.csv" \
  --run-ai
```

## 📖 核心功能详解

### PDF OCR 处理

1. **上传 PDF**：系统会将 PDF 文件上传到 OCR API
2. **智能识别**：OCR 服务会识别文档结构和内容
3. **文本提取**：提取识别后的文本并进行结构化处理
4. **格式转换**：将结果转换为 JSON 或其他格式保存

### AI 翻译校对

1. **数据准备**：加载待校对的文本数据
2. **术语匹配**：自动匹配和应用术语表中的术语
3. **AI 处理**：调用 AI 模型进行专业级校对
4. **结果处理**：处理 AI 返回的校对结果并应用到原文
5. **术语提取**：自动提取新出现的专业术语

### 二校流程

1. **加载一校结果**：读取一校生成的存档文件
2. **术语对比**：同时使用旧术语表和新术语建议
3. **精细校对**：基于一校结果进行最终优化
4. **质量保证**：确保最终译文的准确性和一致性

## 🔧 故障排除

### 常见问题解决

| 问题 | 解决方案 |
|------|----------|
| OCR API Error | 检查 OCR API 令牌是否正确，网络连接是否正常 |
| API Token 过期 | 访问 API 提供商网站重新生成令牌并更新 config.yaml |
| No module named 'pandas' | 运行 `pip install pandas` 安装缺失的依赖 |
| GUI Import Failed | 确保安装了 tkinter（Windows 和 macOS 通常默认安装） |
| SSL 证书错误 | 检查 API URL 是否为有效的 HTTPS 地址 |
| AI 连接失败 | 检查网络连接和 API 密钥是否正确 |

### 性能优化

- **提高处理速度**：根据你的 CPU 核心数增加 `ai_max_workers` 值
- **减少内存使用**：对于大型文档，减小 `max_blocks` 值
- **避免 API 限制**：确保 `time_wait` 设置合理，避免触发 API 速率限制

## 📚 技术栈

- **编程语言**：Python 3.8+
- **GUI 框架**：Tkinter（Python 标准库）
- **数据处理**：Pandas
- **网络请求**：Requests
- **配置管理**：PyYAML
- **AI 模型**：DeepSeek
- **OCR 技术**：PaddleOCR API

## 🤝 贡献指南

欢迎为项目贡献代码和建议！贡献步骤：

1. **Fork** 本项目
2. **创建** 你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. **提交** 你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. **推送** 到分支 (`git push origin feature/AmazingFeature`)
5. **开启** 一个 Pull Request

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 📞 联系与反馈

如有问题或建议，请通过 GitHub Issues 与我们联系：

- **GitHub Issues**：[提交问题或建议](https://github.com/Oas7pOo/AiProofAgent/issues)
- **项目地址**：[Oas7pOo/AiProofAgent](https://github.com/Oas7pOo/AiProofAgent)

---

**版本**：1.0.0
**更新日期**：2026-02-11
