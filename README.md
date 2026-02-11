# 翻译校对与OCR处理工具

这是一个功能强大的翻译校对和OCR处理工具，专为处理PDF文档和翻译校对任务而设计。

## 项目功能

### 核心功能
- **PDF OCR处理**：将PDF文档转换为可编辑的文本格式
- **翻译校对**：提供AI辅助的翻译校对功能
- **术语管理**：支持术语的提取、管理和应用
- **数据格式转换**：在JSON、CSV等格式之间转换
- **多界面支持**：同时支持图形界面(GUI)和命令行界面(CLI)

### 技术特性
- **AI集成**：集成了DeepSeek等AI模型进行翻译校对
- **OCR技术**：使用PaddleOCR API进行PDF文档识别
- **多线程处理**：支持多线程处理提高效率
- **配置灵活**：通过YAML配置文件管理系统设置
- **错误处理**：完善的错误处理和日志记录

## 项目结构

```
study_py/
├── ai/                 # AI相关功能模块
│   ├── __init__.py
│   └── alignment_service.py  # 对齐服务实现
├── cli/                # 命令行界面
│   ├── __init__.py
│   └── cli_handler.py  # 命令行处理逻辑
├── data/               # 示例数据文件
├── tools/              # 核心工具模块
│   ├── __init__.py
│   ├── data_converter.py      # 数据格式转换
│   ├── dual_alignment_service.py  # 校对服务
│   ├── export_manager.py      # 导出管理
│   ├── io_utils.py            # IO工具函数
│   └── ocr_client.py          # OCR客户端
├── ui/                 # 图形用户界面
│   ├── __init__.py
│   ├── gui_app.py      # 主GUI应用
│   ├── tab_preprocess.py  # 预处理标签页
│   ├── tab_run.py      # 运行标签页
│   └── tab_settings.py # 设置标签页
├── utils/              # 工具函数
│   ├── __init__.py
│   └── config_loader.py  # 配置加载器
├── config.yaml         # 配置文件
├── main.py             # 主入口文件
└── README.md           # 项目说明
```

## 安装与依赖

### 必要依赖
- Python 3.8+
- pandas
- requests
- pyyaml
- tkinter (GUI模式)

### 安装方法

```bash
# 安装依赖
pip install pandas requests pyyaml

# 克隆项目
git clone <repository-url>
cd study_py
```

## 配置说明

项目使用 `config.yaml` 文件进行配置，主要配置项如下：

```yaml
# AI配置
api_key: sk-484fc1c32097c1f568300006732c775f  # API密钥
base_url: https://apis.iflow.cn/v1  # API基础URL
model: deepseek-v3.2  # 使用的AI模型

# OCR配置
ocr:
  api_url: https://ych83fn6yaveg1y3.aistudio-app.com/layout-parsing  # OCR API地址
  token: 52621de9cc8d22bd45e1cce14789b107191bebca  # OCR API令牌

# 其他配置
ai_max_workers: 1  # AI处理最大线程数
max_blocks: 10  # 最大处理块数
max_chars: 8000  # 最大字符数
time_wait: 10  # 等待时间
timeout: 600  # 超时时间
```

## 使用方法

### 图形界面模式

```bash
python main.py --gui
```

GUI模式提供了直观的操作界面，包含三个主要标签页：
- **预处理**：处理PDF文件、导入数据
- **运行**：执行翻译校对任务
- **设置**：配置系统参数

### 命令行模式

```bash
python main.py [options]
```

命令行模式支持批处理和自动化操作，具体参数可通过帮助命令查看。

## 核心模块详解

### OCR处理模块

OCR模块负责将PDF文档转换为可编辑的文本格式：

1. **上传PDF文件**：将PDF文件上传到OCR API
2. **处理结果**：解析OCR API返回的结果
3. **提取文本**：从结果中提取结构化文本
4. **保存输出**：将结果保存为JSON或其他格式

### 翻译校对模块

翻译校对模块使用AI模型进行翻译质量检查和改进：

1. **加载数据**：从文件或内存加载待校对数据
2. **AI处理**：使用AI模型进行翻译校对
3. **结果处理**：处理AI返回的校对结果
4. **术语管理**：提取和应用术语

### 数据转换模块

数据转换模块支持在不同格式之间转换：

1. **PDF到JSON**：将PDF转换为JSON格式
2. **JSON到CSV**：将JSON转换为CSV格式
3. **CSV到JSON**：将CSV转换为JSON格式

## 示例用法

### 1. PDF OCR处理

```python
from tools.data_converter import DataConverter
import yaml

# 加载配置
config = yaml.safe_load(open('config.yaml'))

# 创建转换器实例
converter = DataConverter(config)

# 处理PDF文件
converter.pdf_to_file('input.pdf', 'output.json', 'json')
```

### 2. 翻译校对

```python
from tools.dual_alignment_service import ProofreadApp
import yaml

# 加载配置
config = yaml.safe_load(open('config.yaml'))

# 创建校对应用
app = ProofreadApp(config)

# 导入数据
app.import_from_json('input.json')

# 运行校对
app.run_proofread()

# 导出结果
app.export_project('output_final.json')
```

## 常见问题与故障排除

### OCR相关问题

**问题**：OCR API Error: None
**解决方案**：检查OCR API的URL和令牌是否正确，确保网络连接正常

**问题**：SSL证书验证失败
**解决方案**：检查API URL是否正确，确保使用的是有效的HTTPS URL

### 依赖问题

**问题**：No module named 'pandas'
**解决方案**：运行 `pip install pandas` 安装缺失的依赖

**问题**：GUI Import Failed
**解决方案**：确保安装了tkinter，对于Linux系统可能需要单独安装

### API相关问题

**问题**：API Token过期
**解决方案**：访问API提供商的网站重新生成API令牌，并更新config.yaml文件

**问题**：API调用限制
**解决方案**：减少并发请求数，增加请求间隔时间

## 配置与部署

### 生产环境配置

1. **配置文件**：根据实际需求修改config.yaml文件
2. **API密钥**：确保使用有效的API密钥
3. **性能调优**：根据服务器性能调整ai_max_workers等参数
4. **监控**：设置适当的日志记录和监控

### 开发环境设置

1. **克隆代码**：`git clone <repository-url>`
2. **安装依赖**：`pip install -r requirements.txt`（如果有）
3. **运行测试**：`python test.py`
4. **启动应用**：`python main.py --gui`

## 技术栈

- **编程语言**：Python 3.8+
- **GUI框架**：Tkinter
- **数据处理**：Pandas
- **网络请求**：Requests
- **配置管理**：PyYAML
- **AI模型**：DeepSeek
- **OCR技术**：PaddleOCR API

## 许可证

本项目采用MIT许可证。

## 贡献

欢迎提交问题和改进建议！如果您想为项目贡献代码，请遵循以下步骤：

1. Fork本项目
2. 创建您的特性分支
3. 提交您的更改
4. 推送到分支
5. 开启一个Pull Request

## 联系信息

如有任何问题或建议，请通过以下方式联系：

- 项目维护者：[维护者名称]
- 电子邮件：[email@example.com]
- GitHub：[GitHub仓库链接]

---

**版本**：1.0.0
**更新日期**：2026-02-08