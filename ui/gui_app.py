# gui_app.py
import tkinter as tk
from tkinter import ttk
from ui.tab_preprocess import PreprocessTab
from ui.tab_proof import RunTab
from ui.tab_proof2 import Proof2Tab     # <<< 新增
from ui.tab_settings import SettingsTab

class ProofreadGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Proofread Tool")
        self.geometry("950x850")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        self.tab_prep = PreprocessTab(self.notebook)
        self.tab_run = RunTab(self.notebook)
        self.tab_p2 = Proof2Tab(self.notebook)   # <<< 新增
        self.tab_settings = SettingsTab(self.notebook)

        self.notebook.add(self.tab_prep, text='预处理 (PDF/OCR)')
        self.notebook.add(self.tab_run, text='AI 校对')
        self.notebook.add(self.tab_p2, text='二校')          # <<< 新增
        self.notebook.add(self.tab_settings, text='设置')

if __name__ == "__main__":
    app = ProofreadGUI()
    app.mainloop()
