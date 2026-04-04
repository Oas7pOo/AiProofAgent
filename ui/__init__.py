"""UI界面模块"""

from .gui_app import ProofreadGUI
from .tab_preprocess import PreprocessTab
from .tab_proof import RunTab
from .tab_proof2 import Proof2Tab
from .tab_settings import SettingsTab

__all__ = [
    'ProofreadGUI',
    'PreprocessTab',
    'RunTab',
    'Proof2Tab',
    'SettingsTab'
]