# AiProofAgent 项目重构设计文档

## 一、 项目现状与痛点分析

### 1. 现有架构梳理

当前项目实现了一个功能完整的翻译校对流水线（PDF OCR -> 数据切分 -> 一校 -> 二校 -> 导出）。项目的模块划分初具雏形，主要分为：

* **UI层 (`ui/`)**: 基于 Tkinter，分为预处理、一校、二校和设置四个 Tab。
* **CLI层 (`cli/`)**: 提供了简易的命令行入口。
* **核心逻辑层 (`tools/`, `ai/`)**:
  * `proofread_service.py` / `proofread2_service.py`: 负责一校和二校的核心业务编排与提示词（Prompt）生成。
  * `ocr_client.py`: 封装 PaddleOCR API，支持自适应批处理和重试机制。
  * `alignment_service.py`: 封装 LLM API 调用与 JSON 解析。
  * `data_converter.py` / `io_utils.py` / `export_manager.py`: 负责数据转换、文件读写和最终产物导出。
* **配置层 (`utils/`)**: 简单的 YAML 配置读写。

### 2. 当前存在的痛点（重构的动机）

虽然功能完整且包含了一些优秀的设计（如 `StageRunner` 抽象、OCR自适应重试），但代码层面存在以下问题，限制了可维护性和扩展性：

1. **UI 与业务逻辑严重耦合**：
   * 在 `tab_preprocess.py`、`tab_proof.py` 和 `tab_proof2.py` 中，UI 线程不仅负责更新界面，还直接管理多线程（`threading.Thread`）、捕获异常，并通过粗暴地劫持标准输出（`sys.stdout = TextRedirector`）来打印日志。
2. **数据模型（Data Models）散落与重复**：
   * 一校的数据结构 `AlignItem` 在 `proofread_service.py` 中定义。
   * 二校的数据结构 `Proof2Item` 在 `proofread2_service.py` 中定义。
   * 两者高度相似，但缺乏统一的继承或组合机制。导致数据在多个阶段流转时，解析和处理逻辑重复。
3. **状态管理分散**：
   * 任务的上下文（如已完成多少块、正在处理哪个批次）散落在 `ProofreadApp`、`Proofread2Project` 以及 UI 组件自身的状态中。
4. **错误处理与日志不够标准**：
   * 大量使用 `print()` 输出日志，并依赖 UI 层的重定向。缺少标准的 `logging` 模块机制，导致无法进行多级别日志过滤、持久化或无头环境（CLI）下的优雅日志记录。
5. **依赖注入不彻底**：
   * 模块之间直接实例化依赖（如 `DataConverter` 中直接初始化 `PaddleAPIOcr`，或 UI 层直接加载配置传递给 Service）。

---

## 二、 重构目标与原则

1. **单一职责原则 (SRP)**：UI 只管显示和接收用户输入，Service 只管业务逻辑，Model 只管数据结构。
2. **统一数据流**：定义全局统一的项目和任务数据模型（DTO），贯穿 OCR -> 一校 -> 二校全生命周期。
3. **标准化日志系统**：废除 `sys.stdout` 劫持，使用 Python 原生 `logging` 模块加自定义的 GUI Handler 同步日志。
4. **可测试性**：将核心业务逻辑从多线程框架和 UI 中剥离，使其能够通过编写简单的单元测试进行验证。

---

## 三、 重构后的系统架构设计

建议采用经典的 **分层架构 + 领域模型 (Domain Model)**，将目录结构调整如下：

**Plaintext**  纯文本

```
AiProofAgent/
├── models/               # 数据模型层 (纯数据结构)
│   ├── __init__.py
│   ├── document.py       # 定义 TranslationBlock (取代 AlignItem 和 Proof2Item)
│   ├── term.py           # 定义 TermEntry
│   └── project.py        # 定义 ProjectInfo, RunStatus 等
├── core/                 # 核心服务层 (无 UI 依赖，可被 CLI 或 GUI 调用)
│   ├── __init__.py
│   ├── ocr_engine.py     # 原 ocr_client.py 优化
│   ├── llm_engine.py     # 原 alignment_service.py 优化
│   ├── term_manager.py   # 术语匹配引擎 (从 proofread_service 抽离)
│   └── format_converter.py # 原 data_converter 和 io_utils
├── workflows/            # 业务流编排层 (Pipeline)
│   ├── __init__.py
│   ├── base_runner.py    # 原 StageRunner, 负责批处理与多线程并发重试机制
│   ├── proofread1_flow.py# 一校业务逻辑
│   └── proofread2_flow.py# 二校业务逻辑
├── ui/                   # 表现层 (Tkinter)
│   ├── __init__.py
│   ├── gui_app.py
│   ├── views/            # 拆分原各个 tab
│   ├── components/       # 封装可复用的 UI 控件 (如日志框, 路径选择器)
│   └── gui_logger.py     # 基于 logging 模块的 GUI Log Handler
├── cli/                  # 命令行层
├── utils/                # 基础设施层
│   ├── logger.py         # 全局日志配置
│   └── config.py         # 原 config_loader
├── main.py               # 入口点
└── config.yaml           # 用户配置
```

