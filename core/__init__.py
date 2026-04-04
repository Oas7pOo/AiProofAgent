"""核心功能模块"""

from .format_converter import FormatConverter
from .llm_engine import LlmEngine
from .md2doc import parse_and_convert
from .ocr_engine import PaddleOCREngine
from .term_manager import TermManager
from .utils import match_terms_for_block, format_terms

__all__ = [
    'FormatConverter',
    'LlmEngine',
    'parse_and_convert',
    'PaddleOCREngine',
    'TermManager',
    'match_terms_for_block',
    'format_terms'
]