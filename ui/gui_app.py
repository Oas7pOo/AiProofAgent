import tkinter as tk
from tkinter import ttk
from ui.tab_preprocess import PreprocessTab
from ui.tab_proof import RunTab
from ui.tab_proof2 import Proof2Tab
from ui.tab_settings import SettingsTab
from utils.logger import setup_root_logger, setup_file_logger

class ProofreadGUI(tk.Tk):
    def __init__(self, config_path: str = "config.yaml"):
        super().__init__()
        self.config_path = config_path
        self.title("AI Proofread Tool")
        self.geometry("950x850")
        setup_root_logger()
        setup_file_logger()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)

        self.tab_preprocess = PreprocessTab(self.notebook, self.config_path)
        self.tab_proof = RunTab(self.notebook, self.config_path)
        self.tab_proof2 = Proof2Tab(self.notebook, self.config_path)
        self.tab_settings = SettingsTab(self.notebook, self.config_path)

        self.notebook.add(self.tab_preprocess, text="预处理 (PDF/OCR)")
        self.notebook.add(self.tab_proof, text="AI 校对")
        self.notebook.add(self.tab_proof2, text="二校")
        self.notebook.add(self.tab_settings, text="设置")