---

## 四、 核心模块重构方案指南

### 1. 数据模型层重构 (`models/`)

将 `AlignItem` 和 `Proof2Item` 合并为统一的 `TranslationBlock`。避免在阶段之间写大量的映射代码。

**Python**

```
# models/document.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class TranslationBlock:
    key: str
    page: Optional[int] = None
    block_num: Optional[int] = None
    en_block: str = ""
    zh_block: str = ""               # 原始译文/OCR直接翻译
  
    # 一校产物
    proofread1_zh: str = ""        
    proofread1_note: str = ""
    new_terms: List[Dict[str, str]] = field(default_factory=list)
  
    # 二校产物
    proofread_zh: str = ""           # 最终译文
    proofread_note: str = ""         # 最终备注
  
    # 状态标记
    stage: int = 0                   # 0:未处理, 1:一校完成, 2:二校完成, -1:出错
```

### 2. 日志系统重构 (解决 `sys.stdout` 劫持问题)

不要在 UI 层替换 `sys.stdout`。创建一个标准的 Python Logger 处理器：

**Python**

```
# ui/gui_logger.py
import logging

class TextHandler(logging.Handler):
    """用于将标准日志输出到 Tkinter Text 组件的 Handler"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        # 使用 after 确保线程安全
        self.text_widget.after(0, self._append, msg + '\n')
      
    def _append(self, msg):
        self.text_widget.config(state="normal")
        self.text_widget.insert("end", msg)
        self.text_widget.see("end")
        self.text_widget.config(state="disabled")

# 在 main.py 或 utils/logger.py 中配置
# logger = logging.getLogger("AiProofAgent")
```

### 3. Workflow 与多线程抽象重构

现在的 `tab_proof.py` 内部有很多形如 `threading.Thread(target=self._bg_run)` 的逻辑。应该将其转移到 `workflows` 层，UI 只需传入回调函数（Callback）。

**Python**

```
# workflows/proofread1_flow.py
import threading
import logging

logger = logging.getLogger("AiProofAgent")

class Proofread1Workflow:
    def __init__(self, config, project, llm_engine):
        self.config = config
        self.project = project
        self.llm = llm_engine

    def execute_async(self, progress_callback=None, done_callback=None, error_callback=None):
        def _task():
            try:
                logger.info("开始一校流水线...")
                # ... 原有的 runner.process_recursive 等逻辑 ...
                if done_callback:
                    done_callback()
            except Exception as e:
                logger.error(f"一校失败: {e}")
                if error_callback:
                    error_callback(e)

        threading.Thread(target=_task, daemon=True).start()
```

这样，UI 层（`tab_proof.py`）只需调用 `workflow.execute_async(done_callback=self._on_done)`，代码会极大简化，彻底解耦。

### 4. 业务组件整合

当前 `tools/proofread_service.py` 包含了 Prompt 生成、阶段数据校验等逻辑 (`StageSpec`)。这部分抽象非常好，应当保留，但需重命名并移入 `workflows/` 下。

* `StageRunner` -> `BatchTaskRunner`：使其更加通用，不限于某个特定阶段。
* 术语匹配：将现有的 `Terms` 类抽离为独立的 `TermManager` (对应 `core/term_manager.py`)，负责正则编译和文本匹配。

---

## 五、 重构实施计划 (步骤建议)

为了保证重构的安全性，避免系统崩溃，建议采取渐进式重构（Strangler Fig Pattern）：

* **阶段 1：基础设施剥离**
  1. 引入原生的 `logging` 模块。
  2. 将 `sys.stdout` 劫持的代码替换为 `GUI_Logger` Handler。
  3. 将原 `config_loader.py` 加强，使用类单例模式或依赖注入传递。
* **阶段 2：数据模型统一**
  1. 创建 `models/` 文件夹。
  2. 将分散的 `AlignItem`, `Proof2Item`, `TermEntry` 转换为 `@dataclass`，放置于独立文件中。
  3. 调整所有读写逻辑（如 `io_utils.py`）适配新的统一数据模型。
* **阶段 3：服务层与业务流抽离**
  1. 将 LLM 请求提取到 `core/llm_engine.py`，确保它只负责与 API 通信，不知道任何业务。
  2. 将 OCR 客户端移动并稍微重构其错误处理机制。
  3. 创建 `workflows/`，把 `ProofreadApp` 里的后台线程逻辑和 `StageRunner` 搬迁过去。提供 `execute_async` 和回调用以供 UI 调用。
* **阶段 4：UI 层瘦身**
  1. 重构 `tab_*.py`，将内部所有的文件读写、数据构造移除，只保留：按钮点击 -> 读取配置 -> 调用 Workflow -> 触发回调 -> 更新 UI。
  2. 整合 UI 组件代码（例如共用的路径选择行 `_create_file_row` 抽取为通用的 Custom Tkinter Widget）。
