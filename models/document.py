from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class TranslationBlock:
    """
    核心翻译块模型（DTO），贯穿 OCR -> 一校 -> 二校 的全生命周期，
    取代原本散落的 AlignItem 和 Proof2Item。
    """
    key: str                         # 唯一标识，例如 "1_1" (页码_段落序号)
    page: Optional[int] = None       # 页码
    block_num: Optional[int] = None  # 页内的段落序号
    en_block: str = ""               # 原文（英文）
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