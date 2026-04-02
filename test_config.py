#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试配置文件读取"""

import sys
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, '.')

from utils.config import ConfigManager
from workflows.proofread1_flow import Proofread1Workflow
from core.llm_engine import LlmEngine

print("测试配置文件读取...")

# 测试 ConfigManager
cfg = ConfigManager()
print(f"直接读取配置:")
print(f"  api_key: {'已设置' if cfg.get('api_key') else '未设置'}")
print(f"  base_url: {cfg.get('base_url')}")
print(f"  llm.model: {cfg.get('llm.model')}")
print(f"  llm.ai_max_workers: {cfg.get('llm.ai_max_workers')}")
print(f"  llm.max_blocks: {cfg.get('llm.max_blocks')}")
print(f"  llm.max_chars: {cfg.get('llm.max_chars')}")
print(f"  llm.time_wait: {cfg.get('llm.time_wait')}")
print(f"  llm.timeout: {cfg.get('llm.timeout')}")

# 测试 Proofread1Workflow 配置读取
print("\n测试 Proofread1Workflow 配置读取:")
workflow = Proofread1Workflow()
print(f"  max_workers: {workflow.runner.max_workers}")
print(f"  delay_seconds: {workflow.runner.delay_seconds}")
print(f"  max_blocks: {workflow.max_blocks}")
print(f"  max_chars: {workflow.max_chars}")

# 测试 LlmEngine 配置读取
print("\n测试 LlmEngine 配置读取:")
llm_engine = LlmEngine()
print(f"  base_url: {llm_engine.base_url}")
print(f"  model: {llm_engine.model}")
print(f"  api_key: {'已设置' if llm_engine.api_key else '未设置'}")
print(f"  timeout: {llm_engine.timeout}")

print("\n配置读取测试完成！")
